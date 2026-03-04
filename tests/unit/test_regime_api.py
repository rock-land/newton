"""Tests for the regime detection API endpoint (T-404)."""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from src.app import app

client = TestClient(app)


def test_regime_endpoint_returns_unknown_without_db() -> None:
    """Without DATABASE_URL, the endpoint should return UNKNOWN regime gracefully."""
    with patch.dict("os.environ", {}, clear=False):
        # Ensure DATABASE_URL is not set
        import os

        saved = os.environ.pop("DATABASE_URL", None)
        try:
            resp = client.get("/api/v1/regime/EUR_USD")
        finally:
            if saved is not None:
                os.environ["DATABASE_URL"] = saved

    assert resp.status_code == 200
    data = resp.json()
    assert data["instrument"] == "EUR_USD"
    assert data["regime_label"] == "UNKNOWN"
    assert data["confidence"] == 0.0
    assert data["confidence_band"] == "LOW"
    assert data["error"] is not None


def test_regime_endpoint_rejects_unsupported_instrument() -> None:
    """Unsupported instruments should return 404."""
    resp = client.get("/api/v1/regime/INVALID_PAIR")
    assert resp.status_code == 404


def test_regime_endpoint_response_shape_eur_usd() -> None:
    """Verify the response shape includes all required fields."""
    resp = client.get("/api/v1/regime/EUR_USD")
    assert resp.status_code == 200
    data = resp.json()
    required_keys = {
        "instrument",
        "regime_label",
        "confidence",
        "confidence_band",
        "vol_30d",
        "adx_14",
        "vol_median",
        "computed_at",
    }
    assert required_keys.issubset(data.keys())


def test_regime_endpoint_response_shape_btc_usd() -> None:
    """Both supported instruments should return valid responses."""
    resp = client.get("/api/v1/regime/BTC_USD")
    assert resp.status_code == 200
    data = resp.json()
    assert data["instrument"] == "BTC_USD"
    assert "regime_label" in data
