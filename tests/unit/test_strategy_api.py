"""Tests for the strategy management API endpoints (T-702)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.app import app

client = TestClient(app)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_STRATEGY = {
    "instrument": "EUR_USD",
    "events": ["EURUSD_UP_1PCT_24H"],
    "token_config": "config/classifications/EUR_USD_classifications.json",
    "token_selection": {"method": "mutual_information", "top_n": 20, "jaccard_threshold": 0.85},
    "bayesian": {"calibration": "isotonic", "posterior_cap": 0.9, "laplace_alpha": 1},
    "ml_model": {"type": "xgboost", "lookback_periods": 24, "hyperparams": "auto"},
    "meta_learner": {"type": "logistic_regression", "min_samples": 100},
    "thresholds": {"strong_buy": 0.65, "buy": 0.55, "sell": 0.4},
    "risk_overrides": {},
    "performance_overrides": {},
}


@pytest.fixture()
def strategy_dir(tmp_path: Path) -> Path:
    """Create a temporary strategy config directory with a sample config."""
    strategies = tmp_path / "strategies"
    strategies.mkdir()
    config_file = strategies / "EUR_USD_strategy.json"
    config_file.write_text(json.dumps(SAMPLE_STRATEGY, indent=2))
    return strategies


# ---------------------------------------------------------------------------
# GET /strategy/{instrument} — current config
# ---------------------------------------------------------------------------


def test_get_strategy_valid_instrument(strategy_dir: Path) -> None:
    """GET returns the current strategy config for a valid instrument."""
    with patch("src.api.v1.strategy.STRATEGY_DIR", strategy_dir):
        resp = client.get("/api/v1/strategy/EUR_USD")

    assert resp.status_code == 200
    data = resp.json()
    assert data["instrument"] == "EUR_USD"
    assert data["config"]["thresholds"]["strong_buy"] == 0.65
    assert "version" in data


def test_get_strategy_invalid_instrument(strategy_dir: Path) -> None:
    """GET returns 404 for an instrument without a strategy config."""
    with patch("src.api.v1.strategy.STRATEGY_DIR", strategy_dir):
        resp = client.get("/api/v1/strategy/INVALID_PAIR")

    assert resp.status_code == 404


def test_get_strategy_response_shape(strategy_dir: Path) -> None:
    """Response includes all required fields."""
    with patch("src.api.v1.strategy.STRATEGY_DIR", strategy_dir):
        resp = client.get("/api/v1/strategy/EUR_USD")

    assert resp.status_code == 200
    data = resp.json()
    required = {"instrument", "config", "version", "updated_at"}
    assert required.issubset(data.keys())


# ---------------------------------------------------------------------------
# GET /strategy/{instrument}/versions — version history
# ---------------------------------------------------------------------------


def test_get_versions_empty(strategy_dir: Path) -> None:
    """GET versions returns empty list when no versions directory exists."""
    with patch("src.api.v1.strategy.STRATEGY_DIR", strategy_dir):
        resp = client.get("/api/v1/strategy/EUR_USD/versions")

    assert resp.status_code == 200
    data = resp.json()
    assert data["instrument"] == "EUR_USD"
    assert data["versions"] == []
    assert data["count"] == 0


def test_get_versions_with_history(strategy_dir: Path) -> None:
    """GET versions returns version list when versions exist on disk."""
    versions_dir = strategy_dir / "versions" / "EUR_USD"
    versions_dir.mkdir(parents=True)

    v1 = {"version": 1, "config": SAMPLE_STRATEGY, "notes": "Initial version"}
    (versions_dir / "v1.json").write_text(json.dumps(v1))

    v2_config = {**SAMPLE_STRATEGY, "thresholds": {"strong_buy": 0.7, "buy": 0.6, "sell": 0.45}}
    v2 = {"version": 2, "config": v2_config, "notes": "Adjusted thresholds"}
    (versions_dir / "v2.json").write_text(json.dumps(v2))

    with patch("src.api.v1.strategy.STRATEGY_DIR", strategy_dir):
        resp = client.get("/api/v1/strategy/EUR_USD/versions")

    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 2
    assert len(data["versions"]) == 2
    # Versions should be sorted descending (newest first)
    assert data["versions"][0]["version"] == 2
    assert data["versions"][1]["version"] == 1


def test_get_versions_invalid_instrument(strategy_dir: Path) -> None:
    """GET versions returns 404 for unknown instrument."""
    with patch("src.api.v1.strategy.STRATEGY_DIR", strategy_dir):
        resp = client.get("/api/v1/strategy/INVALID_PAIR/versions")

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PUT /strategy/{instrument}/activate — activate a version
# ---------------------------------------------------------------------------


def test_activate_version_success(strategy_dir: Path) -> None:
    """PUT activate copies a versioned config to become the active config."""
    # Create a version to activate
    versions_dir = strategy_dir / "versions" / "EUR_USD"
    versions_dir.mkdir(parents=True)

    new_config = {**SAMPLE_STRATEGY, "thresholds": {"strong_buy": 0.7, "buy": 0.6, "sell": 0.45}}
    v1 = {"version": 1, "config": new_config, "notes": "Test version"}
    (versions_dir / "v1.json").write_text(json.dumps(v1))

    with patch("src.api.v1.strategy.STRATEGY_DIR", strategy_dir):
        resp = client.put(
            "/api/v1/strategy/EUR_USD/activate",
            json={"version": 1},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["instrument"] == "EUR_USD"
    assert data["activated_version"] == 1
    assert data["message"] == "Strategy version 1 activated for EUR_USD"

    # Verify the active config was updated
    active_config = json.loads((strategy_dir / "EUR_USD_strategy.json").read_text())
    assert active_config["thresholds"]["strong_buy"] == 0.7


def test_activate_version_not_found(strategy_dir: Path) -> None:
    """PUT activate returns 404 when the requested version doesn't exist."""
    with patch("src.api.v1.strategy.STRATEGY_DIR", strategy_dir):
        resp = client.put(
            "/api/v1/strategy/EUR_USD/activate",
            json={"version": 99},
        )

    assert resp.status_code == 404


def test_activate_invalid_instrument(strategy_dir: Path) -> None:
    """PUT activate returns 404 for unknown instrument."""
    with patch("src.api.v1.strategy.STRATEGY_DIR", strategy_dir):
        resp = client.put(
            "/api/v1/strategy/INVALID_PAIR/activate",
            json={"version": 1},
        )

    assert resp.status_code == 404


def test_activate_saves_previous_as_version(strategy_dir: Path) -> None:
    """PUT activate saves the current config as a new version before overwriting."""
    versions_dir = strategy_dir / "versions" / "EUR_USD"
    versions_dir.mkdir(parents=True)

    new_config = {**SAMPLE_STRATEGY, "thresholds": {"strong_buy": 0.7, "buy": 0.6, "sell": 0.45}}
    v1 = {"version": 1, "config": new_config, "notes": "New thresholds"}
    (versions_dir / "v1.json").write_text(json.dumps(v1))

    with patch("src.api.v1.strategy.STRATEGY_DIR", strategy_dir):
        resp = client.put(
            "/api/v1/strategy/EUR_USD/activate",
            json={"version": 1, "notes": "Activating v1"},
        )

    assert resp.status_code == 200

    # The previous active config should have been saved as a version
    version_files = sorted(versions_dir.glob("v*.json"))
    assert len(version_files) >= 2  # v1 + the saved previous config


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_activate_request_requires_version() -> None:
    """PUT activate requires a version field in the request body."""
    resp = client.put(
        "/api/v1/strategy/EUR_USD/activate",
        json={},
    )
    assert resp.status_code == 422
