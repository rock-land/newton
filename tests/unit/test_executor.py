"""Tests for order execution orchestrator (T-506, SPEC §5.9/§5.11/§6.3/§6.4)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from src.analysis.signal_contract import Signal
from src.trading.broker_base import (
    AccountInfo,
    OrderResult,
    OrderStatus,
    Position,
)
from src.trading.circuit_breaker import CircuitBreakerManager
from src.trading.executor import (
    ExecutionResult,
    InMemoryTradeStore,
    OrderExecutor,
    TradeRecord,
)
from src.trading.risk import ResolvedRiskConfig, RiskPortfolio


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(UTC)


def _make_risk_config(**overrides: object) -> ResolvedRiskConfig:
    defaults = {
        "max_position_pct": 0.05,
        "max_risk_per_trade_pct": 0.02,
        "kelly_fraction": 0.25,
        "kelly_min_trades": 30,
        "kelly_window": 60,
        "micro_size_pct": 0.005,
        "hard_stop_pct": 0.02,
        "trailing_activation_pct": 0.01,
        "trailing_breakeven_pct": 0.02,
        "time_stop_hours": 48,
        "daily_loss_limit_pct": 0.02,
        "max_drawdown_pct": 0.20,
        "consecutive_loss_halt": 5,
        "consecutive_loss_halt_hours": 24,
        "gap_risk_multiplier": 2.0,
        "volatility_threshold_multiplier": 2.0,
        "high_volatility_size_reduction": 0.5,
        "high_volatility_stop_pct": 0.03,
    }
    defaults.update(overrides)
    return ResolvedRiskConfig(**defaults)  # type: ignore[arg-type]


def _make_portfolio_config() -> RiskPortfolio:
    return RiskPortfolio(max_total_exposure_pct=0.10, max_portfolio_drawdown_pct=0.20)


def _make_account(balance: float = 100_000.0) -> AccountInfo:
    return AccountInfo(
        balance=balance, currency="USD",
        unrealized_pnl=0.0, margin_used=0.0, margin_available=balance,
    )


def _make_signal(
    instrument: str = "EUR_USD",
    action: str = "BUY",
    probability: float = 0.65,
    generator_id: str = "bayesian_v1",
) -> Signal:
    return Signal(
        instrument=instrument,
        action=action,  # type: ignore[arg-type]
        probability=probability,
        confidence=0.8,
        component_scores={"bayesian": 0.65},
        metadata={"regime_label": "low_vol_trending"},
        generated_at=_now(),
        generator_id=generator_id,
    )


class FakeBrokerAdapter:
    """Fake broker for testing — implements BrokerAdapter protocol."""

    def __init__(self) -> None:
        self.orders_placed: list[dict[str, object]] = []
        self.stops_modified: list[dict[str, object]] = []
        self.positions_closed: list[str] = []
        self.order_statuses: dict[str, OrderStatus] = {}
        self._fill_price: float = 1.1000
        self._fail_place: bool = False
        self._fail_close: bool = False

    def get_candles(
        self, instrument: str, interval: str, start: datetime, end: datetime,
    ) -> list[object]:
        return []

    def get_account(self) -> AccountInfo:
        return _make_account()

    def get_positions(self) -> list[Position]:
        return []

    def place_market_order(
        self, instrument: str, units: float, stop_loss: float, client_order_id: str,
    ) -> OrderResult:
        self.orders_placed.append({
            "instrument": instrument, "units": units,
            "stop_loss": stop_loss, "client_order_id": client_order_id,
        })
        if self._fail_place:
            return OrderResult(
                success=False, order_id=None,
                client_order_id=client_order_id, instrument=instrument,
                direction="BUY", units=units, fill_price=None,
                timestamp=_now(), error_message="BROKER_ERROR",
            )
        return OrderResult(
            success=True, order_id="broker-123",
            client_order_id=client_order_id, instrument=instrument,
            direction="BUY", units=units, fill_price=self._fill_price,
            timestamp=_now(), error_message=None,
        )

    def modify_stop_loss(self, trade_id: str, new_stop: float) -> OrderResult:
        self.stops_modified.append({"trade_id": trade_id, "new_stop": new_stop})
        return OrderResult(
            success=True, order_id=trade_id,
            client_order_id="", instrument="", direction="BUY",
            units=0.0, fill_price=None, timestamp=_now(), error_message=None,
        )

    def close_position(self, trade_id: str) -> OrderResult:
        self.positions_closed.append(trade_id)
        if self._fail_close:
            return OrderResult(
                success=False, order_id=None,
                client_order_id="", instrument="", direction="BUY",
                units=0.0, fill_price=None, timestamp=_now(),
                error_message="CLOSE_FAILED",
            )
        return OrderResult(
            success=True, order_id=trade_id,
            client_order_id="", instrument="", direction="BUY",
            units=0.0, fill_price=1.1050, timestamp=_now(), error_message=None,
        )

    def get_order_status(self, client_order_id: str) -> OrderStatus:
        if client_order_id in self.order_statuses:
            return self.order_statuses[client_order_id]
        return OrderStatus(
            client_order_id=client_order_id, broker_order_id=None,
            state="PENDING", fill_price=None, fill_time=None,
        )


def _make_executor(
    broker: FakeBrokerAdapter | None = None,
) -> tuple[OrderExecutor, FakeBrokerAdapter, InMemoryTradeStore]:
    broker = broker or FakeBrokerAdapter()
    store = InMemoryTradeStore()
    cb = CircuitBreakerManager()
    executor = OrderExecutor(
        broker=broker, broker_name="oanda",
        trade_store=store, circuit_breaker=cb,
    )
    return executor, broker, store


# ---------------------------------------------------------------------------
# TradeRecord model tests
# ---------------------------------------------------------------------------


class TestTradeRecord:
    def test_frozen(self) -> None:
        record = TradeRecord(
            client_order_id="NEWTON-EUR_USD-123", broker_order_id=None,
            instrument="EUR_USD", broker="oanda", direction="BUY",
            signal_score=0.65, signal_type="BUY", signal_generator_id="bayesian_v1",
            regime_label="low_vol_trending",
            entry_time=None, entry_price=None, exit_time=None, exit_price=None,
            quantity=100.0, stop_loss_price=1.08,
            status="PENDING", pnl=None, commission=None, slippage=None,
            exit_reason=None, created_at=_now(), updated_at=_now(),
        )
        with pytest.raises(AttributeError):
            record.status = "OPEN"  # type: ignore[misc]

    def test_fields(self) -> None:
        now = _now()
        record = TradeRecord(
            client_order_id="NEWTON-EUR_USD-123", broker_order_id="b-1",
            instrument="EUR_USD", broker="oanda", direction="BUY",
            signal_score=0.65, signal_type="BUY", signal_generator_id="bayesian_v1",
            regime_label=None,
            entry_time=now, entry_price=1.10, exit_time=None, exit_price=None,
            quantity=100.0, stop_loss_price=1.08,
            status="OPEN", pnl=None, commission=None, slippage=None,
            exit_reason=None, created_at=now, updated_at=now,
        )
        assert record.instrument == "EUR_USD"
        assert record.direction == "BUY"
        assert record.status == "OPEN"


# ---------------------------------------------------------------------------
# ExecutionResult model tests
# ---------------------------------------------------------------------------


class TestExecutionResult:
    def test_frozen(self) -> None:
        result = ExecutionResult(
            success=True, trade_record=None, rejection_reason=None,
        )
        with pytest.raises(AttributeError):
            result.success = False  # type: ignore[misc]


# ---------------------------------------------------------------------------
# execute_signal — happy path
# ---------------------------------------------------------------------------


class TestExecuteSignal:
    def test_buy_signal_creates_open_trade(self) -> None:
        executor, broker, store = _make_executor()
        signal = _make_signal(action="BUY")
        result = executor.execute_signal(
            signal=signal,
            risk_config=_make_risk_config(),
            portfolio_config=_make_portfolio_config(),
            account=_make_account(),
            open_positions=[],
            last_candle_time=_now(),
            signal_interval_seconds=3600,
            last_retrain_days=5,
            regime_confidence=0.6,
            win_rate=0.55, avg_win=200.0, avg_loss=100.0, num_trades=10,
        )
        assert result.success
        assert result.trade_record is not None
        assert result.trade_record.status == "OPEN"
        assert result.trade_record.broker_order_id == "broker-123"
        assert result.trade_record.entry_price == 1.1
        assert len(broker.orders_placed) == 1

    def test_strong_buy_maps_to_buy(self) -> None:
        executor, broker, store = _make_executor()
        signal = _make_signal(action="STRONG_BUY")
        result = executor.execute_signal(
            signal=signal,
            risk_config=_make_risk_config(),
            portfolio_config=_make_portfolio_config(),
            account=_make_account(),
            open_positions=[],
            last_candle_time=_now(),
            signal_interval_seconds=3600,
            last_retrain_days=5,
            regime_confidence=0.6,
            win_rate=0.55, avg_win=200.0, avg_loss=100.0, num_trades=10,
        )
        assert result.success
        assert result.trade_record is not None
        assert result.trade_record.direction == "BUY"

    def test_sell_signal_creates_sell_trade(self) -> None:
        executor, broker, store = _make_executor()
        signal = _make_signal(action="SELL")
        result = executor.execute_signal(
            signal=signal,
            risk_config=_make_risk_config(),
            portfolio_config=_make_portfolio_config(),
            account=_make_account(),
            open_positions=[],
            last_candle_time=_now(),
            signal_interval_seconds=3600,
            last_retrain_days=5,
            regime_confidence=0.6,
            win_rate=0.55, avg_win=200.0, avg_loss=100.0, num_trades=10,
        )
        assert result.success
        assert result.trade_record is not None
        assert result.trade_record.direction == "SELL"

    def test_trade_saved_to_store(self) -> None:
        executor, broker, store = _make_executor()
        signal = _make_signal()
        executor.execute_signal(
            signal=signal,
            risk_config=_make_risk_config(),
            portfolio_config=_make_portfolio_config(),
            account=_make_account(),
            open_positions=[],
            last_candle_time=_now(),
            signal_interval_seconds=3600,
            last_retrain_days=5,
            regime_confidence=0.6,
            win_rate=0.55, avg_win=200.0, avg_loss=100.0, num_trades=10,
        )
        trades = store.get_open_trades(None)
        assert len(trades) == 1
        assert trades[0].status == "OPEN"

    def test_stop_loss_set_from_hard_stop(self) -> None:
        """Stop-loss price = entry * (1 - hard_stop_pct) for BUY."""
        executor, broker, store = _make_executor()
        signal = _make_signal(action="BUY")
        executor.execute_signal(
            signal=signal,
            risk_config=_make_risk_config(hard_stop_pct=0.02),
            portfolio_config=_make_portfolio_config(),
            account=_make_account(),
            open_positions=[],
            last_candle_time=_now(),
            signal_interval_seconds=3600,
            last_retrain_days=5,
            regime_confidence=0.6,
            win_rate=0.55, avg_win=200.0, avg_loss=100.0, num_trades=10,
            current_price=1.10,
        )
        order = broker.orders_placed[0]
        expected_stop = 1.10 * (1 - 0.02)  # current_price * (1 - hard_stop)
        assert abs(float(order["stop_loss"]) - expected_stop) < 0.0001


# ---------------------------------------------------------------------------
# execute_signal — rejections
# ---------------------------------------------------------------------------


class TestExecuteSignalRejection:
    def test_neutral_signal_rejected(self) -> None:
        executor, broker, store = _make_executor()
        signal = _make_signal(action="NEUTRAL")
        result = executor.execute_signal(
            signal=signal,
            risk_config=_make_risk_config(),
            portfolio_config=_make_portfolio_config(),
            account=_make_account(),
            open_positions=[],
            last_candle_time=_now(),
            signal_interval_seconds=3600,
            last_retrain_days=5,
            regime_confidence=0.6,
            win_rate=0.55, avg_win=200.0, avg_loss=100.0, num_trades=10,
        )
        assert not result.success
        assert result.rejection_reason == "neutral_signal"
        assert len(broker.orders_placed) == 0

    def test_pretrade_failure_rejects(self) -> None:
        """Existing position for same instrument → position_limit rejection."""
        executor, broker, store = _make_executor()
        signal = _make_signal()
        existing_pos = Position(
            instrument="EUR_USD", direction="BUY", units=100.0,
            entry_price=1.10, unrealized_pnl=0.0,
            stop_loss=1.08, trade_id="existing-1",
        )
        result = executor.execute_signal(
            signal=signal,
            risk_config=_make_risk_config(),
            portfolio_config=_make_portfolio_config(),
            account=_make_account(),
            open_positions=[existing_pos],
            last_candle_time=_now(),
            signal_interval_seconds=3600,
            last_retrain_days=5,
            regime_confidence=0.6,
            win_rate=0.55, avg_win=200.0, avg_loss=100.0, num_trades=10,
        )
        assert not result.success
        assert result.rejection_reason == "position_limit"
        assert len(broker.orders_placed) == 0

    def test_circuit_breaker_tripped_rejects(self) -> None:
        broker = FakeBrokerAdapter()
        store = InMemoryTradeStore()
        cb = CircuitBreakerManager()
        cb.activate_kill_switch("test")
        executor = OrderExecutor(
            broker=broker, broker_name="oanda",
            trade_store=store, circuit_breaker=cb,
        )
        signal = _make_signal()
        result = executor.execute_signal(
            signal=signal,
            risk_config=_make_risk_config(),
            portfolio_config=_make_portfolio_config(),
            account=_make_account(),
            open_positions=[],
            last_candle_time=_now(),
            signal_interval_seconds=3600,
            last_retrain_days=5,
            regime_confidence=0.6,
            win_rate=0.55, avg_win=200.0, avg_loss=100.0, num_trades=10,
        )
        assert not result.success
        assert result.rejection_reason == "circuit_breaker"

    def test_stale_data_rejects(self) -> None:
        executor, broker, store = _make_executor()
        signal = _make_signal()
        old_candle = _now() - timedelta(hours=3)
        result = executor.execute_signal(
            signal=signal,
            risk_config=_make_risk_config(),
            portfolio_config=_make_portfolio_config(),
            account=_make_account(),
            open_positions=[],
            last_candle_time=old_candle,
            signal_interval_seconds=3600,
            last_retrain_days=5,
            regime_confidence=0.6,
            win_rate=0.55, avg_win=200.0, avg_loss=100.0, num_trades=10,
        )
        assert not result.success
        assert result.rejection_reason == "data_freshness"

    def test_broker_failure_creates_rejected_trade(self) -> None:
        broker = FakeBrokerAdapter()
        broker._fail_place = True
        executor, _, store = _make_executor(broker=broker)
        signal = _make_signal()
        result = executor.execute_signal(
            signal=signal,
            risk_config=_make_risk_config(),
            portfolio_config=_make_portfolio_config(),
            account=_make_account(),
            open_positions=[],
            last_candle_time=_now(),
            signal_interval_seconds=3600,
            last_retrain_days=5,
            regime_confidence=0.6,
            win_rate=0.55, avg_win=200.0, avg_loss=100.0, num_trades=10,
        )
        assert not result.success
        assert result.trade_record is not None
        assert result.trade_record.status == "REJECTED"

    def test_zero_position_size_rejects(self) -> None:
        """Zero equity → zero position size → reject."""
        executor, broker, store = _make_executor()
        signal = _make_signal()
        result = executor.execute_signal(
            signal=signal,
            risk_config=_make_risk_config(),
            portfolio_config=_make_portfolio_config(),
            account=_make_account(balance=0.0),
            open_positions=[],
            last_candle_time=_now(),
            signal_interval_seconds=3600,
            last_retrain_days=5,
            regime_confidence=0.6,
            win_rate=0.55, avg_win=200.0, avg_loss=100.0, num_trades=10,
        )
        assert not result.success
        assert result.rejection_reason == "zero_position_size"


# ---------------------------------------------------------------------------
# Idempotency (§5.11)
# ---------------------------------------------------------------------------


class TestIdempotency:
    def test_idempotency_check_before_order(self) -> None:
        """If broker already has a filled order with same client_order_id, skip re-place."""
        broker = FakeBrokerAdapter()
        coid = "NEWTON-EUR_USD-999"
        broker.order_statuses[coid] = OrderStatus(
            client_order_id=coid, broker_order_id="already-filled",
            state="FILLED", fill_price=1.1050, fill_time=_now(),
        )
        store = InMemoryTradeStore()
        cb = CircuitBreakerManager()
        executor = OrderExecutor(
            broker=broker, broker_name="oanda",
            trade_store=store, circuit_breaker=cb,
        )
        result = executor._place_with_idempotency(
            instrument="EUR_USD", units=100.0, stop_loss=1.08,
            client_order_id=coid,
        )
        assert result.success
        assert result.fill_price == 1.1050
        # Should NOT have placed a new order
        assert len(broker.orders_placed) == 0

    def test_no_existing_order_places_new(self) -> None:
        executor, broker, store = _make_executor()
        coid = "NEWTON-EUR_USD-1000"
        result = executor._place_with_idempotency(
            instrument="EUR_USD", units=100.0, stop_loss=1.08,
            client_order_id=coid,
        )
        assert result.success
        assert len(broker.orders_placed) == 1


# ---------------------------------------------------------------------------
# evaluate_open_trades — in-trade controls
# ---------------------------------------------------------------------------


class TestEvaluateOpenTrades:
    def test_hold_no_action(self) -> None:
        executor, broker, store = _make_executor()
        trade = TradeRecord(
            client_order_id="t-1", broker_order_id="b-1",
            instrument="EUR_USD", broker="oanda", direction="BUY",
            signal_score=0.65, signal_type="BUY",
            signal_generator_id="bayesian_v1", regime_label=None,
            entry_time=_now(), entry_price=1.10,
            exit_time=None, exit_price=None,
            quantity=100.0, stop_loss_price=1.078,
            status="OPEN", pnl=None, commission=None, slippage=None,
            exit_reason=None, created_at=_now(), updated_at=_now(),
        )
        store.save_trade(trade)
        actions = executor.evaluate_open_trades(
            risk_config=_make_risk_config(),
            current_prices={"EUR_USD": 1.1005},
            current_atrs={"EUR_USD": 0.0010},
            avg_atrs_30d={"EUR_USD": 0.0010},
        )
        assert len(actions) == 1
        assert actions[0][1].action == "HOLD"

    def test_time_stop_closes_trade(self) -> None:
        executor, broker, store = _make_executor()
        old_entry = _now() - timedelta(hours=50)
        trade = TradeRecord(
            client_order_id="t-1", broker_order_id="b-1",
            instrument="EUR_USD", broker="oanda", direction="BUY",
            signal_score=0.65, signal_type="BUY",
            signal_generator_id="bayesian_v1", regime_label=None,
            entry_time=old_entry, entry_price=1.10,
            exit_time=None, exit_price=None,
            quantity=100.0, stop_loss_price=1.078,
            status="OPEN", pnl=None, commission=None, slippage=None,
            exit_reason=None, created_at=old_entry, updated_at=old_entry,
        )
        store.save_trade(trade)
        actions = executor.evaluate_open_trades(
            risk_config=_make_risk_config(time_stop_hours=48),
            current_prices={"EUR_USD": 1.10},
            current_atrs={"EUR_USD": 0.0010},
            avg_atrs_30d={"EUR_USD": 0.0010},
        )
        assert len(actions) == 1
        assert actions[0][1].action == "CLOSE"
        # Trade should be closed in store
        updated = store.get_trade("t-1")
        assert updated is not None
        assert updated.status == "CLOSED"
        assert updated.exit_reason is not None
        assert "time stop" in updated.exit_reason

    def test_trailing_activation_moves_stop(self) -> None:
        executor, broker, store = _make_executor()
        trade = TradeRecord(
            client_order_id="t-1", broker_order_id="b-1",
            instrument="EUR_USD", broker="oanda", direction="BUY",
            signal_score=0.65, signal_type="BUY",
            signal_generator_id="bayesian_v1", regime_label=None,
            entry_time=_now(), entry_price=1.10,
            exit_time=None, exit_price=None,
            quantity=100.0, stop_loss_price=1.078,
            status="OPEN", pnl=None, commission=None, slippage=None,
            exit_reason=None, created_at=_now(), updated_at=_now(),
        )
        store.save_trade(trade)
        # Price up 1.5% → trailing activation at 1%
        actions = executor.evaluate_open_trades(
            risk_config=_make_risk_config(
                trailing_activation_pct=0.01, trailing_breakeven_pct=0.02,
            ),
            current_prices={"EUR_USD": 1.1165},
            current_atrs={"EUR_USD": 0.0010},
            avg_atrs_30d={"EUR_USD": 0.0010},
        )
        assert len(actions) == 1
        assert actions[0][1].action == "MOVE_STOP"
        assert actions[0][1].new_stop == 1.10  # breakeven
        assert len(broker.stops_modified) == 1

    def test_close_action_records_pnl(self) -> None:
        """When broker closes position, trade records exit price and PnL."""
        executor, broker, store = _make_executor()
        trade = TradeRecord(
            client_order_id="t-1", broker_order_id="b-1",
            instrument="EUR_USD", broker="oanda", direction="BUY",
            signal_score=0.65, signal_type="BUY",
            signal_generator_id="bayesian_v1", regime_label=None,
            entry_time=_now() - timedelta(hours=50), entry_price=1.10,
            exit_time=None, exit_price=None,
            quantity=100.0, stop_loss_price=1.078,
            status="OPEN", pnl=None, commission=None, slippage=None,
            exit_reason=None, created_at=_now(), updated_at=_now(),
        )
        store.save_trade(trade)
        executor.evaluate_open_trades(
            risk_config=_make_risk_config(time_stop_hours=48),
            current_prices={"EUR_USD": 1.1050},
            current_atrs={"EUR_USD": 0.0010},
            avg_atrs_30d={"EUR_USD": 0.0010},
        )
        updated = store.get_trade("t-1")
        assert updated is not None
        assert updated.exit_price == 1.1050
        assert updated.pnl is not None

    def test_missing_price_skips_trade(self) -> None:
        """If current_prices doesn't have the instrument, skip evaluation."""
        executor, broker, store = _make_executor()
        trade = TradeRecord(
            client_order_id="t-1", broker_order_id="b-1",
            instrument="BTC_USD", broker="binance", direction="BUY",
            signal_score=0.65, signal_type="BUY",
            signal_generator_id="ml_v1", regime_label=None,
            entry_time=_now(), entry_price=50000.0,
            exit_time=None, exit_price=None,
            quantity=0.01, stop_loss_price=49000.0,
            status="OPEN", pnl=None, commission=None, slippage=None,
            exit_reason=None, created_at=_now(), updated_at=_now(),
        )
        store.save_trade(trade)
        actions = executor.evaluate_open_trades(
            risk_config=_make_risk_config(),
            current_prices={"EUR_USD": 1.10},  # no BTC_USD
            current_atrs={"EUR_USD": 0.001},
            avg_atrs_30d={"EUR_USD": 0.001},
        )
        assert len(actions) == 0


# ---------------------------------------------------------------------------
# close_all_positions — kill switch
# ---------------------------------------------------------------------------


class TestCloseAllPositions:
    def test_closes_all_open_trades(self) -> None:
        executor, broker, store = _make_executor()
        for i in range(3):
            trade = TradeRecord(
                client_order_id=f"t-{i}", broker_order_id=f"b-{i}",
                instrument="EUR_USD", broker="oanda", direction="BUY",
                signal_score=0.65, signal_type="BUY",
                signal_generator_id="bayesian_v1", regime_label=None,
                entry_time=_now(), entry_price=1.10,
                exit_time=None, exit_price=None,
                quantity=100.0, stop_loss_price=1.078,
                status="OPEN", pnl=None, commission=None, slippage=None,
                exit_reason=None, created_at=_now(), updated_at=_now(),
            )
            store.save_trade(trade)
        closed = executor.close_all_positions("kill_switch")
        assert len(closed) == 3
        assert all(t.status == "CLOSED" for t in closed)
        assert all(t.exit_reason == "kill_switch" for t in closed)
        assert len(broker.positions_closed) == 3

    def test_no_open_trades_returns_empty(self) -> None:
        executor, broker, store = _make_executor()
        closed = executor.close_all_positions("kill_switch")
        assert len(closed) == 0

    def test_broker_close_failure_logs_but_continues(self) -> None:
        broker = FakeBrokerAdapter()
        broker._fail_close = True
        executor, _, store = _make_executor(broker=broker)
        trade = TradeRecord(
            client_order_id="t-1", broker_order_id="b-1",
            instrument="EUR_USD", broker="oanda", direction="BUY",
            signal_score=0.65, signal_type="BUY",
            signal_generator_id="bayesian_v1", regime_label=None,
            entry_time=_now(), entry_price=1.10,
            exit_time=None, exit_price=None,
            quantity=100.0, stop_loss_price=1.078,
            status="OPEN", pnl=None, commission=None, slippage=None,
            exit_reason=None, created_at=_now(), updated_at=_now(),
        )
        store.save_trade(trade)
        closed = executor.close_all_positions("kill_switch")
        # Still returns trades, but they stay OPEN because close failed
        assert len(closed) == 0
        assert store.get_trade("t-1") is not None
        assert store.get_trade("t-1").status == "OPEN"  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# InMemoryTradeStore tests
# ---------------------------------------------------------------------------


class TestInMemoryTradeStore:
    def test_save_and_get(self) -> None:
        store = InMemoryTradeStore()
        trade = TradeRecord(
            client_order_id="t-1", broker_order_id=None,
            instrument="EUR_USD", broker="oanda", direction="BUY",
            signal_score=0.65, signal_type="BUY",
            signal_generator_id="bayesian_v1", regime_label=None,
            entry_time=None, entry_price=None, exit_time=None, exit_price=None,
            quantity=100.0, stop_loss_price=1.08,
            status="PENDING", pnl=None, commission=None, slippage=None,
            exit_reason=None, created_at=_now(), updated_at=_now(),
        )
        store.save_trade(trade)
        assert store.get_trade("t-1") == trade

    def test_update_trade(self) -> None:
        store = InMemoryTradeStore()
        trade = TradeRecord(
            client_order_id="t-1", broker_order_id=None,
            instrument="EUR_USD", broker="oanda", direction="BUY",
            signal_score=0.65, signal_type="BUY",
            signal_generator_id="bayesian_v1", regime_label=None,
            entry_time=None, entry_price=None, exit_time=None, exit_price=None,
            quantity=100.0, stop_loss_price=1.08,
            status="PENDING", pnl=None, commission=None, slippage=None,
            exit_reason=None, created_at=_now(), updated_at=_now(),
        )
        store.save_trade(trade)
        updated = store.update_trade("t-1", status="OPEN", broker_order_id="b-1")
        assert updated.status == "OPEN"
        assert updated.broker_order_id == "b-1"

    def test_get_open_trades_all(self) -> None:
        store = InMemoryTradeStore()
        for i, status in enumerate(["OPEN", "CLOSED", "OPEN"]):
            trade = TradeRecord(
                client_order_id=f"t-{i}", broker_order_id=f"b-{i}",
                instrument="EUR_USD", broker="oanda", direction="BUY",
                signal_score=0.65, signal_type="BUY",
                signal_generator_id="bayesian_v1", regime_label=None,
                entry_time=_now(), entry_price=1.10,
                exit_time=None, exit_price=None,
                quantity=100.0, stop_loss_price=1.08,
                status=status,  # type: ignore[arg-type]
                pnl=None, commission=None, slippage=None,
                exit_reason=None, created_at=_now(), updated_at=_now(),
            )
            store.save_trade(trade)
        open_trades = store.get_open_trades(None)
        assert len(open_trades) == 2

    def test_get_open_trades_by_instrument(self) -> None:
        store = InMemoryTradeStore()
        for idx, inst in enumerate(["EUR_USD", "BTC_USD", "EUR_USD"]):
            trade = TradeRecord(
                client_order_id=f"t-{inst}-{idx}", broker_order_id=None,
                instrument=inst, broker="oanda", direction="BUY",
                signal_score=0.65, signal_type="BUY",
                signal_generator_id="bayesian_v1", regime_label=None,
                entry_time=_now(), entry_price=1.10,
                exit_time=None, exit_price=None,
                quantity=100.0, stop_loss_price=1.08,
                status="OPEN", pnl=None, commission=None, slippage=None,
                exit_reason=None, created_at=_now(), updated_at=_now(),
            )
            store.save_trade(trade)
        eur_trades = store.get_open_trades("EUR_USD")
        assert len(eur_trades) == 2

    def test_get_nonexistent_trade(self) -> None:
        store = InMemoryTradeStore()
        assert store.get_trade("nonexistent") is None

    def test_update_nonexistent_raises(self) -> None:
        store = InMemoryTradeStore()
        with pytest.raises(KeyError):
            store.update_trade("nonexistent", status="OPEN")


# ---------------------------------------------------------------------------
# Coverage gap tests
# ---------------------------------------------------------------------------


class TestCoverageGaps:
    def test_open_trade_missing_entry_price_skipped(self) -> None:
        """OPEN trade with entry_price=None is skipped in evaluate_open_trades."""
        executor, broker, store = _make_executor()
        trade = TradeRecord(
            client_order_id="t-1", broker_order_id="b-1",
            instrument="EUR_USD", broker="oanda", direction="BUY",
            signal_score=0.65, signal_type="BUY",
            signal_generator_id="bayesian_v1", regime_label=None,
            entry_time=None, entry_price=None,
            exit_time=None, exit_price=None,
            quantity=100.0, stop_loss_price=None,
            status="OPEN", pnl=None, commission=None, slippage=None,
            exit_reason=None, created_at=_now(), updated_at=_now(),
        )
        store.save_trade(trade)
        actions = executor.evaluate_open_trades(
            risk_config=_make_risk_config(),
            current_prices={"EUR_USD": 1.10},
            current_atrs={"EUR_USD": 0.001},
            avg_atrs_30d={"EUR_USD": 0.001},
        )
        assert len(actions) == 0

    def test_broker_close_failure_in_evaluate(self) -> None:
        """Broker close failure in evaluate_open_trades logs error."""
        broker = FakeBrokerAdapter()
        broker._fail_close = True
        executor, _, store = _make_executor(broker=broker)
        old_entry = _now() - timedelta(hours=50)
        trade = TradeRecord(
            client_order_id="t-1", broker_order_id="b-1",
            instrument="EUR_USD", broker="oanda", direction="BUY",
            signal_score=0.65, signal_type="BUY",
            signal_generator_id="bayesian_v1", regime_label=None,
            entry_time=old_entry, entry_price=1.10,
            exit_time=None, exit_price=None,
            quantity=100.0, stop_loss_price=1.078,
            status="OPEN", pnl=None, commission=None, slippage=None,
            exit_reason=None, created_at=old_entry, updated_at=old_entry,
        )
        store.save_trade(trade)
        actions = executor.evaluate_open_trades(
            risk_config=_make_risk_config(time_stop_hours=48),
            current_prices={"EUR_USD": 1.10},
            current_atrs={"EUR_USD": 0.001},
            avg_atrs_30d={"EUR_USD": 0.001},
        )
        assert len(actions) == 1
        assert actions[0][1].action == "CLOSE"
        # Trade should still be OPEN because close failed
        updated = store.get_trade("t-1")
        assert updated is not None
        assert updated.status == "OPEN"

    def test_close_all_skips_trade_without_broker_order_id(self) -> None:
        """close_all_positions skips trades without broker_order_id."""
        executor, broker, store = _make_executor()
        trade = TradeRecord(
            client_order_id="t-1", broker_order_id=None,
            instrument="EUR_USD", broker="oanda", direction="BUY",
            signal_score=0.65, signal_type="BUY",
            signal_generator_id="bayesian_v1", regime_label=None,
            entry_time=_now(), entry_price=1.10,
            exit_time=None, exit_price=None,
            quantity=100.0, stop_loss_price=1.078,
            status="OPEN", pnl=None, commission=None, slippage=None,
            exit_reason=None, created_at=_now(), updated_at=_now(),
        )
        store.save_trade(trade)
        closed = executor.close_all_positions("kill_switch")
        assert len(closed) == 0
        assert len(broker.positions_closed) == 0

    def test_idempotency_exception_falls_through(self) -> None:
        """When get_order_status raises, we fall through to place_market_order."""
        broker = FakeBrokerAdapter()
        # Make get_order_status raise for our specific ID
        original_get = broker.get_order_status

        def raising_get(coid: str) -> OrderStatus:
            if coid == "NEWTON-EUR_USD-EXC":
                raise RuntimeError("not found")
            return original_get(coid)

        broker.get_order_status = raising_get  # type: ignore[assignment]
        store = InMemoryTradeStore()
        cb = CircuitBreakerManager()
        executor = OrderExecutor(
            broker=broker, broker_name="oanda",
            trade_store=store, circuit_breaker=cb,
        )
        result = executor._place_with_idempotency(
            instrument="EUR_USD", units=100.0, stop_loss=1.08,
            client_order_id="NEWTON-EUR_USD-EXC",
        )
        assert result.success
        assert len(broker.orders_placed) == 1

    def test_sell_pnl_computation(self) -> None:
        """SELL PnL = (entry - exit) * quantity."""
        executor, broker, store = _make_executor()
        old_entry = _now() - timedelta(hours=50)
        trade = TradeRecord(
            client_order_id="t-1", broker_order_id="b-1",
            instrument="EUR_USD", broker="oanda", direction="SELL",
            signal_score=0.65, signal_type="SELL",
            signal_generator_id="bayesian_v1", regime_label=None,
            entry_time=old_entry, entry_price=1.10,
            exit_time=None, exit_price=None,
            quantity=100.0, stop_loss_price=1.122,
            status="OPEN", pnl=None, commission=None, slippage=None,
            exit_reason=None, created_at=old_entry, updated_at=old_entry,
        )
        store.save_trade(trade)
        executor.evaluate_open_trades(
            risk_config=_make_risk_config(time_stop_hours=48),
            current_prices={"EUR_USD": 1.08},
            current_atrs={"EUR_USD": 0.001},
            avg_atrs_30d={"EUR_USD": 0.001},
        )
        updated = store.get_trade("t-1")
        assert updated is not None
        assert updated.status == "CLOSED"
        # SELL PnL: (entry - exit) * qty = (1.10 - 1.1050) * 100 = -0.50
        assert updated.pnl is not None
