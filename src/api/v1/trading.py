"""Trading API endpoints (SPEC §8.1, §6.5).

Provides trade listing, kill switch management, and risk configuration
CRUD with audit logging to the config_changes store.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ValidationError

from src.data.schema import RiskConfig
from src.trading.circuit_breaker import CircuitBreakerManager
from src.trading.executor import OrderExecutor, TradeRecord, TradeStore

logger = logging.getLogger(__name__)

router = APIRouter(tags=["trading"])


# ---------------------------------------------------------------------------
# Domain models — frozen per DEC-010
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ConfigChangeEntry:
    """Audit entry for config_changes table (§4.2)."""

    changed_at: datetime
    changed_by: str
    section: str
    instrument: str | None
    old_value: dict[str, Any]
    new_value: dict[str, Any]
    reason: str | None


# ---------------------------------------------------------------------------
# ConfigChangeStore protocol (DEC-005)
# ---------------------------------------------------------------------------


class ConfigChangeStore(Protocol):
    """Persistence for configuration change audit log."""

    def save_change(self, entry: ConfigChangeEntry) -> None: ...

    def get_changes(self, section: str | None) -> list[ConfigChangeEntry]: ...


class InMemoryConfigChangeStore:
    """In-memory implementation for testing."""

    def __init__(self) -> None:
        self._entries: list[ConfigChangeEntry] = []

    def save_change(self, entry: ConfigChangeEntry) -> None:
        self._entries.append(entry)

    def get_changes(self, section: str | None) -> list[ConfigChangeEntry]:
        if section is None:
            return list(self._entries)
        return [e for e in self._entries if e.section == section]


# ---------------------------------------------------------------------------
# Pydantic request/response models
# ---------------------------------------------------------------------------


class TradeResponse(BaseModel):
    """Serialized trade record."""

    client_order_id: str
    broker_order_id: str | None
    instrument: str
    broker: str
    direction: str
    signal_score: float
    signal_type: str
    signal_generator_id: str
    regime_label: str | None
    entry_time: datetime | None
    entry_price: float | None
    exit_time: datetime | None
    exit_price: float | None
    quantity: float
    stop_loss_price: float | None
    status: str
    pnl: float | None
    commission: float | None
    slippage: float | None
    exit_reason: str | None
    created_at: datetime
    updated_at: datetime


class TradesListResponse(BaseModel):
    """Response for GET /trades."""

    trades: list[TradeResponse]
    count: int


class KillSwitchActivateRequest(BaseModel):
    """Request body for POST /kill."""

    reason: str = "manual_activation"


class KillSwitchResponse(BaseModel):
    """Response for kill switch operations."""

    active: bool
    action: str
    positions_closed: int
    message: str


class RiskConfigResponse(BaseModel):
    """Response for GET /config/risk."""

    config: dict[str, Any]


class RiskConfigUpdateRequest(BaseModel):
    """Request body for PUT /config/risk."""

    defaults: dict[str, Any] | None = None
    portfolio: dict[str, Any] | None = None
    reason: str | None = None
    changed_by: str = "api"


class CircuitBreakerStateResponse(BaseModel):
    """Single circuit breaker state."""

    name: str
    tripped: bool
    tripped_at: datetime | None
    reason: str
    scope: str


class CircuitBreakersResponse(BaseModel):
    """Response for GET /circuit-breakers."""

    instrument_breakers: dict[str, list[CircuitBreakerStateResponse]]
    portfolio_breakers: list[CircuitBreakerStateResponse]
    system_breakers: list[CircuitBreakerStateResponse]
    any_tripped: bool
    kill_switch_active: bool


class ReconciliationResultResponse(BaseModel):
    """Single reconciliation result."""

    checked_at: datetime
    broker: str
    instrument: str
    status: str
    details: dict[str, Any]
    resolved: bool


class ReconciliationResponse(BaseModel):
    """Response for GET /reconciliation."""

    results: list[ReconciliationResultResponse]
    unresolved_count: int


class PauseResponse(BaseModel):
    """Response for pause/resume operations."""

    instrument: str
    paused: bool


class PausedListResponse(BaseModel):
    """Response for GET /trading/pause."""

    paused_instruments: list[str]


# ---------------------------------------------------------------------------
# TradingService — holds injected dependencies
# ---------------------------------------------------------------------------


class TradingService:
    """Facade for trading API endpoint logic."""

    def __init__(
        self,
        *,
        trade_store: TradeStore,
        circuit_breaker: CircuitBreakerManager,
        config_change_store: ConfigChangeStore,
        risk_config: RiskConfig,
        executors: list[OrderExecutor] | None = None,
    ) -> None:
        self._trade_store = trade_store
        self._circuit_breaker = circuit_breaker
        self._config_change_store = config_change_store
        self._risk_config = risk_config
        self._executors = executors or []

    @property
    def trade_store(self) -> TradeStore:
        return self._trade_store

    @property
    def circuit_breaker(self) -> CircuitBreakerManager:
        return self._circuit_breaker

    @property
    def config_change_store(self) -> ConfigChangeStore:
        return self._config_change_store

    @property
    def risk_config(self) -> RiskConfig:
        return self._risk_config

    @risk_config.setter
    def risk_config(self, value: RiskConfig) -> None:
        self._risk_config = value

    @property
    def executors(self) -> list[OrderExecutor]:
        return self._executors


# Module-level service
_service: TradingService | None = None

# In-memory pause state per instrument (v1 — lost on restart)
_paused_instruments: set[str] = set()
_SUPPORTED_INSTRUMENTS = {"EUR_USD", "BTC_USD"}


def configure(service: TradingService) -> None:
    """Configure the trading API service. Called at app startup or in tests."""
    global _service  # noqa: PLW0603
    _service = service


def _get_service() -> TradingService:
    if _service is None:
        raise HTTPException(status_code=503, detail="Trading service not configured")
    return _service


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _trade_to_response(trade: TradeRecord) -> TradeResponse:
    return TradeResponse(
        client_order_id=trade.client_order_id,
        broker_order_id=trade.broker_order_id,
        instrument=trade.instrument,
        broker=trade.broker,
        direction=trade.direction,
        signal_score=trade.signal_score,
        signal_type=trade.signal_type,
        signal_generator_id=trade.signal_generator_id,
        regime_label=trade.regime_label,
        entry_time=trade.entry_time,
        entry_price=trade.entry_price,
        exit_time=trade.exit_time,
        exit_price=trade.exit_price,
        quantity=trade.quantity,
        stop_loss_price=trade.stop_loss_price,
        status=trade.status,
        pnl=trade.pnl,
        commission=trade.commission,
        slippage=trade.slippage,
        exit_reason=trade.exit_reason,
        created_at=trade.created_at,
        updated_at=trade.updated_at,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/trades", response_model=TradesListResponse)
def get_trades(
    instrument: str | None = Query(default=None, description="Filter by instrument"),
    status: str | None = Query(default=None, description="Filter by status"),
    broker: str | None = Query(default=None, description="Filter by broker"),
    limit: int = Query(default=100, ge=1, le=1000, description="Max results"),
) -> TradesListResponse:
    """List trades with optional filters (§8.1)."""
    svc = _get_service()
    trades = svc.trade_store.list_trades(
        instrument=instrument, status=status, broker=broker, limit=limit,
    )
    return TradesListResponse(
        trades=[_trade_to_response(t) for t in trades],
        count=len(trades),
    )


@router.post("/kill", response_model=KillSwitchResponse)
def activate_kill_switch(req: KillSwitchActivateRequest) -> KillSwitchResponse:
    """Activate system-wide kill switch (§6.5)."""
    svc = _get_service()
    now = datetime.now(UTC)

    if svc.circuit_breaker.is_kill_switch_active():
        return KillSwitchResponse(
            active=True,
            action="no_change",
            positions_closed=0,
            message="Kill switch was already active",
        )

    svc.circuit_breaker.activate_kill_switch(req.reason)

    # Close all positions via executors
    total_closed = 0
    for executor in svc.executors:
        closed = executor.close_all_positions(req.reason)
        total_closed += len(closed)

    # Audit log
    svc.config_change_store.save_change(ConfigChangeEntry(
        changed_at=now,
        changed_by="api",
        section="kill_switch",
        instrument=None,
        old_value={"active": False},
        new_value={"active": True, "reason": req.reason},
        reason=req.reason,
    ))
    logger.critical("Kill switch activated via API: %s", req.reason)

    return KillSwitchResponse(
        active=True,
        action="activated",
        positions_closed=total_closed,
        message=f"Kill switch activated. {total_closed} positions closed.",
    )


@router.delete("/kill", response_model=KillSwitchResponse)
def deactivate_kill_switch(
    confirm: bool = Query(default=False, description="Must be true to confirm"),
) -> KillSwitchResponse:
    """Deactivate kill switch with confirmation (§6.5)."""
    svc = _get_service()
    now = datetime.now(UTC)

    if not confirm:
        raise HTTPException(
            status_code=400,
            detail="Kill switch deactivation requires confirm=true",
        )

    if not svc.circuit_breaker.is_kill_switch_active():
        return KillSwitchResponse(
            active=False,
            action="no_change",
            positions_closed=0,
            message="Kill switch was not active",
        )

    svc.circuit_breaker.deactivate_kill_switch()

    # Audit log
    svc.config_change_store.save_change(ConfigChangeEntry(
        changed_at=now,
        changed_by="api",
        section="kill_switch",
        instrument=None,
        old_value={"active": True},
        new_value={"active": False},
        reason="manual_deactivation",
    ))
    logger.info("Kill switch deactivated via API")

    return KillSwitchResponse(
        active=False,
        action="deactivated",
        positions_closed=0,
        message="Kill switch deactivated.",
    )


@router.get("/config/risk", response_model=RiskConfigResponse)
def get_risk_config() -> RiskConfigResponse:
    """Return current risk configuration (§6.1)."""
    svc = _get_service()
    return RiskConfigResponse(
        config=svc.risk_config.model_dump(mode="json"),
    )


@router.put("/config/risk", response_model=RiskConfigResponse)
def update_risk_config(req: RiskConfigUpdateRequest) -> RiskConfigResponse:
    """Update risk configuration with validation and audit logging (§6.1)."""
    svc = _get_service()
    now = datetime.now(UTC)

    # Snapshot old config
    old_config_dict = svc.risk_config.model_dump(mode="json")

    # Deep merge updates
    new_config_dict = dict(old_config_dict)
    if req.defaults:
        merged_defaults = dict(old_config_dict["defaults"])
        merged_defaults.update(req.defaults)
        new_config_dict["defaults"] = merged_defaults

    if req.portfolio:
        merged_portfolio = dict(old_config_dict["portfolio"])
        merged_portfolio.update(req.portfolio)
        new_config_dict["portfolio"] = merged_portfolio

    # Validate through Pydantic
    try:
        new_config = RiskConfig(**new_config_dict)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc

    # Apply
    svc.risk_config = new_config

    # Audit log
    svc.config_change_store.save_change(ConfigChangeEntry(
        changed_at=now,
        changed_by=req.changed_by,
        section="risk",
        instrument=None,
        old_value=old_config_dict,
        new_value=new_config.model_dump(mode="json"),
        reason=req.reason,
    ))

    logger.info("Risk config updated via API by %s: %s", req.changed_by, req.reason)

    return RiskConfigResponse(
        config=new_config.model_dump(mode="json"),
    )


# ---------------------------------------------------------------------------
# Circuit breaker snapshot endpoint
# ---------------------------------------------------------------------------


def _breaker_to_response(b: Any) -> CircuitBreakerStateResponse:
    return CircuitBreakerStateResponse(
        name=b.name,
        tripped=b.tripped,
        tripped_at=b.tripped_at,
        reason=b.reason,
        scope=b.scope,
    )


@router.get("/circuit-breakers", response_model=CircuitBreakersResponse)
def get_circuit_breakers() -> CircuitBreakersResponse:
    """Return current circuit breaker states (§6.5)."""
    svc = _get_service()
    snapshot = svc.circuit_breaker.get_snapshot()

    instrument_breakers: dict[str, list[CircuitBreakerStateResponse]] = {}
    for instrument, breakers in snapshot.instrument_breakers.items():
        instrument_breakers[instrument] = [_breaker_to_response(b) for b in breakers]

    return CircuitBreakersResponse(
        instrument_breakers=instrument_breakers,
        portfolio_breakers=[_breaker_to_response(b) for b in snapshot.portfolio_breakers],
        system_breakers=[_breaker_to_response(b) for b in snapshot.system_breakers],
        any_tripped=snapshot.any_tripped,
        kill_switch_active=svc.circuit_breaker.is_kill_switch_active(),
    )


# ---------------------------------------------------------------------------
# Reconciliation status endpoint
# ---------------------------------------------------------------------------


@router.get("/reconciliation", response_model=ReconciliationResponse)
def get_reconciliation_status() -> ReconciliationResponse:
    """Return latest reconciliation results (§5.12)."""
    svc = _get_service()

    # Use reconciliation store if available, otherwise return empty
    recon_store = getattr(svc, "_recon_store", None)
    if recon_store is not None and hasattr(recon_store, "get_unresolved"):
        unresolved = recon_store.get_unresolved()
        results = [
            ReconciliationResultResponse(
                checked_at=r.checked_at,
                broker=r.broker,
                instrument=r.instrument,
                status=r.status,
                details=r.details,
                resolved=r.resolved,
            )
            for r in unresolved
        ]
        return ReconciliationResponse(results=results, unresolved_count=len(results))

    return ReconciliationResponse(results=[], unresolved_count=0)


# ---------------------------------------------------------------------------
# Pause/resume per instrument
# ---------------------------------------------------------------------------


@router.put("/trading/pause/{instrument}", response_model=PauseResponse)
def pause_instrument(instrument: str) -> PauseResponse:
    """Pause signal execution for an instrument."""
    if instrument not in _SUPPORTED_INSTRUMENTS:
        raise HTTPException(status_code=404, detail=f"Unsupported instrument: {instrument}")
    _paused_instruments.add(instrument)
    logger.info("Instrument paused: %s", instrument)
    return PauseResponse(instrument=instrument, paused=True)


@router.delete("/trading/pause/{instrument}", response_model=PauseResponse)
def resume_instrument(instrument: str) -> PauseResponse:
    """Resume signal execution for an instrument."""
    if instrument not in _SUPPORTED_INSTRUMENTS:
        raise HTTPException(status_code=404, detail=f"Unsupported instrument: {instrument}")
    _paused_instruments.discard(instrument)
    logger.info("Instrument resumed: %s", instrument)
    return PauseResponse(instrument=instrument, paused=False)


@router.get("/trading/pause", response_model=PausedListResponse)
def list_paused_instruments() -> PausedListResponse:
    """List all paused instruments."""
    return PausedListResponse(paused_instruments=sorted(_paused_instruments))
