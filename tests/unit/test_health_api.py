from __future__ import annotations

from src.api.schemas import calculate_payload_checksum
from src.api.v1.data import HealthService


def test_health_service_returns_stage1_payload_shape() -> None:
    service = HealthService()
    payload = service.build_health().model_dump(mode="json")

    assert payload["status"] in {"healthy", "degraded", "unhealthy"}
    assert isinstance(payload["db"], bool)
    assert "oanda" in payload["brokers"]
    assert "binance" in payload["brokers"]
    assert "EUR_USD" in payload["instruments"]
    assert "BTC_USD" in payload["instruments"]
    assert isinstance(payload["uptime_seconds"], int)
    assert payload["generated_at"]
    assert len(payload["checksum"]) == 64


def test_health_service_checksum_matches_payload_body() -> None:
    service = HealthService()
    payload = service.build_health().model_dump(mode="json")

    checksum = payload.pop("checksum")
    assert checksum == calculate_payload_checksum(payload)
