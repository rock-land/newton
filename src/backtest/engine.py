"""Backtest engine — end-to-end simulation orchestrator (T-602, SPEC §9.1–9.4).

Loads OHLCV candles, generates signals bar-by-bar, applies pre-trade risk checks,
simulates fills via the T-601 simulator, manages open positions with stop-loss
controls (hard/trailing/time stops), and produces an equity curve + trade list.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

import numpy as np

from src.analysis.signal_contract import (
    FeatureSnapshot,
    GeneratorConfig,
    SignalGenerator,
)
from src.backtest.simulator import FillConfig, simulate_fill
from src.data.fetcher_base import CandleRecord
from src.data.indicators import TechnicalIndicatorProvider
from src.regime.detector import (
    ADX_PERIOD,
    VOL_WINDOW,
    classify_regime,
    compute_adx_14,
    compute_vol_30d,
    compute_vol_median,
)
from src.trading.risk import (
    InTradeAction,
    ResolvedRiskConfig,
    evaluate_in_trade_controls,
    kelly_size,
)

logger = logging.getLogger(__name__)

# Minimum bars for regime detection (ADX needs 2×period)
_MIN_REGIME_BARS = 2 * ADX_PERIOD

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

    def close(
        self,
        exit_price: float,
        exit_time: datetime,
        reason: str,
        fill_config: FillConfig | None = None,
    ) -> BacktestTrade:
        """Close the position and return a frozen BacktestTrade.

        If fill_config is provided, exit-side transaction costs (slippage,
        spread, commission) are computed via simulate_fill and deducted from PnL.
        """
        exit_direction: Literal["BUY", "SELL"] = (
            "SELL" if self.direction == "BUY" else "BUY"
        )

        exit_slippage = 0.0
        exit_spread = 0.0
        exit_commission = 0.0

        if fill_config is not None:
            exit_fill = simulate_fill(
                direction=exit_direction,
                next_bar_open=exit_price,
                fill_time=exit_time,
                config=fill_config,
            )
            exit_price = exit_fill.fill_price
            exit_slippage = exit_fill.slippage_cost
            exit_spread = exit_fill.spread_cost
            exit_commission = exit_fill.commission_cost * self.quantity

        if self.direction == "BUY":
            raw_pnl = (exit_price - self.entry_price) * self.quantity
        else:
            raw_pnl = (self.entry_price - exit_price) * self.quantity

        total_commission = self.commission + exit_commission
        pnl = raw_pnl - total_commission

        return BacktestTrade(
            entry_time=self.entry_time,
            entry_price=self.entry_price,
            exit_time=exit_time,
            exit_price=exit_price,
            direction=self.direction,
            quantity=self.quantity,
            pnl=pnl,
            commission=total_commission,
            slippage_cost=self.slippage_cost + exit_slippage,
            spread_cost=self.spread_cost + exit_spread,
            exit_reason=reason,
            regime_label=self.regime_label,
        )

    def open_hours(self, current_time: datetime) -> float:
        """Hours since entry."""
        return (current_time - self.entry_time).total_seconds() / 3600.0


# ---------------------------------------------------------------------------
# Pre-computation helpers
# ---------------------------------------------------------------------------


def _precompute_features(
    filtered: list[CandleRecord],
    config: BacktestConfig,
) -> dict[datetime, dict[str, float]]:
    """Pre-compute indicator features for all bars using TechnicalIndicatorProvider."""
    provider = TechnicalIndicatorProvider()
    feature_map = provider.get_features(
        instrument=config.instrument,
        interval=config.interval,
        candles=list(filtered),
        lookback=max(26, len(filtered)),  # Ensure full lookback
    )
    return feature_map


def _annualization_factor(instrument: str) -> float:
    """Return annualization factor based on instrument type."""
    if "BTC" in instrument or "ETH" in instrument:
        return math.sqrt(365)
    return math.sqrt(252)


def _precompute_regimes(
    filtered: list[CandleRecord],
    instrument: str,
) -> dict[datetime, str]:
    """Pre-compute regime labels for each bar where sufficient history exists."""
    regime_map: dict[datetime, str] = {}
    ann_factor = _annualization_factor(instrument)

    closes_list = [c.close for c in filtered]
    highs_list = [c.high for c in filtered]
    lows_list = [c.low for c in filtered]

    # Pre-compute vol_30d for all bars with sufficient data to get vol_median
    vol_history: list[float] = []
    for i in range(len(filtered)):
        if i < VOL_WINDOW:
            regime_map[filtered[i].time] = "UNKNOWN"
            continue

        window_closes = np.array(closes_list[: i + 1], dtype=np.float64)
        try:
            vol_30d = compute_vol_30d(closes=window_closes, annualization_factor=ann_factor)
        except ValueError:
            regime_map[filtered[i].time] = "UNKNOWN"
            continue

        vol_history.append(vol_30d)

        if i < _MIN_REGIME_BARS:
            regime_map[filtered[i].time] = "UNKNOWN"
            continue

        window_highs = np.array(highs_list[: i + 1], dtype=np.float64)
        window_lows = np.array(lows_list[: i + 1], dtype=np.float64)

        try:
            adx_14 = compute_adx_14(
                highs=window_highs, lows=window_lows, closes=window_closes,
            )
        except ValueError:
            regime_map[filtered[i].time] = "UNKNOWN"
            continue

        vol_med = compute_vol_median(vol_history)
        label = classify_regime(vol_30d=vol_30d, adx_14=adx_14, vol_median=vol_med)
        regime_map[filtered[i].time] = label.value

    return regime_map


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

    # Pre-compute indicator features and regime labels
    feature_map = _precompute_features(filtered, config)
    regime_map = _precompute_regimes(filtered, config.instrument)

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
            closed_trade = _check_stop_hit(position, bar, fill_config)
            if closed_trade is not None:
                cash += position.entry_price * position.quantity + closed_trade.pnl
                trades.append(closed_trade)
                completed_trades.append(closed_trade)
                position = None
            else:
                # Evaluate in-trade controls (time stop, trailing stop)
                action = _evaluate_controls(position, bar, risk_config)
                if action.action == "CLOSE":
                    closed_trade = position.close(
                        bar.close, bar.time, _reason_label(action), fill_config,
                    )
                    cash += position.entry_price * position.quantity + closed_trade.pnl
                    trades.append(closed_trade)
                    completed_trades.append(closed_trade)
                    position = None
                elif action.action == "MOVE_STOP" and action.new_stop is not None:
                    position.stop_price = action.new_stop

        # --- 2. Force close at end of data ---
        if is_last_bar and position is not None:
            closed_trade = position.close(bar.close, bar.time, "end_of_data", fill_config)
            cash += position.entry_price * position.quantity + closed_trade.pnl
            trades.append(closed_trade)
            completed_trades.append(closed_trade)
            position = None

        # --- 3. Generate signal and open new position ---
        if not is_last_bar and position is None:
            features = _build_features(bar, config, feature_map)
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
                    regime_confidence=None,
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

                        # Cash guard: skip trade if insufficient cash (SR-M2)
                        if cash < cost_of_entry:
                            pass  # Skip — insufficient cash for this trade
                        else:
                            cash -= cost_of_entry

                            # Regime label for this bar
                            regime_label = regime_map.get(bar.time, "UNKNOWN")

                            position = _OpenPosition(
                                direction=direction,
                                entry_time=fill.fill_time,
                                entry_price=fill.fill_price,
                                quantity=quantity,
                                stop_price=stop_price,
                                commission=fill.commission_cost * quantity,
                                slippage_cost=fill.slippage_cost,
                                spread_cost=fill.spread_cost,
                                regime_label=regime_label,
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


def _build_features(
    bar: CandleRecord,
    config: BacktestConfig,
    feature_map: dict[datetime, dict[str, float]],
) -> FeatureSnapshot:
    """Build a FeatureSnapshot from pre-computed indicator features."""
    values: dict[str, float] = {
        "_open": bar.open,
        "_high": bar.high,
        "_low": bar.low,
        "_close": bar.close,
        "_volume": bar.volume,
    }
    # Merge pre-computed indicator features if available for this timestamp
    precomputed = feature_map.get(bar.time)
    if precomputed:
        values.update(precomputed)

    return FeatureSnapshot(
        instrument=config.instrument,
        interval=config.interval,
        time=bar.time,
        values=values,
        metadata={},
    )


def _check_stop_hit(
    position: _OpenPosition,
    bar: CandleRecord,
    fill_config: FillConfig,
) -> BacktestTrade | None:
    """Check if the bar's price action hits the hard stop."""
    if position.direction == "BUY":
        if bar.low <= position.stop_price:
            return position.close(position.stop_price, bar.time, "hard_stop", fill_config)
    else:
        if bar.high >= position.stop_price:
            return position.close(position.stop_price, bar.time, "hard_stop", fill_config)
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

    win_rate = len(wins) / len(completed)
    avg_win = sum(wins) / len(wins) if wins else 0.0
    avg_loss = sum(losses) / len(losses) if losses else 0.0

    return {
        "win_rate": win_rate,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "num_trades": len(completed),
    }
