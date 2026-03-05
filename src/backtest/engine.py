"""Backtest engine — end-to-end simulation orchestrator (T-602, SPEC §9.1–9.4).

Loads OHLCV candles, generates signals bar-by-bar, applies pre-trade risk checks,
simulates fills via the T-601 simulator, manages open positions with stop-loss
controls (hard/trailing/time stops), and produces an equity curve + trade list.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from src.analysis.signal_contract import (
    FeatureSnapshot,
    GeneratorConfig,
    SignalGenerator,
)
from src.backtest.simulator import FillConfig, simulate_fill
from src.data.fetcher_base import CandleRecord
from src.trading.risk import (
    InTradeAction,
    ResolvedRiskConfig,
    evaluate_in_trade_controls,
    kelly_size,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Domain models — all frozen per DEC-010
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BacktestConfig:
    """Configuration for a single backtest run."""

    instrument: str
    interval: str
    start_date: datetime
    end_date: datetime
    initial_equity: float
    pessimistic: bool


@dataclass(frozen=True)
class BacktestTrade:
    """Record of a single simulated trade."""

    entry_time: datetime
    entry_price: float
    exit_time: datetime | None
    exit_price: float | None
    direction: Literal["BUY", "SELL"]
    quantity: float
    pnl: float
    commission: float
    slippage_cost: float
    spread_cost: float
    exit_reason: str
    regime_label: str


@dataclass(frozen=True)
class BacktestResult:
    """Complete output of a backtest run."""

    config: BacktestConfig
    equity_curve: list[tuple[datetime, float]]
    trades: list[BacktestTrade]
    initial_equity: float
    final_equity: float
    total_return: float
    trade_count: int


# ---------------------------------------------------------------------------
# Internal mutable position tracker (not exported)
# ---------------------------------------------------------------------------


class _OpenPosition:
    """Mutable in-flight position state used only within the engine loop."""

    __slots__ = (
        "direction", "entry_time", "entry_price", "quantity",
        "stop_price", "commission", "slippage_cost", "spread_cost",
        "regime_label",
    )

    def __init__(
        self,
        *,
        direction: Literal["BUY", "SELL"],
        entry_time: datetime,
        entry_price: float,
        quantity: float,
        stop_price: float,
        commission: float,
        slippage_cost: float,
        spread_cost: float,
        regime_label: str,
    ) -> None:
        self.direction = direction
        self.entry_time = entry_time
        self.entry_price = entry_price
        self.quantity = quantity
        self.stop_price = stop_price
        self.commission = commission
        self.slippage_cost = slippage_cost
        self.spread_cost = spread_cost
        self.regime_label = regime_label

    def unrealized_pnl(self, current_price: float) -> float:
        """Mark-to-market PnL (before commission)."""
        if self.direction == "BUY":
            return (current_price - self.entry_price) * self.quantity
        return (self.entry_price - current_price) * self.quantity

    def close(self, exit_price: float, exit_time: datetime, reason: str) -> BacktestTrade:
        """Close the position and return a frozen BacktestTrade."""
        if self.direction == "BUY":
            raw_pnl = (exit_price - self.entry_price) * self.quantity
        else:
            raw_pnl = (self.entry_price - exit_price) * self.quantity
        pnl = raw_pnl - self.commission
        return BacktestTrade(
            entry_time=self.entry_time,
            entry_price=self.entry_price,
            exit_time=exit_time,
            exit_price=exit_price,
            direction=self.direction,
            quantity=self.quantity,
            pnl=pnl,
            commission=self.commission,
            slippage_cost=self.slippage_cost,
            spread_cost=self.spread_cost,
            exit_reason=reason,
            regime_label=self.regime_label,
        )

    def open_hours(self, current_time: datetime) -> float:
        """Hours since entry."""
        return (current_time - self.entry_time).total_seconds() / 3600.0


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


def run_backtest(
    *,
    candles: Sequence[CandleRecord],
    signal_generator: SignalGenerator,
    generator_config: GeneratorConfig,
    fill_config: FillConfig,
    risk_config: ResolvedRiskConfig,
    config: BacktestConfig,
) -> BacktestResult:
    """Run an end-to-end backtest simulation.

    Args:
        candles: Pre-loaded OHLCV candle data (must be sorted by time).
        signal_generator: Any SignalGenerator protocol implementation.
        generator_config: Generator configuration (enabled, parameters).
        fill_config: Fill model config from build_fill_config (T-601).
        risk_config: Resolved risk parameters.
        config: Backtest date range and instrument configuration.

    Returns:
        BacktestResult with equity curve, trade list, and summary stats.
    """
    sorted_candles = sorted(candles, key=lambda c: c.time)

    # Filter to instrument, interval, and date range
    filtered = [
        c for c in sorted_candles
        if c.instrument == config.instrument
        and c.interval == config.interval
        and config.start_date <= c.time <= config.end_date
    ]

    if len(filtered) < 2:
        return BacktestResult(
            config=config,
            equity_curve=[],
            trades=[],
            initial_equity=config.initial_equity,
            final_equity=config.initial_equity,
            total_return=0.0,
            trade_count=0,
        )

    equity = config.initial_equity
    cash = config.initial_equity
    position: _OpenPosition | None = None
    trades: list[BacktestTrade] = []
    equity_curve: list[tuple[datetime, float]] = []

    # Trade statistics for Kelly sizing
    completed_trades: list[BacktestTrade] = []

    for i, bar in enumerate(filtered):
        is_last_bar = i == len(filtered) - 1

        # --- 1. Manage open position ---
        if position is not None:
            # Check hard stop against bar's price action
            closed_trade = _check_stop_hit(position, bar)
            if closed_trade is not None:
                cash += position.entry_price * position.quantity + closed_trade.pnl
                trades.append(closed_trade)
                completed_trades.append(closed_trade)
                position = None
            else:
                # Evaluate in-trade controls (time stop, trailing stop)
                action = _evaluate_controls(position, bar, risk_config)
                if action.action == "CLOSE":
                    closed_trade = position.close(bar.close, bar.time, _reason_label(action))
                    cash += position.entry_price * position.quantity + closed_trade.pnl
                    trades.append(closed_trade)
                    completed_trades.append(closed_trade)
                    position = None
                elif action.action == "MOVE_STOP" and action.new_stop is not None:
                    position.stop_price = action.new_stop

        # --- 2. Force close at end of data ---
        if is_last_bar and position is not None:
            closed_trade = position.close(bar.close, bar.time, "end_of_data")
            cash += position.entry_price * position.quantity + closed_trade.pnl
            trades.append(closed_trade)
            completed_trades.append(closed_trade)
            position = None

        # --- 3. Generate signal and open new position ---
        if not is_last_bar and position is None:
            features = _build_features(bar, config)
            signal = signal_generator.generate(
                config.instrument, features, generator_config,
            )

            if signal.action in ("BUY", "SELL", "STRONG_BUY"):
                direction: Literal["BUY", "SELL"] = (
                    "SELL" if signal.action == "SELL" else "BUY"
                )

                # Pre-trade: position limit already enforced (position is None)
                # Position sizing via Kelly
                stats = _trade_stats(completed_trades)
                sizing = kelly_size(
                    win_rate=stats["win_rate"],
                    avg_win=stats["avg_win"],
                    avg_loss=stats["avg_loss"],
                    equity=cash,
                    config=risk_config,
                    regime_confidence=None,  # Regime not integrated in v1 engine
                    num_trades=int(stats["num_trades"]),
                )

                if sizing.units > 0:
                    next_bar = filtered[i + 1]
                    fill = simulate_fill(
                        direction=direction,
                        next_bar_open=next_bar.open,
                        fill_time=next_bar.time,
                        config=fill_config,
                    )

                    # Convert dollar risk to quantity
                    stop_distance = fill.fill_price * risk_config.hard_stop_pct
                    if stop_distance > 0:
                        quantity = sizing.units / stop_distance
                    else:
                        quantity = 0.0

                    if quantity > 0:
                        # Compute stop price
                        if direction == "BUY":
                            stop_price = fill.fill_price * (1.0 - risk_config.hard_stop_pct)
                        else:
                            stop_price = fill.fill_price * (1.0 + risk_config.hard_stop_pct)

                        cost_of_entry = fill.fill_price * quantity
                        cash -= cost_of_entry

                        position = _OpenPosition(
                            direction=direction,
                            entry_time=fill.fill_time,
                            entry_price=fill.fill_price,
                            quantity=quantity,
                            stop_price=stop_price,
                            commission=fill.commission_cost * quantity,
                            slippage_cost=fill.slippage_cost,
                            spread_cost=fill.spread_cost,
                            regime_label="UNKNOWN",
                        )

        # --- 4. Record equity ---
        if position is not None:
            mark_to_market = position.unrealized_pnl(bar.close)
            equity = cash + position.entry_price * position.quantity + mark_to_market
        else:
            equity = cash
        equity_curve.append((bar.time, equity))

    final_equity = equity_curve[-1][1] if equity_curve else config.initial_equity
    total_return = (final_equity - config.initial_equity) / config.initial_equity

    return BacktestResult(
        config=config,
        equity_curve=equity_curve,
        trades=trades,
        initial_equity=config.initial_equity,
        final_equity=final_equity,
        total_return=total_return,
        trade_count=len(trades),
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_features(bar: CandleRecord, config: BacktestConfig) -> FeatureSnapshot:
    """Build a minimal FeatureSnapshot from a candle bar."""
    return FeatureSnapshot(
        instrument=config.instrument,
        interval=config.interval,
        time=bar.time,
        values={
            "_open": bar.open,
            "_high": bar.high,
            "_low": bar.low,
            "_close": bar.close,
            "_volume": bar.volume,
        },
        metadata={},
    )


def _check_stop_hit(
    position: _OpenPosition,
    bar: CandleRecord,
) -> BacktestTrade | None:
    """Check if the bar's price action hits the hard stop."""
    if position.direction == "BUY":
        if bar.low <= position.stop_price:
            return position.close(position.stop_price, bar.time, "hard_stop")
    else:
        if bar.high >= position.stop_price:
            return position.close(position.stop_price, bar.time, "hard_stop")
    return None


def _evaluate_controls(
    position: _OpenPosition,
    bar: CandleRecord,
    risk_config: ResolvedRiskConfig,
) -> InTradeAction:
    """Evaluate in-trade controls for an open position."""
    return evaluate_in_trade_controls(
        entry_price=position.entry_price,
        current_price=bar.close,
        current_stop=position.stop_price,
        open_hours=position.open_hours(bar.time),
        current_atr=0.0,  # Simplified: ATR not tracked bar-by-bar in v1
        avg_atr_30d=0.0,
        config=risk_config,
        direction=position.direction,
    )


def _reason_label(action: InTradeAction) -> str:
    """Extract a short exit reason label from an InTradeAction."""
    reason = action.reason.lower()
    if "time stop" in reason:
        return "time_stop"
    if "volatility" in reason:
        return "volatility_stop"
    if "trailing" in reason:
        return "trailing_stop"
    return "in_trade_control"


def _trade_stats(completed: list[BacktestTrade]) -> dict[str, float]:
    """Compute rolling trade statistics for Kelly sizing."""
    if not completed:
        return {"win_rate": 0.0, "avg_win": 0.0, "avg_loss": 0.0, "num_trades": 0}

    wins = [t.pnl for t in completed if t.pnl > 0]
    losses = [abs(t.pnl) for t in completed if t.pnl <= 0]

    win_rate = len(wins) / len(completed) if completed else 0.0
    avg_win = sum(wins) / len(wins) if wins else 0.0
    avg_loss = sum(losses) / len(losses) if losses else 0.0

    return {
        "win_rate": win_rate,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "num_trades": len(completed),
    }
