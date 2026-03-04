"""Model artifact listing API endpoints (T-404).

Exposes model version history and metadata for the admin dashboard.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from src.analysis.model_store import list_versions
from src.api.schemas import ModelArtifactResponse, ModelListResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["models"])

_SUPPORTED_INSTRUMENTS = {"EUR_USD", "BTC_USD"}
_MODEL_TYPES = ["bayesian", "xgboost", "meta_learner"]


def _models_dir() -> Path:
    return Path(os.getenv("NEWTON_MODELS_DIR", "models"))


@router.get("/models/{instrument}", response_model=ModelListResponse)
def get_models(
    instrument: str,
    model_type: str | None = Query(
        default=None,
        description="Filter by model type (bayesian, xgboost, meta_learner)",
    ),
) -> ModelListResponse:
    """List model artifact versions for an instrument.

    Returns metadata for all stored model versions, optionally filtered
    by model_type.
    """
    if instrument not in _SUPPORTED_INSTRUMENTS:
        raise HTTPException(status_code=404, detail=f"Unsupported instrument: {instrument}")

    base_dir = _models_dir()
    types_to_query = [model_type] if model_type else _MODEL_TYPES

    artifacts: list[ModelArtifactResponse] = []
    for mt in types_to_query:
        try:
            versions = list_versions(
                instrument=instrument,
                model_type=mt,
                base_dir=base_dir,
            )
            for v in versions:
                artifacts.append(
                    ModelArtifactResponse(
                        model_type=v.model_type,
                        instrument=v.instrument,
                        version=v.version,
                        training_date=v.training_date,
                        hyperparameters=v.hyperparameters,
                        performance_metrics=v.performance_metrics,
                        data_hash=v.data_hash,
                        artifact_hash=v.artifact_hash,
                    )
                )
        except (ValueError, FileNotFoundError):
            # No versions for this model_type — skip
            continue
        except Exception:
            logger.exception("Failed to list models for %s/%s", instrument, mt)
            continue

    return ModelListResponse(
        instrument=instrument,
        model_type=model_type,
        artifacts=artifacts,
        count=len(artifacts),
    )
