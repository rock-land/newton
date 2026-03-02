from __future__ import annotations

import logging

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


def test_health_check_database_logs_exceptions() -> None:
    """Health check should log exceptions instead of silently swallowing them."""
    import pytest

    mp = pytest.MonkeyPatch()
    mp.setenv("DATABASE_URL", "postgresql://invalid:invalid@localhost:1/nonexistent")

    try:
        service = HealthService()
        target_logger = logging.getLogger("src.api.v1.data")
        original_level = target_logger.level
        target_logger.setLevel(logging.DEBUG)
        captured: list[str] = []
        handler = logging.Handler()
        handler.emit = lambda record: captured.append(record.getMessage())  # type: ignore[assignment]
        target_logger.addHandler(handler)

        try:
            result = service.check_database()
        finally:
            target_logger.removeHandler(handler)
            target_logger.setLevel(original_level)

        assert result is False
        assert any("database" in msg.lower() or "health" in msg.lower() for msg in captured)
    finally:
        mp.undo()
