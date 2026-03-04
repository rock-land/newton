"""Tests for the model listing API endpoint (T-404)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from src.app import app

client = TestClient(app)


def test_models_endpoint_rejects_unsupported_instrument() -> None:
    """Unsupported instruments should return 404."""
    resp = client.get("/api/v1/models/INVALID_PAIR")
    assert resp.status_code == 404


def test_models_endpoint_empty_dir() -> None:
    """When the models directory is empty, return an empty list."""
    with tempfile.TemporaryDirectory() as tmpdir:
        import os

        saved = os.environ.get("NEWTON_MODELS_DIR")
        os.environ["NEWTON_MODELS_DIR"] = tmpdir
        try:
            resp = client.get("/api/v1/models/EUR_USD")
        finally:
            if saved is not None:
                os.environ["NEWTON_MODELS_DIR"] = saved
            else:
                os.environ.pop("NEWTON_MODELS_DIR", None)

    assert resp.status_code == 200
    data = resp.json()
    assert data["instrument"] == "EUR_USD"
    assert data["artifacts"] == []
    assert data["count"] == 0


def test_models_endpoint_returns_stored_artifacts() -> None:
    """When model artifacts exist on disk, they should be listed."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a fake model artifact
        model_dir = Path(tmpdir) / "EUR_USD" / "bayesian"
        model_dir.mkdir(parents=True)
        model_dir.joinpath("v1.model").write_bytes(b"fake-model-bytes")
        meta = {
            "model_type": "bayesian",
            "instrument": "EUR_USD",
            "version": 1,
            "training_date": "2026-01-01T00:00:00+00:00",
            "hyperparameters": {"alpha": 1.0},
            "performance_metrics": {"auc_roc": 0.72},
            "data_hash": "abc123",
            "artifact_hash": "def456",
        }
        model_dir.joinpath("v1.meta.json").write_text(json.dumps(meta, indent=2))

        import os

        saved = os.environ.get("NEWTON_MODELS_DIR")
        os.environ["NEWTON_MODELS_DIR"] = tmpdir
        try:
            resp = client.get("/api/v1/models/EUR_USD")
        finally:
            if saved is not None:
                os.environ["NEWTON_MODELS_DIR"] = saved
            else:
                os.environ.pop("NEWTON_MODELS_DIR", None)

    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    art = data["artifacts"][0]
    assert art["model_type"] == "bayesian"
    assert art["version"] == 1
    assert art["performance_metrics"]["auc_roc"] == 0.72


def test_models_endpoint_filter_by_model_type() -> None:
    """When model_type query param is provided, only that type is returned."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create bayesian + xgboost models
        for mt in ("bayesian", "xgboost"):
            d = Path(tmpdir) / "BTC_USD" / mt
            d.mkdir(parents=True)
            d.joinpath("v1.model").write_bytes(b"bytes")
            meta = {
                "model_type": mt,
                "instrument": "BTC_USD",
                "version": 1,
                "training_date": "2026-01-01T00:00:00+00:00",
                "hyperparameters": {},
                "performance_metrics": {},
                "data_hash": "h",
                "artifact_hash": "h",
            }
            d.joinpath("v1.meta.json").write_text(json.dumps(meta))

        import os

        saved = os.environ.get("NEWTON_MODELS_DIR")
        os.environ["NEWTON_MODELS_DIR"] = tmpdir
        try:
            resp = client.get("/api/v1/models/BTC_USD?model_type=xgboost")
        finally:
            if saved is not None:
                os.environ["NEWTON_MODELS_DIR"] = saved
            else:
                os.environ.pop("NEWTON_MODELS_DIR", None)

    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    assert data["artifacts"][0]["model_type"] == "xgboost"
    assert data["model_type"] == "xgboost"


def test_models_endpoint_response_shape() -> None:
    """Verify the response shape includes all required fields."""
    resp = client.get("/api/v1/models/EUR_USD")
    assert resp.status_code == 200
    data = resp.json()
    required_keys = {"instrument", "model_type", "artifacts", "count"}
    assert required_keys.issubset(data.keys())
