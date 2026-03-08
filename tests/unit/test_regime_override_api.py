"""Tests for regime override API endpoints (T-704)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import src.api.v1.regime as regime_mod
from fastapi.testclient import TestClient

from src.app import app

client = TestClient(app)


def setup_function() -> None:
    """Clear overrides before each test."""
    regime_mod._overrides.clear()


# ---------------------------------------------------------------------------
# PUT /api/v1/regime/{instrument}/override
# ---------------------------------------------------------------------------


def test_set_override_returns_201() -> None:
    """Setting an override returns 201 with override details."""
    resp = client.put(
        "/api/v1/regime/EUR_USD/override",
        json={"regime_label": "HIGH_VOL_TRENDING", "reason": "manual test"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["instrument"] == "EUR_USD"
    assert data["regime_label"] == "HIGH_VOL_TRENDING"
    assert data["reason"] == "manual test"
    assert data["active"] is True
    assert data["expires_at"] is None
    assert "set_at" in data


def test_set_override_with_expiry() -> None:
    """Override with expires_at stores the expiry time."""
    future = (datetime.now(tz=UTC) + timedelta(hours=2)).isoformat()
    resp = client.put(
        "/api/v1/regime/EUR_USD/override",
        json={
            "regime_label": "LOW_VOL_RANGING",
            "reason": "scheduled",
            "expires_at": future,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["expires_at"] is not None
    assert data["active"] is True


def test_set_override_invalid_label_returns_422() -> None:
    """Invalid regime label returns 422."""
    resp = client.put(
        "/api/v1/regime/EUR_USD/override",
        json={"regime_label": "INVALID_REGIME", "reason": "bad"},
    )
    assert resp.status_code == 422


def test_set_override_unsupported_instrument_returns_404() -> None:
    """Unsupported instrument returns 404."""
    resp = client.put(
        "/api/v1/regime/INVALID/override",
        json={"regime_label": "HIGH_VOL_TRENDING", "reason": "test"},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /api/v1/regime/{instrument}/override
# ---------------------------------------------------------------------------


def test_clear_override_returns_200() -> None:
    """Clearing an active override returns 200."""
    client.put(
        "/api/v1/regime/EUR_USD/override",
        json={"regime_label": "HIGH_VOL_TRENDING", "reason": "test"},
    )
    resp = client.delete("/api/v1/regime/EUR_USD/override")
    assert resp.status_code == 200
    data = resp.json()
    assert data["active"] is False


def test_clear_override_when_none_returns_404() -> None:
    """Clearing when no override exists returns 404."""
    resp = client.delete("/api/v1/regime/EUR_USD/override")
    assert resp.status_code == 404


def test_clear_override_unsupported_instrument_returns_404() -> None:
    """Unsupported instrument returns 404."""
    resp = client.delete("/api/v1/regime/INVALID/override")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/v1/regime/{instrument} — override integration
# ---------------------------------------------------------------------------


def test_get_regime_returns_override_when_active() -> None:
    """GET regime should return overridden regime when override is active."""
    client.put(
        "/api/v1/regime/EUR_USD/override",
        json={"regime_label": "HIGH_VOL_TRENDING", "reason": "override test"},
    )
    resp = client.get("/api/v1/regime/EUR_USD")
    assert resp.status_code == 200
    data = resp.json()
    assert data["regime_label"] == "HIGH_VOL_TRENDING"
    assert data["override_active"] is True


def test_get_regime_returns_computed_after_clear() -> None:
    """After clearing override, GET regime returns computed regime."""
    client.put(
        "/api/v1/regime/EUR_USD/override",
        json={"regime_label": "HIGH_VOL_TRENDING", "reason": "test"},
    )
    client.delete("/api/v1/regime/EUR_USD/override")
    resp = client.get("/api/v1/regime/EUR_USD")
    assert resp.status_code == 200
    data = resp.json()
    assert data["override_active"] is False


def test_get_regime_expired_override_returns_computed() -> None:
    """An expired override should be auto-cleared on GET."""
    past = (datetime.now(tz=UTC) - timedelta(hours=1)).isoformat()
    client.put(
        "/api/v1/regime/EUR_USD/override",
        json={
            "regime_label": "LOW_VOL_RANGING",
            "reason": "expired",
            "expires_at": past,
        },
    )
    resp = client.get("/api/v1/regime/EUR_USD")
    assert resp.status_code == 200
    data = resp.json()
    assert data["override_active"] is False


# ---------------------------------------------------------------------------
# Full set/get/clear cycle
# ---------------------------------------------------------------------------


def test_full_set_get_clear_cycle() -> None:
    """Full lifecycle: set → get (overridden) → clear → get (computed)."""
    # Set
    put_resp = client.put(
        "/api/v1/regime/BTC_USD/override",
        json={"regime_label": "LOW_VOL_TRENDING", "reason": "cycle test"},
    )
    assert put_resp.status_code == 200

    # Get — override active
    get_resp = client.get("/api/v1/regime/BTC_USD")
    assert get_resp.status_code == 200
    assert get_resp.json()["regime_label"] == "LOW_VOL_TRENDING"
    assert get_resp.json()["override_active"] is True

    # Clear
    del_resp = client.delete("/api/v1/regime/BTC_USD/override")
    assert del_resp.status_code == 200
    assert del_resp.json()["active"] is False

    # Get — computed
    get_resp2 = client.get("/api/v1/regime/BTC_USD")
    assert get_resp2.status_code == 200
    assert get_resp2.json()["override_active"] is False


def test_override_replaces_previous() -> None:
    """Setting a new override replaces the previous one."""
    client.put(
        "/api/v1/regime/EUR_USD/override",
        json={"regime_label": "HIGH_VOL_TRENDING", "reason": "first"},
    )
    client.put(
        "/api/v1/regime/EUR_USD/override",
        json={"regime_label": "LOW_VOL_RANGING", "reason": "second"},
    )
    resp = client.get("/api/v1/regime/EUR_USD")
    data = resp.json()
    assert data["regime_label"] == "LOW_VOL_RANGING"
    assert data["override_active"] is True
