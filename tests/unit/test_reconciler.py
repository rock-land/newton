"""Tests for position reconciliation loop (T-507, SPEC §5.12)."""

from __future__ import annotations

from datetime import UTC, datetime
import pytest

from src.trading.broker_base import (
    AccountInfo,
    Direction,
    OrderResult,
    OrderStatus,
    Position,
)
from src.trading.circuit_breaker import CircuitBreakerManager
from src.trading.executor import InMemoryTradeStore, TradeRecord
from src.trading.reconciler import (
    InMemoryReconciliationStore,
    PositionReconciler,
    ReconciliationResult,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 3, 5, 12, 0, 0, tzinfo=UTC)

_ACCOUNT = AccountInfo(
    balance=100_000.0,
    currency="USD",
    unrealized_pnl=0.0,
    margin_used=0.0,
    margin_available=100_000.0,
)


def _make_trade(
    instrument: str = "EUR_USD",
    direction: Direction = "BUY",
    client_order_id: str = "NEWTON-EUR_USD-001",
    broker_order_id: str | None = "broker-001",
    quantity: float = 1000.0,
    status: str = "OPEN",
    broker: str = "oanda",
) -> TradeRecord:
    return TradeRecord(
        client_order_id=client_order_id,
        broker_order_id=broker_order_id,
        instrument=instrument,
        broker=broker,
        direction=direction,
        signal_score=0.75,
        signal_type="BUY",
        signal_generator_id="bayesian_v1",
        regime_label=None,
        entry_time=_NOW,
        entry_price=1.1000,
        exit_time=None,
        exit_price=None,
        quantity=quantity,
        stop_loss_price=1.0780,
        status=status,
        pnl=None,
        commission=None,
        slippage=None,
        exit_reason=None,
        created_at=_NOW,
        updated_at=_NOW,
    )


def _make_position(
    instrument: str = "EUR_USD",
    direction: Direction = "BUY",
    units: float = 1000.0,
    trade_id: str = "broker-001",
) -> Position:
    return Position(
        instrument=instrument,
        direction=direction,
        units=units,
        entry_price=1.1000,
        unrealized_pnl=5.0,
        stop_loss=1.0780,
        trade_id=trade_id,
    )


class FakeBrokerAdapter:
    """Fake broker that returns configurable positions."""

    def __init__(self, positions: list[Position] | None = None) -> None:
        self._positions = positions or []

    def get_candles(self, instrument: str, interval: str,
                    start: datetime, end: datetime) -> list:
        return []

    def get_account(self) -> AccountInfo:
        return _ACCOUNT

    def get_positions(self) -> list[Position]:
        return self._positions

    def place_market_order(self, instrument: str, units: float,
                           stop_loss: float, client_order_id: str) -> OrderResult:
        return OrderResult(
            success=True, order_id="o-1", client_order_id=client_order_id,
            instrument=instrument, direction="BUY", units=units,
            fill_price=1.1, timestamp=_NOW, error_message=None,
        )

    def modify_stop_loss(self, trade_id: str, new_stop: float) -> OrderResult:
        return OrderResult(
            success=True, order_id=trade_id, client_order_id="",
            instrument="", direction="BUY", units=0,
            fill_price=None, timestamp=_NOW, error_message=None,
        )

    def close_position(self, trade_id: str) -> OrderResult:
        return OrderResult(
            success=True, order_id=trade_id, client_order_id="",
            instrument="", direction="BUY", units=0,
            fill_price=1.1, timestamp=_NOW, error_message=None,
        )

    def get_order_status(self, client_order_id: str) -> OrderStatus:
        return OrderStatus(
            client_order_id=client_order_id, broker_order_id=None,
            state="PENDING", fill_price=None, fill_time=None,
        )


def _build_reconciler(
    broker_positions: list[Position] | None = None,
    trades: list[TradeRecord] | None = None,
) -> tuple[PositionReconciler, InMemoryTradeStore, InMemoryReconciliationStore]:
    broker = FakeBrokerAdapter(broker_positions or [])
    trade_store = InMemoryTradeStore()
    for t in (trades or []):
        trade_store.save_trade(t)
    recon_store = InMemoryReconciliationStore()
    cb = CircuitBreakerManager()
    reconciler = PositionReconciler(
        broker=broker,
        broker_name="oanda",
        trade_store=trade_store,
        recon_store=recon_store,
        circuit_breaker=cb,
    )
    return reconciler, trade_store, recon_store


# ---------------------------------------------------------------------------
# ReconciliationResult model tests
# ---------------------------------------------------------------------------


class TestReconciliationResult:
    def test_frozen(self) -> None:
        r = ReconciliationResult(
            checked_at=_NOW, broker="oanda", instrument="EUR_USD",
            status="MATCH", details={}, resolved=False,
        )
        with pytest.raises(AttributeError):
            r.status = "SYSTEM_EXTRA"  # type: ignore[misc]

    def test_fields(self) -> None:
        r = ReconciliationResult(
            checked_at=_NOW, broker="oanda", instrument="EUR_USD",
            status="BROKER_EXTRA", details={"units": 1000}, resolved=False,
        )
        assert r.broker == "oanda"
        assert r.status == "BROKER_EXTRA"
        assert r.details == {"units": 1000}


# ---------------------------------------------------------------------------
# InMemoryReconciliationStore tests
# ---------------------------------------------------------------------------


class TestInMemoryReconciliationStore:
    def test_save_and_get_unresolved(self) -> None:
        store = InMemoryReconciliationStore()
        r = ReconciliationResult(
            checked_at=_NOW, broker="oanda", instrument="EUR_USD",
            status="SYSTEM_EXTRA", details={}, resolved=False,
        )
        store.save_result(r)
        assert len(store.get_unresolved()) == 1

    def test_resolved_excluded(self) -> None:
        store = InMemoryReconciliationStore()
        r = ReconciliationResult(
            checked_at=_NOW, broker="oanda", instrument="EUR_USD",
            status="MATCH", details={}, resolved=True,
        )
        store.save_result(r)
        assert len(store.get_unresolved()) == 0

    def test_mark_resolved(self) -> None:
        store = InMemoryReconciliationStore()
        r = ReconciliationResult(
            checked_at=_NOW, broker="oanda", instrument="EUR_USD",
            status="BROKER_EXTRA", details={}, resolved=False,
        )
        store.save_result(r)
        store.mark_resolved(0)
        assert len(store.get_unresolved()) == 0

    def test_mark_resolved_invalid_index(self) -> None:
        store = InMemoryReconciliationStore()
        with pytest.raises(IndexError):
            store.mark_resolved(99)


# ---------------------------------------------------------------------------
# Reconciliation — MATCH scenarios
# ---------------------------------------------------------------------------


class TestReconcileMatch:
    def test_perfect_match(self) -> None:
        """Broker and internal agree — all MATCH."""
        trade = _make_trade()
        pos = _make_position()
        reconciler, _, recon_store = _build_reconciler(
            broker_positions=[pos], trades=[trade],
        )
        results = reconciler.reconcile()
        assert len(results) == 1
        assert results[0].status == "MATCH"
        assert results[0].instrument == "EUR_USD"

    def test_multiple_instruments_all_match(self) -> None:
        """Multiple instruments all in agreement."""
        t1 = _make_trade(instrument="EUR_USD", client_order_id="c-1",
                         broker_order_id="b-1")
        t2 = _make_trade(instrument="BTC_USD", client_order_id="c-2",
                         broker_order_id="b-2", broker="oanda")
        p1 = _make_position(instrument="EUR_USD", trade_id="b-1")
        p2 = _make_position(instrument="BTC_USD", trade_id="b-2")
        reconciler, _, _ = _build_reconciler(
            broker_positions=[p1, p2], trades=[t1, t2],
        )
        results = reconciler.reconcile()
        statuses = {r.instrument: r.status for r in results}
        assert statuses == {"EUR_USD": "MATCH", "BTC_USD": "MATCH"}

    def test_empty_both_sides(self) -> None:
        """No positions on either side — no results."""
        reconciler, _, _ = _build_reconciler()
        results = reconciler.reconcile()
        assert results == []


# ---------------------------------------------------------------------------
# Reconciliation — SYSTEM_EXTRA scenarios
# ---------------------------------------------------------------------------


class TestReconcileSystemExtra:
    def test_system_extra_marks_trade_closed(self) -> None:
        """Internal trade with no broker position → CLOSED with RECONCILIATION."""
        trade = _make_trade()
        reconciler, trade_store, _ = _build_reconciler(
            broker_positions=[], trades=[trade],
        )
        results = reconciler.reconcile()
        assert len(results) == 1
        assert results[0].status == "SYSTEM_EXTRA"

        # Trade should be marked CLOSED
        updated = trade_store.get_trade("NEWTON-EUR_USD-001")
        assert updated is not None
        assert updated.status == "CLOSED"
        assert updated.exit_reason == "RECONCILIATION"

    def test_system_extra_details_contain_trade_info(self) -> None:
        """SYSTEM_EXTRA details include the orphaned trade's client_order_id."""
        trade = _make_trade()
        reconciler, _, _ = _build_reconciler(
            broker_positions=[], trades=[trade],
        )
        results = reconciler.reconcile()
        assert results[0].details["client_order_id"] == "NEWTON-EUR_USD-001"

    def test_system_extra_only_affects_this_broker(self) -> None:
        """Trades for a different broker are not flagged as SYSTEM_EXTRA."""
        trade_other = _make_trade(broker="binance", client_order_id="c-bin-1")
        trade_this = _make_trade(broker="oanda", client_order_id="c-oan-1")
        pos = _make_position()  # matches trade_this
        reconciler, trade_store, _ = _build_reconciler(
            broker_positions=[pos], trades=[trade_other, trade_this],
        )
        results = reconciler.reconcile()
        # Only the oanda trade should be in results (MATCH)
        # The binance trade is filtered out — not this reconciler's broker
        statuses = [r.status for r in results]
        assert "SYSTEM_EXTRA" not in statuses

        # Binance trade should remain OPEN
        bin_trade = trade_store.get_trade("c-bin-1")
        assert bin_trade is not None
        assert bin_trade.status == "OPEN"


# ---------------------------------------------------------------------------
# Reconciliation — BROKER_EXTRA scenarios
# ---------------------------------------------------------------------------


class TestReconcileBrokerExtra:
    def test_broker_extra_halts_instrument(self) -> None:
        """Broker position with no internal record → halt entries."""
        pos = _make_position(instrument="EUR_USD")
        reconciler, _, _ = _build_reconciler(
            broker_positions=[pos], trades=[],
        )
        results = reconciler.reconcile()
        assert len(results) == 1
        assert results[0].status == "BROKER_EXTRA"
        assert reconciler.is_instrument_halted("EUR_USD")

    def test_broker_extra_does_not_halt_other_instruments(self) -> None:
        """Halting EUR_USD doesn't affect BTC_USD."""
        pos = _make_position(instrument="EUR_USD")
        reconciler, _, _ = _build_reconciler(
            broker_positions=[pos], trades=[],
        )
        reconciler.reconcile()
        assert not reconciler.is_instrument_halted("BTC_USD")

    def test_broker_extra_details_contain_position_info(self) -> None:
        """BROKER_EXTRA details include the broker position's trade_id and units."""
        pos = _make_position(instrument="EUR_USD", units=5000.0, trade_id="b-99")
        reconciler, _, _ = _build_reconciler(
            broker_positions=[pos], trades=[],
        )
        results = reconciler.reconcile()
        assert results[0].details["trade_id"] == "b-99"
        assert results[0].details["units"] == 5000.0

    def test_clear_halt(self) -> None:
        """Manual review done — clear_halt removes the halt."""
        pos = _make_position(instrument="EUR_USD")
        reconciler, _, _ = _build_reconciler(
            broker_positions=[pos], trades=[],
        )
        reconciler.reconcile()
        assert reconciler.is_instrument_halted("EUR_USD")
        reconciler.clear_halt("EUR_USD")
        assert not reconciler.is_instrument_halted("EUR_USD")

    def test_clear_halt_idempotent(self) -> None:
        """Clearing a non-halted instrument is a no-op."""
        reconciler, _, _ = _build_reconciler()
        reconciler.clear_halt("EUR_USD")  # should not raise
        assert not reconciler.is_instrument_halted("EUR_USD")


# ---------------------------------------------------------------------------
# Mixed scenarios
# ---------------------------------------------------------------------------


class TestReconcileMixed:
    def test_match_and_system_extra(self) -> None:
        """One matching, one orphaned internal trade."""
        t1 = _make_trade(instrument="EUR_USD", client_order_id="c-1",
                         broker_order_id="b-1")
        t2 = _make_trade(instrument="BTC_USD", client_order_id="c-2",
                         broker_order_id="b-2", broker="oanda")
        p1 = _make_position(instrument="EUR_USD", trade_id="b-1")
        # No broker position for BTC_USD → SYSTEM_EXTRA
        reconciler, trade_store, _ = _build_reconciler(
            broker_positions=[p1], trades=[t1, t2],
        )
        results = reconciler.reconcile()
        by_inst = {r.instrument: r.status for r in results}
        assert by_inst["EUR_USD"] == "MATCH"
        assert by_inst["BTC_USD"] == "SYSTEM_EXTRA"

    def test_match_and_broker_extra(self) -> None:
        """One matching, one unknown broker position."""
        trade = _make_trade(instrument="EUR_USD", client_order_id="c-1",
                            broker_order_id="b-1")
        p1 = _make_position(instrument="EUR_USD", trade_id="b-1")
        p2 = _make_position(instrument="BTC_USD", trade_id="b-99")
        reconciler, _, _ = _build_reconciler(
            broker_positions=[p1, p2], trades=[trade],
        )
        results = reconciler.reconcile()
        by_inst = {r.instrument: r.status for r in results}
        assert by_inst["EUR_USD"] == "MATCH"
        assert by_inst["BTC_USD"] == "BROKER_EXTRA"

    def test_results_saved_to_recon_store(self) -> None:
        """All reconciliation results are persisted."""
        trade = _make_trade()
        pos = _make_position()
        reconciler, _, recon_store = _build_reconciler(
            broker_positions=[pos], trades=[trade],
        )
        reconciler.reconcile()
        # MATCH results are saved as resolved=True
        # All results should be in the store
        assert len(recon_store._results) == 1

    def test_same_instrument_different_direction(self) -> None:
        """BUY and SELL on same instrument are tracked separately."""
        t_buy = _make_trade(instrument="EUR_USD", direction="BUY",
                            client_order_id="c-buy", broker_order_id="b-buy")
        t_sell = _make_trade(instrument="EUR_USD", direction="SELL",
                             client_order_id="c-sell", broker_order_id="b-sell")
        p_buy = _make_position(instrument="EUR_USD", direction="BUY",
                               trade_id="b-buy")
        # No SELL position on broker → SYSTEM_EXTRA for the sell trade
        reconciler, trade_store, _ = _build_reconciler(
            broker_positions=[p_buy], trades=[t_buy, t_sell],
        )
        results = reconciler.reconcile()
        statuses = {(r.instrument, r.details.get("direction", "")): r.status
                    for r in results}
        assert statuses[("EUR_USD", "BUY")] == "MATCH"
        assert statuses[("EUR_USD", "SELL")] == "SYSTEM_EXTRA"

        sell_trade = trade_store.get_trade("c-sell")
        assert sell_trade is not None
        assert sell_trade.status == "CLOSED"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestReconcileEdgeCases:
    def test_non_open_trades_excluded(self) -> None:
        """Only OPEN trades are considered for reconciliation."""
        closed_trade = _make_trade(status="CLOSED", client_order_id="c-closed")
        pos = _make_position()  # No matching OPEN trade
        reconciler, _, _ = _build_reconciler(
            broker_positions=[pos], trades=[closed_trade],
        )
        results = reconciler.reconcile()
        assert len(results) == 1
        assert results[0].status == "BROKER_EXTRA"

    def test_broker_get_positions_exception(self) -> None:
        """If broker.get_positions() raises, reconcile returns empty + logs."""
        reconciler, _, _ = _build_reconciler()
        # Monkey-patch to raise
        reconciler._broker.get_positions = lambda: (_ for _ in ()).throw(  # type: ignore[assignment]
            ConnectionError("broker unreachable"),
        )
        results = reconciler.reconcile()
        assert results == []

    def test_trade_without_broker_order_id_excluded(self) -> None:
        """OPEN trades without broker_order_id are skipped."""
        trade = _make_trade(broker_order_id=None, client_order_id="c-pending")
        reconciler, trade_store, _ = _build_reconciler(
            broker_positions=[], trades=[trade],
        )
        results = reconciler.reconcile()
        # Should not produce SYSTEM_EXTRA — trade has no broker_order_id
        assert all(r.status != "SYSTEM_EXTRA" for r in results)
        # Trade remains OPEN
        t = trade_store.get_trade("c-pending")
        assert t is not None
        assert t.status == "OPEN"
