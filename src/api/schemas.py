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
    override_active: bool = False


class RegimeOverrideRequest(BaseModel):
    """Request body for PUT /api/v1/regime/{instrument}/override."""

    regime_label: str
    reason: str
    expires_at: datetime | None = None


class RegimeOverrideResponse(BaseModel):
    """Response for regime override operations."""

    instrument: str
    regime_label: str
    reason: str
    expires_at: datetime | None = None
    set_at: datetime
    active: bool


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


# ---------------------------------------------------------------------------
# Backtest schemas (T-606)
# ---------------------------------------------------------------------------


class BacktestRunRequest(BaseModel):
    """Request body for POST /api/v1/backtest."""

    instrument: str
    start_date: datetime
    end_date: datetime
    pessimistic: bool = False
    initial_equity: float = Field(default=10_000.0, gt=0, le=10_000_000.0)


class EquityCurvePoint(BaseModel):
    """Single point on the equity curve."""

    time: datetime
    equity: float


class BacktestTradeResponse(BaseModel):
    """Serialized backtest trade."""

    entry_time: datetime
    entry_price: float
    exit_time: datetime | None
    exit_price: float | None
    direction: str
    quantity: float
    pnl: float
    commission: float
    slippage_cost: float
    spread_cost: float
    exit_reason: str
    regime_label: str


class CalibrationDecileResponse(BaseModel):
    """Per-decile calibration data for calibration plots."""

    bin_index: int
    predicted_mid: float
    observed_freq: float
    count: int


class BacktestMetricsResponse(BaseModel):
    """Performance metrics from a backtest run."""

    sharpe_ratio: float
    profit_factor: float
    max_drawdown: float
    win_rate: float
    calmar_ratio: float
    expectancy: float
    calibration_error: float
    trade_count: int
    annualized_return: float
    total_return: float
    calibration_deciles: list[CalibrationDecileResponse] = []


class BacktestGateResultResponse(BaseModel):
    """Single metric gate evaluation result."""

    metric_name: str
    value: float
    threshold: float
    gate_type: str
    passed: bool


class BacktestGateResponse(BaseModel):
    """Aggregate gate evaluation."""

    results: list[BacktestGateResultResponse]
    all_hard_gates_passed: bool
    instrument: str


class BacktestRegimeResponse(BaseModel):
    """Per-regime performance breakdown entry."""

    regime_label: str
    sharpe_ratio: float
    profit_factor: float
    win_rate: float
    trade_count: int
    total_pnl: float
    low_sample_flag: bool


class BacktestBiasControlResponse(BaseModel):
    """Bias control checklist entry."""

    bias_name: str
    mitigation: str
    status: str


class BacktestResultResponse(BaseModel):
    """Full backtest results including metrics, gates, regime, and bias."""

    instrument: str
    equity_curve: list[EquityCurvePoint]
    trades: list[BacktestTradeResponse]
    metrics: BacktestMetricsResponse
    gate_evaluation: BacktestGateResponse
    regime_breakdown: dict[str, BacktestRegimeResponse]
    bias_controls: list[BacktestBiasControlResponse]
    low_sample_regimes: list[str]
    initial_equity: float
    final_equity: float
    total_return: float
    trade_count: int


class BacktestRunStatusResponse(BaseModel):
    """Status and results of a backtest run."""

    id: str
    status: str
    instrument: str
    start_date: datetime
    end_date: datetime
    pessimistic: bool
    initial_equity: float
    created_at: datetime
    completed_at: datetime | None = None
    result: BacktestResultResponse | None = None
    error: str | None = None


class BacktestListResponse(BaseModel):
    """List of backtest runs."""

    runs: list[BacktestRunStatusResponse]
    count: int


def utc_now() -> datetime:
    """Return timezone-aware UTC now timestamp."""

    return datetime.now(tz=UTC)



def calculate_payload_checksum(payload: dict[str, Any]) -> str:
    """Compute deterministic checksum for API payload integrity checks."""

    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
