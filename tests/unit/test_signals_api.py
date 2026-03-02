from __future__ import annotations

from src.api.v1 import signals as signals_api
from src.app import app


def test_signals_generators_endpoint_is_additive() -> None:
    payload = signals_api.list_signal_generators()
    assert payload["count"] >= 1


def test_signals_endpoint_returns_contract_fields() -> None:
    payload = signals_api.get_current_signal("EUR_USD")
    assert payload["action"] in {"STRONG_BUY", "BUY", "SELL", "NEUTRAL"}
    assert "probability" in payload
    assert "confidence" in payload
    assert isinstance(payload["component_scores"], dict)
    assert isinstance(payload["metadata"], dict)


def test_stage1_endpoints_unchanged_paths_still_registered() -> None:
    paths = app.openapi()["paths"]

    assert "/api/v1/health" in paths
    assert "/api/v1/ohlcv/{instrument}" in paths
    assert "/api/v1/features/{instrument}" in paths
    assert "/api/v1/features/metadata" in paths
