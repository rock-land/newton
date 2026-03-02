"""API response schemas for Newton v1 endpoints."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class BrokerHealth(BaseModel):
    """Broker connectivity and latency status."""

    connected: bool
    last_response_ms: int | None = None


class InstrumentHealth(BaseModel):
    """Per-instrument data freshness and runtime status."""

    last_candle_age_seconds: int | None = None
    reconciled: bool = True
    regime: str = "UNKNOWN"
    regime_confidence: float = 0.0


class HealthResponse(BaseModel):
    """System health payload for thin-client status panel."""

    status: Literal["healthy", "degraded", "unhealthy"]
    db: bool
    brokers: dict[str, BrokerHealth]
    instruments: dict[str, InstrumentHealth]
    kill_switch_active: bool
    uptime_seconds: int = Field(ge=0)
    generated_at: datetime
    checksum: str



def utc_now() -> datetime:
    """Return timezone-aware UTC now timestamp."""

    return datetime.now(tz=UTC)



def calculate_payload_checksum(payload: dict[str, Any]) -> str:
    """Compute deterministic checksum for API payload integrity checks."""

    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
