"""Backtest API endpoints (T-606, SPEC §8.1).

Provides endpoints to run backtests and retrieve results with metrics,
gate evaluations, regime breakdowns, and bias controls.
"""

from __future__ import annotations

import json
import logging
import math
import os
import threading
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from fastapi import APIRouter, HTTPException

if TYPE_CHECKING:
    from src.backtest.simulator import FillConfig
    from src.data.fetcher_base import CandleRecord
    from src.trading.risk import ResolvedRiskConfig

from src.api.schemas import (
    BacktestBiasControlResponse,
    BacktestGateResponse,
    BacktestGateResultResponse,
    BacktestListResponse,
    BacktestMetricsResponse,
    BacktestRegimeResponse,
    BacktestResultResponse,
    BacktestRunRequest,
    BacktestRunStatusResponse,
    BacktestTradeResponse,
    CalibrationDecileResponse,
    EquityCurvePoint,
)
from src.backtest.engine import BacktestConfig, BacktestResult, BacktestTrade
from src.backtest.metrics import compute_metrics, evaluate_gates
from src.backtest.report import build_bias_controls, compute_regime_breakdown

logger = logging.getLogger(__name__)

router = APIRouter(tags=["backtest"])

_SUPPORTED_INSTRUMENTS = {"EUR_USD", "BTC_USD"}
_ANNUALIZATION_FACTORS: dict[str, float] = {
    "EUR_USD": math.sqrt(252),
    "BTC_USD": math.sqrt(365),
}


# ---------------------------------------------------------------------------
# BacktestRunner protocol (DEC-005)
# ---------------------------------------------------------------------------


@runtime_checkable
class BacktestRunner(Protocol):
    """Protocol for executing backtests."""

    def run(self, config: BacktestConfig) -> BacktestResult: ...


# ---------------------------------------------------------------------------
# Run state (mutable — service internal only)
# ---------------------------------------------------------------------------


@dataclass
class _RunState:
    """Mutable state for a single backtest run."""

    id: str
    status: str  # "running", "completed", "failed"
    instrument: str
    start_date: datetime
    end_date: datetime
    pessimistic: bool
    initial_equity: float
    result: BacktestResultResponse | None = None
    error: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


_MAX_RUNS = 100
"""Maximum stored backtest runs. Oldest completed runs evicted when exceeded."""


@dataclass
class BacktestService:
    """Manages backtest execution and result storage."""

    runner: BacktestRunner
    _runs: dict[str, _RunState] = field(default_factory=dict)
    _executor: ThreadPoolExecutor = field(
        default_factory=lambda: ThreadPoolExecutor(max_workers=2),
    )
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def submit_run(self, request: BacktestRunRequest) -> tuple[str, Future[None]]:
        """Submit a backtest run. Returns (run_id, future)."""
        run_id = uuid.uuid4().hex[:12]
        state = _RunState(
            id=run_id,
            status="running",
            instrument=request.instrument,
            start_date=request.start_date,
            end_date=request.end_date,
            pessimistic=request.pessimistic,
            initial_equity=request.initial_equity,
        )
        with self._lock:
            self._evict_oldest()
            self._runs[run_id] = state
        future = self._executor.submit(self._execute, state, request)
        return run_id, future

    def get_run(self, run_id: str) -> _RunState | None:
        with self._lock:
            return self._runs.get(run_id)

    def list_runs(self) -> list[_RunState]:
        with self._lock:
            runs = list(self._runs.values())
        return sorted(runs, key=lambda r: r.created_at, reverse=True)

    def _evict_oldest(self) -> None:
        """Remove oldest completed runs when at capacity. Called under lock."""
        if len(self._runs) < _MAX_RUNS:
            return
        completed = sorted(
            (r for r in self._runs.values() if r.status in ("completed", "failed")),
            key=lambda r: r.created_at,
        )
        while len(self._runs) >= _MAX_RUNS and completed:
            oldest = completed.pop(0)
            del self._runs[oldest.id]

    def _execute(self, state: _RunState, request: BacktestRunRequest) -> None:
        try:
            config = BacktestConfig(
                instrument=request.instrument,
                interval="1h",
                start_date=request.start_date,
                end_date=request.end_date,
                initial_equity=request.initial_equity,
                pessimistic=request.pessimistic,
            )
            result = self.runner.run(config)
            with self._lock:
                state.result = _build_result_response(result)
                state.status = "completed"
                state.completed_at = datetime.now(UTC)
        except Exception:
            logger.exception("Backtest run %s failed", state.id)
            with self._lock:
                state.status = "failed"
                state.error = "Backtest execution failed"
                state.completed_at = datetime.now(UTC)

    def build_status_response(
        self, run_id: str, *, include_result: bool = True,
    ) -> BacktestRunStatusResponse:
        """Build API response from internal run state."""
        with self._lock:
            state = self._runs[run_id]
            return BacktestRunStatusResponse(
                id=state.id,
                status=state.status,
                instrument=state.instrument,
                start_date=state.start_date,
                end_date=state.end_date,
                pessimistic=state.pessimistic,
                initial_equity=state.initial_equity,
                created_at=state.created_at,
                completed_at=state.completed_at,
                result=state.result if include_result else None,
                error=state.error,
            )


# ---------------------------------------------------------------------------
# Default runner (loads candles from DB, uses neutral signal generator)
# ---------------------------------------------------------------------------

_ROOT_DIR = Path(__file__).resolve().parents[3]


class _NeutralGenerator:
    """Minimal signal generator that always returns BUY for backtest testing."""

    @property
    def id(self) -> str:
        return "backtest_neutral"

    @property
    def version(self) -> str:
        return "1.0"

    def generate(
        self, instrument: str, features: object, config: object,
    ) -> object:
        from src.analysis.signal_contract import Signal
        return Signal(
            instrument=instrument,
            action="BUY",
            probability=0.6,
            confidence=0.5,
            component_scores={},
            metadata={"generator": "backtest_neutral"},
            generated_at=datetime.now(UTC),
            generator_id="backtest_neutral",
        )

    def generate_batch(
        self, instrument: str, historical_features: list[object], config: object,
    ) -> list[object]:
        return []

    def validate_config(self, config: dict[str, object]) -> bool:
        return True


class DefaultBacktestRunner:
    """Default BacktestRunner that loads candles from DB and runs the engine."""

    def run(self, config: BacktestConfig) -> BacktestResult:
        from src.analysis.signal_contract import GeneratorConfig
        from src.backtest.engine import run_backtest

        candles = self._load_candles(config)
        fill_config = self._build_fill(config)
        risk_config = self._default_risk()
        generator = _NeutralGenerator()
        gen_config = GeneratorConfig(enabled=True, parameters={})

        return run_backtest(
            candles=candles,
            signal_generator=generator,  # type: ignore[arg-type]
            generator_config=gen_config,
            fill_config=fill_config,
            risk_config=risk_config,
            config=config,
        )

    def _load_candles(self, config: BacktestConfig) -> list[CandleRecord]:
        from src.data.fetcher_base import CandleRecord

        db_url = os.environ.get(
            "DATABASE_URL",
            "postgresql://newton:newton@localhost:5432/newton",
        )
        try:
            import psycopg
            with psycopg.connect(db_url, autocommit=True) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT time, instrument, interval, open, high, low, close,
                               volume, COALESCE(spread_avg, 0), verified, source
                        FROM ohlcv
                        WHERE instrument = %s AND interval = %s
                          AND time >= %s AND time <= %s
                        ORDER BY time ASC
                        """,
                        (config.instrument, config.interval,
                         config.start_date, config.end_date),
                    )
                    rows = cur.fetchall()
        except Exception:
            logger.exception("Failed to load candles for backtest")
            return []

        return [
            CandleRecord(
                time=row[0], instrument=row[1], interval=row[2],
                open=float(row[3]), high=float(row[4]), low=float(row[5]),
                close=float(row[6]), volume=float(row[7]),
                spread_avg=float(row[8]), verified=bool(row[9]), source=str(row[10]),
            )
            for row in rows
        ]

    def _build_fill(self, config: BacktestConfig) -> FillConfig:
        from src.backtest.simulator import FillConfig, build_fill_config

        inst_file = _ROOT_DIR / f"config/instruments/{config.instrument}.json"
        if inst_file.exists():
            with open(inst_file) as f:
                inst_cfg = json.load(f)
            return build_fill_config(inst_cfg, pessimistic=config.pessimistic)

        # Fallback defaults
        if "BTC" in config.instrument:
            return FillConfig(
                instrument=config.instrument, asset_class="crypto",
                slippage=0.0002, half_spread=0.00025, pip_size=0.01,
                commission_pct=0.001, pessimistic=config.pessimistic,
            )
        return FillConfig(
            instrument=config.instrument, asset_class="forex",
            slippage=1.0, half_spread=0.75, pip_size=0.0001,
            commission_pct=0.0, pessimistic=config.pessimistic,
        )

    def _default_risk(self) -> ResolvedRiskConfig:
        from src.trading.risk import ResolvedRiskConfig
        return ResolvedRiskConfig(
            max_position_pct=0.10, max_risk_per_trade_pct=0.02,
            kelly_fraction=0.25, kelly_min_trades=20, kelly_window=100,
            micro_size_pct=0.005, hard_stop_pct=0.02,
            trailing_activation_pct=0.015, trailing_breakeven_pct=0.005,
            time_stop_hours=48, daily_loss_limit_pct=0.03,
            max_drawdown_pct=0.15, consecutive_loss_halt=5,
            consecutive_loss_halt_hours=24, gap_risk_multiplier=1.5,
            volatility_threshold_multiplier=2.0,
            high_volatility_size_reduction=0.5,
            high_volatility_stop_pct=0.03,
        )


# ---------------------------------------------------------------------------
# Module-level service singleton
# ---------------------------------------------------------------------------

_service: BacktestService | None = None


def configure(service: BacktestService) -> None:
    """Inject the backtest service (called at startup or in tests)."""
    global _service
    _service = service


def _get_service() -> BacktestService:
    if _service is None:
        # Auto-configure with default runner on first access
        configure(BacktestService(runner=DefaultBacktestRunner()))
    assert _service is not None
    return _service


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/backtest", response_model=BacktestRunStatusResponse)
def create_backtest_run(req: BacktestRunRequest) -> BacktestRunStatusResponse:
    """Run a backtest for an instrument over a date range."""
    service = _get_service()

    if req.instrument not in _SUPPORTED_INSTRUMENTS:
        raise HTTPException(
            status_code=400, detail=f"Unsupported instrument: {req.instrument}",
        )
    if req.start_date >= req.end_date:
        raise HTTPException(status_code=400, detail="start_date must be before end_date")
    max_range = timedelta(days=5 * 365)
    if req.end_date - req.start_date > max_range:
        raise HTTPException(status_code=400, detail="Date range must not exceed 5 years")

    run_id, future = service.submit_run(req)

    # Wait for completion with timeout (sync mode for v1)
    try:
        future.result(timeout=300)
    except TimeoutError:
        pass  # Will be polled via GET /backtest/{run_id}

    return service.build_status_response(run_id)


@router.get("/backtest", response_model=BacktestListResponse)
def list_backtest_runs() -> BacktestListResponse:
    """List all backtest runs (without full result data)."""
    service = _get_service()
    runs = service.list_runs()
    return BacktestListResponse(
        runs=[service.build_status_response(r.id, include_result=False) for r in runs],
        count=len(runs),
    )


@router.get("/backtest/{run_id}", response_model=BacktestRunStatusResponse)
def get_backtest_run(run_id: str) -> BacktestRunStatusResponse:
    """Get the status and results of a backtest run."""
    service = _get_service()
    state = service.get_run(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"Backtest run not found: {run_id}")
    return service.build_status_response(run_id)


# ---------------------------------------------------------------------------
# Response builders
# ---------------------------------------------------------------------------


def _build_result_response(result: BacktestResult) -> BacktestResultResponse:
    """Convert BacktestResult + computed analytics to API response."""
    instrument = result.config.instrument
    ann_factor = _ANNUALIZATION_FACTORS.get(instrument, math.sqrt(252))

    metrics = compute_metrics(result, annualization_factor=ann_factor)
    gate_eval = evaluate_gates(metrics, instrument=instrument)
    breakdown = compute_regime_breakdown(result.trades, ann_factor)
    bias = build_bias_controls(instrument=instrument)
    low_sample = [label for label, perf in breakdown.items() if perf.low_sample_flag]

    return BacktestResultResponse(
        instrument=instrument,
        equity_curve=[
            EquityCurvePoint(time=t, equity=v)
            for t, v in result.equity_curve
        ],
        trades=[_trade_to_response(t) for t in result.trades],
        metrics=BacktestMetricsResponse(
            sharpe_ratio=metrics.sharpe_ratio,
            profit_factor=metrics.profit_factor,
            max_drawdown=metrics.max_drawdown,
            win_rate=metrics.win_rate,
            calmar_ratio=metrics.calmar_ratio,
            expectancy=metrics.expectancy,
            calibration_error=metrics.calibration_error,
            trade_count=metrics.trade_count,
            annualized_return=metrics.annualized_return,
            total_return=metrics.total_return,
            calibration_deciles=[
                CalibrationDecileResponse(
                    bin_index=d.bin_index,
                    predicted_mid=d.predicted_mid,
                    observed_freq=d.observed_freq,
                    count=d.count,
                )
                for d in metrics.calibration_deciles
            ],
        ),
        gate_evaluation=BacktestGateResponse(
            results=[
                BacktestGateResultResponse(
                    metric_name=r.metric_name,
                    value=r.value,
                    threshold=r.threshold,
                    gate_type=r.gate_type,
                    passed=r.passed,
                )
                for r in gate_eval.results
            ],
            all_hard_gates_passed=gate_eval.all_hard_gates_passed,
            instrument=gate_eval.instrument,
        ),
        regime_breakdown={
            label: BacktestRegimeResponse(
                regime_label=perf.regime_label,
                sharpe_ratio=perf.sharpe_ratio,
                profit_factor=perf.profit_factor,
                win_rate=perf.win_rate,
                trade_count=perf.trade_count,
                total_pnl=perf.total_pnl,
                low_sample_flag=perf.low_sample_flag,
            )
            for label, perf in breakdown.items()
        },
        bias_controls=[
            BacktestBiasControlResponse(
                bias_name=bc.bias_name,
                mitigation=bc.mitigation,
                status=bc.status,
            )
            for bc in bias
        ],
        low_sample_regimes=low_sample,
        initial_equity=result.initial_equity,
        final_equity=result.final_equity,
        total_return=result.total_return,
        trade_count=result.trade_count,
    )


def _trade_to_response(trade: BacktestTrade) -> BacktestTradeResponse:
    return BacktestTradeResponse(
        entry_time=trade.entry_time,
        entry_price=trade.entry_price,
        exit_time=trade.exit_time,
        exit_price=trade.exit_price,
        direction=trade.direction,
        quantity=trade.quantity,
        pnl=trade.pnl,
        commission=trade.commission,
        slippage_cost=trade.slippage_cost,
        spread_cost=trade.spread_cost,
        exit_reason=trade.exit_reason,
        regime_label=trade.regime_label,
    )
