"""Order execution orchestrator (SPEC §5.9, §5.11, §6.3, §6.4).

End-to-end trade execution: signal → pre-trade checks → position sizing →
order submission → stop-loss placement → trade record lifecycle.

Uses BrokerAdapter protocol for broker-agnostic order placement and
TradeStore protocol for persistence abstraction.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any, Protocol

from src.analysis.signal_contract import Signal
from src.trading.broker_base import (
    AccountInfo,
    BrokerAdapter,
    Direction,
    OrderNotFoundError,
    OrderResult,
    Position,
    TradeStatus,
    make_client_order_id,
)
from src.trading.circuit_breaker import CircuitBreakerManager
from src.data.schema import RiskPortfolio
from src.trading.risk import (
    InTradeAction,
    ResolvedRiskConfig,
    evaluate_in_trade_controls,
    run_pre_trade_checks,
)

logger = logging.getLogger(__name__)

# Signal actions that map to a BUY direction
_BUY_ACTIONS = {"STRONG_BUY", "BUY"}


# ---------------------------------------------------------------------------
# Domain models — all frozen per DEC-010
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TradeRecord:
    """Internal trade record mirroring the trades table schema (§4.2)."""

    client_order_id: str
    broker_order_id: str | None
    instrument: str
    broker: str
    direction: Direction
    signal_score: float
    signal_type: str
    signal_generator_id: str
    regime_label: str | None
    entry_time: datetime | None
    entry_price: float | None
    exit_time: datetime | None
    exit_price: float | None
    quantity: float
    stop_loss_price: float | None
    status: TradeStatus
    pnl: float | None
    commission: float | None
    slippage: float | None
    exit_reason: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class ExecutionResult:
    """Outcome of an execute_signal call."""

    success: bool
    trade_record: TradeRecord | None
    rejection_reason: str | None


# ---------------------------------------------------------------------------
# TradeStore protocol — persistence abstraction
# ---------------------------------------------------------------------------


class TradeStore(Protocol):
    """Persistence layer for trade records (DEC-005)."""

    def save_trade(self, trade: TradeRecord) -> None: ...

    def update_trade(self, client_order_id: str, **updates: Any) -> TradeRecord: ...

    def get_open_trades(self, instrument: str | None) -> list[TradeRecord]: ...

    def get_trade(self, client_order_id: str) -> TradeRecord | None: ...

    def list_trades(
        self,
        *,
        instrument: str | None = None,
        status: str | None = None,
        broker: str | None = None,
        limit: int = 100,
    ) -> list[TradeRecord]: ...


class InMemoryTradeStore:
    """In-memory implementation of TradeStore for testing."""

    def __init__(self) -> None:
        self._trades: dict[str, TradeRecord] = {}

    def save_trade(self, trade: TradeRecord) -> None:
        self._trades[trade.client_order_id] = trade

    def update_trade(self, client_order_id: str, **updates: Any) -> TradeRecord:
        if client_order_id not in self._trades:
            msg = f"trade not found: {client_order_id}"
            raise KeyError(msg)
        current = self._trades[client_order_id]
        updated = replace(current, updated_at=datetime.now(UTC), **updates)
        self._trades[client_order_id] = updated
        return updated

    def get_open_trades(self, instrument: str | None) -> list[TradeRecord]:
        trades = [t for t in self._trades.values() if t.status == "OPEN"]
        if instrument is not None:
            trades = [t for t in trades if t.instrument == instrument]
        return trades

    def get_trade(self, client_order_id: str) -> TradeRecord | None:
        return self._trades.get(client_order_id)

    def list_trades(
        self,
        *,
        instrument: str | None = None,
        status: str | None = None,
        broker: str | None = None,
        limit: int = 100,
    ) -> list[TradeRecord]:
        trades = list(self._trades.values())
        if instrument is not None:
            trades = [t for t in trades if t.instrument == instrument]
        if status is not None:
            trades = [t for t in trades if t.status == status]
        if broker is not None:
            trades = [t for t in trades if t.broker == broker]
        trades.sort(key=lambda t: t.created_at, reverse=True)
        return trades[:limit]


# ---------------------------------------------------------------------------
# OrderExecutor
# ---------------------------------------------------------------------------


class OrderExecutor:
    """Orchestrates the full trade lifecycle (SPEC §5.9, §5.11).

    Ties together signal evaluation, pre-trade risk checks, broker order
    submission, and in-trade control monitoring.
    """

    def __init__(
        self,
        *,
        broker: BrokerAdapter,
        broker_name: str,
        trade_store: TradeStore,
        circuit_breaker: CircuitBreakerManager,
    ) -> None:
        self._broker = broker
        self._broker_name = broker_name
        self._store = trade_store
        self._circuit_breaker = circuit_breaker

    # ------------------------------------------------------------------
    # Signal execution
    # ------------------------------------------------------------------

    def execute_signal(
        self,
        *,
        signal: Signal,
        risk_config: ResolvedRiskConfig,
        portfolio_config: RiskPortfolio,
        account: AccountInfo,
        open_positions: list[Position],
        last_candle_time: datetime,
        signal_interval_seconds: int,
        last_retrain_days: int | None,
        regime_confidence: float | None,
        win_rate: float,
        avg_win: float,
        avg_loss: float,
        num_trades: int,
        current_price: float | None = None,
    ) -> ExecutionResult:
        """Execute a signal through the full trade lifecycle.

        Steps: validate action → pre-trade checks → dollar→units conversion →
        place order → record trade.

        Args:
            current_price: Latest market price for stop-loss estimation and
                dollar→units conversion. Required for correct position sizing.
        """
        now = datetime.now(UTC)

        # 1. Map signal action to direction
        if signal.action == "NEUTRAL":
            return ExecutionResult(
                success=False, trade_record=None, rejection_reason="neutral_signal",
            )

        direction: Direction = "BUY" if signal.action in _BUY_ACTIONS else "SELL"

        # 2. Generate idempotent client order ID
        client_order_id = make_client_order_id(signal.instrument)

        # 3. Run pre-trade checks
        circuit_breaker_ok = self._circuit_breaker.is_entry_allowed(signal.instrument)

        pre_trade = run_pre_trade_checks(
            instrument=signal.instrument,
            signal_direction=direction,
            account=account,
            open_positions=open_positions,
            risk_config=risk_config,
            portfolio_config=portfolio_config,
            circuit_breaker_ok=circuit_breaker_ok,
            last_candle_time=last_candle_time,
            signal_interval_seconds=signal_interval_seconds,
            last_retrain_days=last_retrain_days,
            regime_confidence=regime_confidence,
            win_rate=win_rate,
            avg_win=avg_win,
            avg_loss=avg_loss,
            num_trades=num_trades,
        )

        if not pre_trade.approved:
            logger.info(
                "Trade rejected for %s: %s", signal.instrument, pre_trade.reason,
            )
            return ExecutionResult(
                success=False, trade_record=None,
                rejection_reason=pre_trade.reason,
            )

        # 4. Check for zero position size (dollar risk)
        if pre_trade.position_size <= 0:
            return ExecutionResult(
                success=False, trade_record=None,
                rejection_reason="zero_position_size",
            )

        # 5. Convert dollar risk to instrument units (§6.3 + §6.4 gap risk)
        price_estimate = current_price or 0.0
        if price_estimate > 0:
            stop_distance = price_estimate * risk_config.hard_stop_pct
            gap_adjusted = stop_distance * risk_config.gap_risk_multiplier
            units = pre_trade.position_size / gap_adjusted if gap_adjusted > 0 else 0.0
        else:
            units = pre_trade.position_size  # Fallback: use raw dollar amount

        if units <= 0:
            return ExecutionResult(
                success=False, trade_record=None,
                rejection_reason="zero_position_size",
            )

        # 6. Compute preliminary stop-loss from current price estimate
        preliminary_stop = self._compute_stop_loss(
            direction=direction,
            entry_estimate=price_estimate,
            risk_config=risk_config,
        ) if price_estimate > 0 else 0.0

        # 7. Save PENDING trade
        regime_label = signal.metadata.get("regime_label")
        pending_trade = TradeRecord(
            client_order_id=client_order_id,
            broker_order_id=None,
            instrument=signal.instrument,
            broker=self._broker_name,
            direction=direction,
            signal_score=signal.probability,
            signal_type=signal.action,
            signal_generator_id=signal.generator_id,
            regime_label=regime_label if isinstance(regime_label, str) else None,
            entry_time=None,
            entry_price=None,
            exit_time=None,
            exit_price=None,
            quantity=units,
            stop_loss_price=None,  # Set after fill
            status="PENDING",
            pnl=None,
            commission=None,
            slippage=None,
            exit_reason=None,
            created_at=now,
            updated_at=now,
        )
        self._store.save_trade(pending_trade)

        # 8. Place order with idempotency check (§5.11)
        order_result = self._place_with_idempotency(
            instrument=signal.instrument,
            direction=direction,
            units=units,
            stop_loss=preliminary_stop,
            client_order_id=client_order_id,
        )

        # 8. Update trade based on order result
        if order_result.success and order_result.fill_price is not None:
            # Compute actual stop from fill price
            actual_stop = self._compute_stop_loss(
                direction=direction,
                entry_estimate=order_result.fill_price,
                risk_config=risk_config,
            )
            updated = self._store.update_trade(
                client_order_id,
                status="OPEN",
                broker_order_id=order_result.order_id,
                entry_time=order_result.timestamp,
                entry_price=order_result.fill_price,
                stop_loss_price=actual_stop,
            )
            logger.info(
                "Trade OPEN %s %s %s @ %.4f (stop %.4f)",
                direction, signal.instrument, client_order_id,
                order_result.fill_price, actual_stop,
            )
            return ExecutionResult(
                success=True, trade_record=updated, rejection_reason=None,
            )

        # Order failed
        updated = self._store.update_trade(
            client_order_id,
            status="REJECTED",
            exit_reason=order_result.error_message or "order_failed",
        )
        logger.warning(
            "Trade REJECTED %s: %s",
            client_order_id, order_result.error_message,
        )
        return ExecutionResult(
            success=False, trade_record=updated, rejection_reason="broker_rejected",
        )

    # ------------------------------------------------------------------
    # In-trade control evaluation
    # ------------------------------------------------------------------

    def evaluate_open_trades(
        self,
        *,
        risk_config: ResolvedRiskConfig,
        current_prices: dict[str, float],
        current_atrs: dict[str, float],
        avg_atrs_30d: dict[str, float],
    ) -> list[tuple[TradeRecord, InTradeAction]]:
        """Evaluate in-trade controls for all open trades (§6.4).

        Returns list of (trade, action) pairs for trades that were evaluated.
        Executes CLOSE and MOVE_STOP actions immediately.
        """
        open_trades = self._store.get_open_trades(None)
        results: list[tuple[TradeRecord, InTradeAction]] = []

        for trade in open_trades:
            inst = trade.instrument
            if inst not in current_prices:
                logger.debug("Skipping %s — no current price", trade.client_order_id)
                continue

            if trade.entry_price is None or trade.entry_time is None:
                continue

            current_price = current_prices[inst]
            current_stop = trade.stop_loss_price or 0.0
            open_hours = (
                (datetime.now(UTC) - trade.entry_time).total_seconds() / 3600
            )
            current_atr = current_atrs.get(inst, 0.0)
            avg_atr = avg_atrs_30d.get(inst, 0.0)

            action = evaluate_in_trade_controls(
                entry_price=trade.entry_price,
                current_price=current_price,
                current_stop=current_stop,
                open_hours=open_hours,
                current_atr=current_atr,
                avg_atr_30d=avg_atr,
                config=risk_config,
                direction=trade.direction,
            )

            if action.action == "CLOSE" and trade.broker_order_id:
                close_result = self._broker.close_position(trade.broker_order_id)
                if close_result.success:
                    exit_price = close_result.fill_price or current_price
                    pnl = self._compute_pnl(
                        trade.direction, trade.entry_price,
                        exit_price, trade.quantity,
                    )
                    self._store.update_trade(
                        trade.client_order_id,
                        status="CLOSED",
                        exit_time=datetime.now(UTC),
                        exit_price=exit_price,
                        pnl=pnl,
                        exit_reason=action.reason,
                    )
                    logger.info(
                        "Trade CLOSED %s: %s (PnL %.2f)",
                        trade.client_order_id, action.reason, pnl,
                    )
                else:
                    logger.error(
                        "Failed to close %s: %s",
                        trade.client_order_id, close_result.error_message,
                    )

            elif action.action == "MOVE_STOP" and action.new_stop is not None:
                if trade.broker_order_id:
                    self._broker.modify_stop_loss(
                        trade.broker_order_id, action.new_stop,
                    )
                    self._store.update_trade(
                        trade.client_order_id,
                        stop_loss_price=action.new_stop,
                    )
                    logger.info(
                        "Stop moved %s → %.4f: %s",
                        trade.client_order_id, action.new_stop, action.reason,
                    )

            results.append((trade, action))

        return results

    # ------------------------------------------------------------------
    # Kill switch — close all positions
    # ------------------------------------------------------------------

    def close_all_positions(self, reason: str) -> list[TradeRecord]:
        """Close all open positions (kill switch scenario).

        Attempts to close every open trade via the broker. Trades that
        fail to close remain OPEN and are logged as errors.
        """
        open_trades = self._store.get_open_trades(None)
        closed: list[TradeRecord] = []

        for trade in open_trades:
            if not trade.broker_order_id:
                continue

            close_result = self._broker.close_position(trade.broker_order_id)
            if close_result.success:
                exit_price = close_result.fill_price
                pnl = None
                if (
                    trade.entry_price is not None
                    and exit_price is not None
                ):
                    pnl = self._compute_pnl(
                        trade.direction, trade.entry_price,
                        exit_price, trade.quantity,
                    )
                updated = self._store.update_trade(
                    trade.client_order_id,
                    status="CLOSED",
                    exit_time=datetime.now(UTC),
                    exit_price=exit_price,
                    pnl=pnl,
                    exit_reason=reason,
                )
                closed.append(updated)
                logger.info(
                    "Kill switch closed %s (PnL %s)",
                    trade.client_order_id, pnl,
                )
            else:
                logger.error(
                    "Kill switch FAILED to close %s: %s",
                    trade.client_order_id, close_result.error_message,
                )

        return closed

    # ------------------------------------------------------------------
    # Idempotent order placement (§5.11)
    # ------------------------------------------------------------------

    def _place_with_idempotency(
        self,
        *,
        instrument: str,
        direction: Direction,
        units: float,
        stop_loss: float,
        client_order_id: str,
    ) -> OrderResult:
        """Place order with idempotency check per §5.11.

        Before placing, check if broker already has a filled order with
        the same client_order_id.
        """
        try:
            existing = self._broker.get_order_status(client_order_id)
            if existing.state == "FILLED":
                logger.info(
                    "Idempotency: order %s already filled @ %s",
                    client_order_id, existing.fill_price,
                )
                return OrderResult(
                    success=True,
                    order_id=existing.broker_order_id,
                    client_order_id=client_order_id,
                    instrument=instrument,
                    direction=direction,
                    units=units,
                    fill_price=existing.fill_price,
                    timestamp=existing.fill_time or datetime.now(UTC),
                    error_message=None,
                )
        except OrderNotFoundError:
            # Order doesn't exist yet — expected for new orders
            pass

        return self._broker.place_market_order(
            instrument, units, stop_loss, client_order_id,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_stop_loss(
        *,
        direction: Direction,
        entry_estimate: float,
        risk_config: ResolvedRiskConfig,
    ) -> float:
        """Compute initial stop-loss price from entry and hard_stop_pct."""
        if direction == "BUY":
            return entry_estimate * (1.0 - risk_config.hard_stop_pct)
        return entry_estimate * (1.0 + risk_config.hard_stop_pct)

    @staticmethod
    def _compute_pnl(
        direction: Direction,
        entry_price: float,
        exit_price: float,
        quantity: float,
    ) -> float:
        """Compute realized PnL for a closed trade."""
        if direction == "BUY":
            return (exit_price - entry_price) * quantity
        return (entry_price - exit_price) * quantity
