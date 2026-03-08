"""Strategy management API endpoints (T-702).

Provides CRUD access to per-instrument strategy configurations with
file-based version history.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.api.schemas import utc_now

logger = logging.getLogger(__name__)

router = APIRouter(tags=["strategy"])

ROOT_DIR = Path(__file__).resolve().parents[3]
STRATEGY_DIR = ROOT_DIR / "config" / "strategies"


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class StrategyConfigResponse(BaseModel):
    """Current strategy configuration for an instrument."""

    instrument: str
    config: dict[str, Any]
    version: int
    updated_at: datetime


class StrategyVersionEntry(BaseModel):
    """A single version history entry."""

    version: int
    config: dict[str, Any]
    notes: str | None = None
    created_at: datetime | None = None


class StrategyVersionsResponse(BaseModel):
    """Version history for an instrument's strategy."""

    instrument: str
    versions: list[StrategyVersionEntry]
    count: int


class StrategyActivateRequest(BaseModel):
    """Request body for activating a strategy version."""

    version: int = Field(..., ge=1)
    notes: str | None = None


class StrategyActivateResponse(BaseModel):
    """Response after activating a strategy version."""

    instrument: str
    activated_version: int
    message: str
    activated_at: datetime


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _config_path(instrument: str) -> Path:
    """Return the path to an instrument's active strategy config."""
    return STRATEGY_DIR / f"{instrument}_strategy.json"


def _versions_dir(instrument: str) -> Path:
    """Return the path to an instrument's version history directory."""
    return STRATEGY_DIR / "versions" / instrument


def _read_config(instrument: str) -> dict[str, Any]:
    """Read the active strategy config from disk.

    Raises HTTPException 404 if the config file does not exist.
    """
    path = _config_path(instrument)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"No strategy config for instrument: {instrument}")
    result: dict[str, Any] = json.loads(path.read_text())
    return result


def _current_version(instrument: str) -> int:
    """Determine the current version number from the version history directory.

    Returns 0 if no versions exist (i.e. only the initial config is present).
    """
    vdir = _versions_dir(instrument)
    if not vdir.exists():
        return 0
    version_files = list(vdir.glob("v*.json"))
    if not version_files:
        return 0
    versions = []
    for f in version_files:
        try:
            versions.append(int(f.stem[1:]))  # "v3" -> 3
        except ValueError:
            continue
    return max(versions) if versions else 0


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/strategy/{instrument}", response_model=StrategyConfigResponse)
def get_strategy(instrument: str) -> StrategyConfigResponse:
    """Return the current active strategy configuration for an instrument."""
    config = _read_config(instrument)
    version = _current_version(instrument)
    path = _config_path(instrument)
    mtime = datetime.fromtimestamp(path.stat().st_mtime)

    return StrategyConfigResponse(
        instrument=instrument,
        config=config,
        version=version,
        updated_at=mtime,
    )


@router.get("/strategy/{instrument}/versions", response_model=StrategyVersionsResponse)
def get_strategy_versions(instrument: str) -> StrategyVersionsResponse:
    """Return the version history for an instrument's strategy configuration."""
    # Validate instrument has a config
    _read_config(instrument)

    vdir = _versions_dir(instrument)
    if not vdir.exists():
        return StrategyVersionsResponse(instrument=instrument, versions=[], count=0)

    entries: list[StrategyVersionEntry] = []
    for vfile in sorted(vdir.glob("v*.json")):
        try:
            ver_num = int(vfile.stem[1:])
        except ValueError:
            continue
        ver_data = json.loads(vfile.read_text())
        mtime = datetime.fromtimestamp(vfile.stat().st_mtime)
        entries.append(
            StrategyVersionEntry(
                version=ver_data.get("version", ver_num),
                config=ver_data.get("config", ver_data),
                notes=ver_data.get("notes"),
                created_at=mtime,
            )
        )

    # Sort descending (newest first)
    entries.sort(key=lambda e: e.version, reverse=True)

    return StrategyVersionsResponse(
        instrument=instrument,
        versions=entries,
        count=len(entries),
    )


@router.put("/strategy/{instrument}/activate", response_model=StrategyActivateResponse)
def activate_strategy_version(
    instrument: str, body: StrategyActivateRequest
) -> StrategyActivateResponse:
    """Activate a specific strategy version, making it the current config.

    Before overwriting, the current active config is saved as a new version
    to preserve history.
    """
    # Validate instrument
    current_config = _read_config(instrument)

    # Find the requested version
    vdir = _versions_dir(instrument)
    version_file = vdir / f"v{body.version}.json"
    if not version_file.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Version {body.version} not found for instrument {instrument}",
        )

    ver_data = json.loads(version_file.read_text())
    new_config = ver_data.get("config", ver_data)

    # Save current active config as a new version before overwriting
    next_version = _current_version(instrument) + 1
    vdir.mkdir(parents=True, exist_ok=True)
    save_entry = {
        "version": next_version,
        "config": current_config,
        "notes": f"Auto-saved before activating version {body.version}",
    }
    save_path = vdir / f"v{next_version}.json"
    save_path.write_text(json.dumps(save_entry, indent=2))

    # Write the activated version as the new active config
    config_path = _config_path(instrument)
    config_path.write_text(json.dumps(new_config, indent=2))

    now = utc_now()
    logger.info(
        "Strategy version %d activated for %s (previous saved as v%d)",
        body.version,
        instrument,
        next_version,
    )

    return StrategyActivateResponse(
        instrument=instrument,
        activated_version=body.version,
        message=f"Strategy version {body.version} activated for {instrument}",
        activated_at=now,
    )
