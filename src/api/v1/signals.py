"""Additive Signal API endpoints (SPEC.v4 scaffolding, Stage 1-compatible)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from src.analysis.signal_contract import FeatureSnapshot
from src.trading.signal import SignalRouter, build_default_router

router = APIRouter(tags=["signals"])
_signal_router: SignalRouter = build_default_router()


_SCAFFOLD_WARNING = (
    "This endpoint returns scaffold data with hardcoded features. "
    "Real signal generation requires Stage 2+ implementation."
)


@router.get("/signals/generators")
def list_signal_generators() -> dict[str, Any]:
    generator_ids = _signal_router.registry.list_generators()
    payload = []
    for generator_id in generator_ids:
        cfg = _signal_router.generators[generator_id]
        payload.append({"id": generator_id, "enabled": cfg.enabled, "parameters": cfg.parameters})
    return {"scaffold": True, "count": len(payload), "generators": payload}


@router.get("/signals/{instrument}")
def get_current_signal(
    instrument: str,
    generator: str | None = Query(default=None, description="Optional generator override"),
) -> dict[str, Any]:
    if instrument not in _signal_router.routing:
        raise HTTPException(status_code=404, detail=f"Unsupported instrument: {instrument}")

    features = FeatureSnapshot(
        instrument=instrument,
        interval="1h",
        time=datetime.now(tz=UTC),
        values={"score": 0.5, "confidence": 0.5, "bayesian_score": 0.5, "ml_score": 0.5},
        metadata={"mode": "scaffold"},
    )
    signal = _signal_router.route_signal(
        instrument=instrument,
        features=features,
        generator_override=generator,
    )
    return {
        "scaffold": True,
        "warning": _SCAFFOLD_WARNING,
        "instrument": signal.instrument,
        "action": signal.action,
        "probability": signal.probability,
        "confidence": signal.confidence,
        "component_scores": signal.component_scores,
        "metadata": signal.metadata,
        "generated_at": signal.generated_at,
        "generator_id": signal.generator_id,
    }
