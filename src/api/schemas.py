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



class UATSuiteResponse(BaseModel):
    """Summary of a UAT test suite."""

    id: str
    name: str
    test_count: int


class UATTestResult(BaseModel):
    """Result of a single UAT test execution."""

    id: str
    name: str
    suite: str
    status: str
    duration_ms: int
    details: str
    error: str | None = None


class UATRunSummary(BaseModel):
    """Aggregate summary of a UAT run."""

    total: int
    passed: int
    failed: int
    duration_ms: int


class UATSuitesResponse(BaseModel):
    """Response for GET /api/v1/uat/suites."""

    suites: list[UATSuiteResponse]


class UATRunRequest(BaseModel):
    """Request body for POST /api/v1/uat/run."""

    suite: str | None = None
    test_id: str | None = None


class UATRunResponse(BaseModel):
    """Response for POST /api/v1/uat/run."""

    results: list[UATTestResult]
    summary: UATRunSummary


class RegimeResponse(BaseModel):
    """Regime state for a single instrument."""

    instrument: str
    regime_label: str
    confidence: float
    confidence_band: str
    vol_30d: float
    adx_14: float
    vol_median: float
    computed_at: datetime
    error: str | None = None


class ModelArtifactResponse(BaseModel):
    """Metadata for a single model artifact version."""

    model_type: str
    instrument: str
    version: int
    training_date: datetime
    hyperparameters: dict[str, Any]
    performance_metrics: dict[str, float]
    data_hash: str
    artifact_hash: str


class ModelListResponse(BaseModel):
    """Response for GET /api/v1/models/{instrument}."""

    instrument: str
    model_type: str | None = None
    artifacts: list[ModelArtifactResponse]
    count: int


def utc_now() -> datetime:
    """Return timezone-aware UTC now timestamp."""

    return datetime.now(tz=UTC)



def calculate_payload_checksum(payload: dict[str, Any]) -> str:
    """Compute deterministic checksum for API payload integrity checks."""

    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
