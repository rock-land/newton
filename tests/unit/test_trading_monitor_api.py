"""Tests for trading monitor API endpoints (T-705).

Tests circuit breaker snapshot, reconciliation status, and pause/resume endpoints.
"""

from __future__ import annotations

import src.api.v1.trading as trading_mod
from fastapi.testclient import TestClient

from src.api.v1.trading import (
    InMemoryConfigChangeStore,
    TradingService,
    configure,
)
from src.app import app
from src.data.schema import RiskConfig, RiskDefaults, RiskPortfolio
from src.trading.circuit_breaker import CircuitBreakerManager
from src.trading.executor import InMemoryTradeStore

client = TestClient(app)


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


def _make_service(
    *,
    circuit_breaker: CircuitBreakerManager | None = None,
) -> TradingService:
    """Create a TradingService with defaults for testing."""
    return TradingService(
        trade_store=InMemoryTradeStore(),
        circuit_breaker=circuit_breaker or CircuitBreakerManager(),
        config_change_store=InMemoryConfigChangeStore(),
        risk_config=_make_risk_config(),
    )


def setup_function() -> None:
    """Clear pause state before each test."""
    trading_mod._paused_instruments.clear()


# ---------------------------------------------------------------------------
# GET /api/v1/circuit-breakers
# ---------------------------------------------------------------------------


def test_circuit_breakers_returns_snapshot() -> None:
    """GET /circuit-breakers returns breaker snapshot."""
    cb = CircuitBreakerManager()
    configure(_make_service(circuit_breaker=cb))
    resp = client.get("/api/v1/circuit-breakers")
    assert resp.status_code == 200
    data = resp.json()
    assert "instrument_breakers" in data
    assert "portfolio_breakers" in data
    assert "system_breakers" in data
    assert data["any_tripped"] is False
    assert data["kill_switch_active"] is False


def test_circuit_breakers_shows_tripped_kill_switch() -> None:
    """Kill switch activation is reflected in circuit breakers response."""
    cb = CircuitBreakerManager()
    cb.activate_kill_switch("test reason")
    configure(_make_service(circuit_breaker=cb))
    resp = client.get("/api/v1/circuit-breakers")
    assert resp.status_code == 200
    data = resp.json()
    assert data["any_tripped"] is True
    assert data["kill_switch_active"] is True


def test_circuit_breakers_shows_instrument_breakers() -> None:
    """Instrument-level breakers appear in the snapshot."""
    cb = CircuitBreakerManager()
    cb.update_equity(
        instrument="EUR_USD",
        day_open_equity=10000.0,
        current_equity=9700.0,
        ath_equity=10000.0,
        daily_loss_limit_pct=0.02,
        max_drawdown_pct=0.15,
    )
    configure(_make_service(circuit_breaker=cb))
    resp = client.get("/api/v1/circuit-breakers")
    data = resp.json()
    assert data["any_tripped"] is True
    eur_breakers = data["instrument_breakers"]["EUR_USD"]
    daily_loss = next(b for b in eur_breakers if b["name"] == "daily_loss")
    assert daily_loss["tripped"] is True


# ---------------------------------------------------------------------------
# GET /api/v1/reconciliation
# ---------------------------------------------------------------------------


def test_reconciliation_returns_empty_when_no_data() -> None:
    """GET /reconciliation returns empty results when no reconciliation has run."""
    configure(_make_service())
    resp = client.get("/api/v1/reconciliation")
    assert resp.status_code == 200
    data = resp.json()
    assert data["results"] == []
    assert data["unresolved_count"] == 0


# ---------------------------------------------------------------------------
# PUT /api/v1/trading/pause/{instrument}
# ---------------------------------------------------------------------------


def test_pause_instrument_returns_200() -> None:
    """Pausing an instrument returns 200."""
    configure(_make_service())
    resp = client.put("/api/v1/trading/pause/EUR_USD")
    assert resp.status_code == 200
    data = resp.json()
    assert data["instrument"] == "EUR_USD"
    assert data["paused"] is True


def test_pause_invalid_instrument_returns_404() -> None:
    """Pausing an unsupported instrument returns 404."""
    configure(_make_service())
    resp = client.put("/api/v1/trading/pause/INVALID")
    assert resp.status_code == 404


def test_pause_already_paused_returns_200() -> None:
    """Pausing an already-paused instrument returns 200 (idempotent)."""
    configure(_make_service())
    client.put("/api/v1/trading/pause/EUR_USD")
    resp = client.put("/api/v1/trading/pause/EUR_USD")
    assert resp.status_code == 200
    assert resp.json()["paused"] is True


# ---------------------------------------------------------------------------
# DELETE /api/v1/trading/pause/{instrument}
# ---------------------------------------------------------------------------


def test_resume_instrument_returns_200() -> None:
    """Resuming a paused instrument returns 200."""
    configure(_make_service())
    client.put("/api/v1/trading/pause/EUR_USD")
    resp = client.delete("/api/v1/trading/pause/EUR_USD")
    assert resp.status_code == 200
    data = resp.json()
    assert data["instrument"] == "EUR_USD"
    assert data["paused"] is False


def test_resume_not_paused_returns_200() -> None:
    """Resuming a non-paused instrument returns 200 (idempotent)."""
    configure(_make_service())
    resp = client.delete("/api/v1/trading/pause/EUR_USD")
    assert resp.status_code == 200
    assert resp.json()["paused"] is False


def test_resume_invalid_instrument_returns_404() -> None:
    """Resuming an unsupported instrument returns 404."""
    configure(_make_service())
    resp = client.delete("/api/v1/trading/pause/INVALID")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/v1/trading/pause — list paused instruments
# ---------------------------------------------------------------------------


def test_list_paused_returns_empty() -> None:
    """GET /trading/pause returns empty list when nothing is paused."""
    configure(_make_service())
    resp = client.get("/api/v1/trading/pause")
    assert resp.status_code == 200
    data = resp.json()
    assert data["paused_instruments"] == []


def test_list_paused_returns_paused_instruments() -> None:
    """GET /trading/pause returns list of paused instruments."""
    configure(_make_service())
    client.put("/api/v1/trading/pause/EUR_USD")
    client.put("/api/v1/trading/pause/BTC_USD")
    resp = client.get("/api/v1/trading/pause")
    assert resp.status_code == 200
    data = resp.json()
    assert sorted(data["paused_instruments"]) == ["BTC_USD", "EUR_USD"]
