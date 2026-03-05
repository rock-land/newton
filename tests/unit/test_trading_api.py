"""Tests for trading API endpoints (T-508)."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from src.api.v1.trading import (
    InMemoryConfigChangeStore,
    TradingService,
    configure,
)
from src.app import app
from src.data.schema import RiskConfig, RiskDefaults, RiskPortfolio
from src.trading.circuit_breaker import CircuitBreakerManager
from src.trading.broker_base import OrderResult
from src.trading.executor import InMemoryTradeStore, OrderExecutor, TradeRecord

client = TestClient(app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_trade(
    instrument: str = "EUR_USD",
    status: str = "OPEN",
    broker: str = "oanda",
    client_order_id: str = "NEWTON-EUR_USD-1000",
    direction: str = "BUY",
    **overrides: object,
) -> TradeRecord:
    now = datetime.now(UTC)
    defaults: dict[str, object] = {
        "client_order_id": client_order_id,
        "broker_order_id": "broker-1",
        "instrument": instrument,
        "broker": broker,
        "direction": direction,
        "signal_score": 0.75,
        "signal_type": "BUY",
        "signal_generator_id": "BayesianV1",
        "regime_label": "trending",
        "entry_time": now,
        "entry_price": 1.1000,
        "exit_time": None,
        "exit_price": None,
        "quantity": 100.0,
        "stop_loss_price": 1.0950,
        "status": status,
        "pnl": None,
        "commission": None,
        "slippage": None,
        "exit_reason": None,
        "created_at": now,
        "updated_at": now,
    }
    defaults.update(overrides)
    return TradeRecord(**defaults)  # type: ignore[arg-type]


def _make_risk_config() -> RiskConfig:
    return RiskConfig(
        defaults=RiskDefaults(
            max_position_pct=0.10,
            max_risk_per_trade_pct=0.02,
            kelly_fraction=0.25,
            kelly_min_trades=30,
            kelly_window=100,
            micro_size_pct=0.001,
            hard_stop_pct=0.02,
            trailing_activation_pct=0.01,
            trailing_breakeven_pct=0.005,
            time_stop_hours=48,
            daily_loss_limit_pct=0.02,
            max_drawdown_pct=0.10,
            consecutive_loss_halt=5,
            consecutive_loss_halt_hours=24,
            gap_risk_multiplier=0.5,
            volatility_threshold_multiplier=2.0,
            high_volatility_size_reduction=0.5,
            high_volatility_stop_pct=0.03,
        ),
        portfolio=RiskPortfolio(
            max_total_exposure_pct=0.5,
            max_portfolio_drawdown_pct=0.2,
        ),
    )


def _setup_service(
    trades: list[TradeRecord] | None = None,
    kill_switch_active: bool = False,
) -> tuple[InMemoryTradeStore, CircuitBreakerManager, InMemoryConfigChangeStore]:
    trade_store = InMemoryTradeStore()
    for t in (trades or []):
        trade_store.save_trade(t)

    cb = CircuitBreakerManager()
    if kill_switch_active:
        cb.activate_kill_switch("test")

    config_store = InMemoryConfigChangeStore()
    risk_config = _make_risk_config()

    svc = TradingService(
        trade_store=trade_store,
        circuit_breaker=cb,
        config_change_store=config_store,
        risk_config=risk_config,
    )
    configure(svc)

    return trade_store, cb, config_store


# ---------------------------------------------------------------------------
# GET /api/v1/trades
# ---------------------------------------------------------------------------


class TestGetTrades:
    """GET /api/v1/trades endpoint."""

    def test_empty_trades(self) -> None:
        _setup_service()
        resp = client.get("/api/v1/trades")
        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 0
        assert body["trades"] == []

    def test_returns_trades(self) -> None:
        trade = _make_trade()
        _setup_service(trades=[trade])
        resp = client.get("/api/v1/trades")
        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 1
        assert body["trades"][0]["client_order_id"] == "NEWTON-EUR_USD-1000"

    def test_filter_by_instrument(self) -> None:
        t1 = _make_trade(instrument="EUR_USD", client_order_id="t1")
        t2 = _make_trade(instrument="BTC_USD", client_order_id="t2")
        _setup_service(trades=[t1, t2])
        resp = client.get("/api/v1/trades?instrument=EUR_USD")
        body = resp.json()
        assert body["count"] == 1
        assert body["trades"][0]["instrument"] == "EUR_USD"

    def test_filter_by_status(self) -> None:
        t1 = _make_trade(status="OPEN", client_order_id="t1")
        t2 = _make_trade(status="CLOSED", client_order_id="t2")
        _setup_service(trades=[t1, t2])
        resp = client.get("/api/v1/trades?status=OPEN")
        body = resp.json()
        assert body["count"] == 1
        assert body["trades"][0]["status"] == "OPEN"

    def test_filter_by_broker(self) -> None:
        t1 = _make_trade(broker="oanda", client_order_id="t1")
        t2 = _make_trade(broker="binance", client_order_id="t2")
        _setup_service(trades=[t1, t2])
        resp = client.get("/api/v1/trades?broker=oanda")
        body = resp.json()
        assert body["count"] == 1
        assert body["trades"][0]["broker"] == "oanda"

    def test_limit_parameter(self) -> None:
        trades = [_make_trade(client_order_id=f"t{i}") for i in range(5)]
        _setup_service(trades=trades)
        resp = client.get("/api/v1/trades?limit=2")
        body = resp.json()
        assert body["count"] == 2

    def test_service_not_configured(self) -> None:
        from src.api.v1 import trading

        trading._service = None
        resp = client.get("/api/v1/trades")
        assert resp.status_code == 503


# ---------------------------------------------------------------------------
# POST /api/v1/kill
# ---------------------------------------------------------------------------


class TestActivateKillSwitch:
    """POST /api/v1/kill endpoint."""

    def test_activate(self) -> None:
        _, cb, config_store = _setup_service()
        resp = client.post("/api/v1/kill", json={"reason": "emergency"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["active"] is True
        assert body["action"] == "activated"
        assert cb.is_kill_switch_active()
        # Audit logged
        changes = config_store.get_changes("kill_switch")
        assert len(changes) == 1
        assert changes[0].new_value["active"] is True

    def test_activate_already_active(self) -> None:
        _setup_service(kill_switch_active=True)
        resp = client.post("/api/v1/kill", json={"reason": "another"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["active"] is True
        assert body["message"] == "Kill switch was already active"

    def test_activate_default_reason(self) -> None:
        _, cb, _ = _setup_service()
        resp = client.post("/api/v1/kill", json={})
        assert resp.status_code == 200
        assert cb.is_kill_switch_active()

    def test_activate_closes_positions_via_executor(self) -> None:
        """Kill switch activation should close positions through executors."""
        trade = _make_trade(status="OPEN", broker_order_id="broker-1")
        trade_store = InMemoryTradeStore()
        trade_store.save_trade(trade)

        class FakeBroker:
            def close_position(self, order_id: str) -> OrderResult:
                return OrderResult(
                    success=True,
                    order_id=order_id,
                    client_order_id="",
                    instrument="EUR_USD",
                    direction="SELL",
                    units=100.0,
                    fill_price=1.1050,
                    timestamp=datetime.now(UTC),
                    error_message=None,
                )

        cb = CircuitBreakerManager()
        config_store = InMemoryConfigChangeStore()
        executor = OrderExecutor(
            broker=FakeBroker(),  # type: ignore[arg-type]
            broker_name="oanda",
            trade_store=trade_store,
            circuit_breaker=cb,
        )
        svc = TradingService(
            trade_store=trade_store,
            circuit_breaker=cb,
            config_change_store=config_store,
            risk_config=_make_risk_config(),
            executors=[executor],
        )
        configure(svc)

        resp = client.post("/api/v1/kill", json={"reason": "test_close"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["positions_closed"] == 1


# ---------------------------------------------------------------------------
# DELETE /api/v1/kill
# ---------------------------------------------------------------------------


class TestDeactivateKillSwitch:
    """DELETE /api/v1/kill endpoint."""

    def test_deactivate_with_confirm(self) -> None:
        _, cb, config_store = _setup_service(kill_switch_active=True)
        resp = client.delete("/api/v1/kill?confirm=true")
        assert resp.status_code == 200
        body = resp.json()
        assert body["active"] is False
        assert body["action"] == "deactivated"
        assert not cb.is_kill_switch_active()
        # Audit logged
        changes = config_store.get_changes("kill_switch")
        assert len(changes) == 1

    def test_deactivate_without_confirm(self) -> None:
        _setup_service(kill_switch_active=True)
        resp = client.delete("/api/v1/kill")
        assert resp.status_code == 400
        assert "confirm=true" in resp.json()["detail"]

    def test_deactivate_confirm_false(self) -> None:
        _setup_service(kill_switch_active=True)
        resp = client.delete("/api/v1/kill?confirm=false")
        assert resp.status_code == 400

    def test_deactivate_not_active(self) -> None:
        _setup_service()
        resp = client.delete("/api/v1/kill?confirm=true")
        assert resp.status_code == 200
        body = resp.json()
        assert body["active"] is False
        assert body["message"] == "Kill switch was not active"


# ---------------------------------------------------------------------------
# GET /api/v1/config/risk
# ---------------------------------------------------------------------------


class TestGetRiskConfig:
    """GET /api/v1/config/risk endpoint."""

    def test_returns_current_config(self) -> None:
        _setup_service()
        resp = client.get("/api/v1/config/risk")
        assert resp.status_code == 200
        body = resp.json()
        assert "defaults" in body["config"]
        assert "portfolio" in body["config"]
        assert body["config"]["defaults"]["hard_stop_pct"] == 0.02

    def test_portfolio_fields(self) -> None:
        _setup_service()
        resp = client.get("/api/v1/config/risk")
        body = resp.json()
        assert body["config"]["portfolio"]["max_total_exposure_pct"] == 0.5
        assert body["config"]["portfolio"]["max_portfolio_drawdown_pct"] == 0.2


# ---------------------------------------------------------------------------
# PUT /api/v1/config/risk
# ---------------------------------------------------------------------------


class TestUpdateRiskConfig:
    """PUT /api/v1/config/risk endpoint."""

    def test_update_defaults(self) -> None:
        _, _, config_store = _setup_service()
        resp = client.put(
            "/api/v1/config/risk",
            json={
                "defaults": {"hard_stop_pct": 0.03},
                "reason": "Widening stops",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["config"]["defaults"]["hard_stop_pct"] == 0.03
        # Verify audit log
        changes = config_store.get_changes("risk")
        assert len(changes) == 1
        assert changes[0].reason == "Widening stops"

    def test_update_portfolio(self) -> None:
        _setup_service()
        resp = client.put(
            "/api/v1/config/risk",
            json={"portfolio": {"max_total_exposure_pct": 0.6}},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["config"]["portfolio"]["max_total_exposure_pct"] == 0.6

    def test_invalid_value_rejected(self) -> None:
        _setup_service()
        resp = client.put(
            "/api/v1/config/risk",
            json={"defaults": {"hard_stop_pct": 99.0}},
        )
        assert resp.status_code == 422

    def test_logs_old_and_new(self) -> None:
        _, _, config_store = _setup_service()
        client.put(
            "/api/v1/config/risk",
            json={"defaults": {"hard_stop_pct": 0.04}},
        )
        changes = config_store.get_changes("risk")
        assert len(changes) == 1
        entry = changes[0]
        assert entry.old_value["defaults"]["hard_stop_pct"] == 0.02
        assert entry.new_value["defaults"]["hard_stop_pct"] == 0.04

    def test_empty_update_preserves_config(self) -> None:
        _setup_service()
        resp = client.put("/api/v1/config/risk", json={})
        assert resp.status_code == 200
        body = resp.json()
        assert body["config"]["defaults"]["hard_stop_pct"] == 0.02

    def test_changed_by_field(self) -> None:
        _, _, config_store = _setup_service()
        client.put(
            "/api/v1/config/risk",
            json={
                "defaults": {"hard_stop_pct": 0.03},
                "changed_by": "admin_user",
            },
        )
        changes = config_store.get_changes("risk")
        assert changes[0].changed_by == "admin_user"

    def test_subsequent_get_reflects_update(self) -> None:
        _setup_service()
        client.put(
            "/api/v1/config/risk",
            json={"defaults": {"hard_stop_pct": 0.05}},
        )
        resp = client.get("/api/v1/config/risk")
        assert resp.json()["config"]["defaults"]["hard_stop_pct"] == 0.05


# ---------------------------------------------------------------------------
# ConfigChangeStore
# ---------------------------------------------------------------------------


class TestInMemoryConfigChangeStore:
    """Unit tests for InMemoryConfigChangeStore."""

    def test_save_and_get(self) -> None:
        from src.api.v1.trading import ConfigChangeEntry

        store = InMemoryConfigChangeStore()
        entry = ConfigChangeEntry(
            changed_at=datetime.now(UTC),
            changed_by="test",
            section="risk",
            instrument=None,
            old_value={"a": 1},
            new_value={"a": 2},
            reason="testing",
        )
        store.save_change(entry)
        assert len(store.get_changes(None)) == 1
        assert len(store.get_changes("risk")) == 1
        assert len(store.get_changes("other")) == 0
