"""Tests for model artifact storage and versioning (T-302)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from src.analysis.model_store import (
    ModelArtifact,
    ModelIntegrityError,
    get_latest_version,
    list_versions,
    load_model,
    save_model,
)


def _make_artifact(
    *,
    instrument: str = "EUR_USD",
    model_type: str = "xgboost",
    version: int = 1,
    artifact_hash: str = "",
) -> ModelArtifact:
    return ModelArtifact(
        model_type=model_type,
        instrument=instrument,
        version=version,
        training_date=datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC),
        hyperparameters={"max_depth": 6, "learning_rate": 0.1},
        performance_metrics={"auc_roc": 0.58, "accuracy": 0.62},
        data_hash="abc123def456",
        artifact_hash=artifact_hash,
    )


SAMPLE_MODEL_BYTES = b"fake-xgboost-model-binary-data-v1"


# --- ModelArtifact frozen ---


class TestModelArtifactFrozen:
    def test_frozen(self) -> None:
        artifact = _make_artifact()
        with pytest.raises(AttributeError):
            artifact.instrument = "BTC_USD"  # type: ignore[misc]

    def test_fields_present(self) -> None:
        artifact = _make_artifact()
        assert artifact.model_type == "xgboost"
        assert artifact.instrument == "EUR_USD"
        assert artifact.version == 1
        assert artifact.training_date.tzinfo == UTC
        assert isinstance(artifact.hyperparameters, dict)
        assert isinstance(artifact.performance_metrics, dict)
        assert isinstance(artifact.data_hash, str)
        assert isinstance(artifact.artifact_hash, str)


# --- save_model ---


class TestSaveModel:
    def test_save_creates_files(self, tmp_path: Path) -> None:
        artifact = _make_artifact(version=1)
        result_path = save_model(
            model_bytes=SAMPLE_MODEL_BYTES,
            artifact=artifact,
            base_dir=tmp_path,
        )
        assert result_path.exists()
        assert result_path.name == "v1.model"
        meta_path = result_path.with_suffix(".meta.json")
        assert meta_path.exists()

    def test_save_writes_correct_bytes(self, tmp_path: Path) -> None:
        artifact = _make_artifact(version=1)
        result_path = save_model(
            model_bytes=SAMPLE_MODEL_BYTES,
            artifact=artifact,
            base_dir=tmp_path,
        )
        assert result_path.read_bytes() == SAMPLE_MODEL_BYTES

    def test_save_metadata_contains_hash(self, tmp_path: Path) -> None:
        artifact = _make_artifact(version=1)
        result_path = save_model(
            model_bytes=SAMPLE_MODEL_BYTES,
            artifact=artifact,
            base_dir=tmp_path,
        )
        meta_path = result_path.with_suffix(".meta.json")
        meta = json.loads(meta_path.read_text())
        assert "artifact_hash" in meta
        assert len(meta["artifact_hash"]) == 64  # SHA-256 hex digest

    def test_save_directory_structure(self, tmp_path: Path) -> None:
        artifact = _make_artifact(instrument="BTC_USD", model_type="bayesian", version=3)
        result_path = save_model(
            model_bytes=SAMPLE_MODEL_BYTES,
            artifact=artifact,
            base_dir=tmp_path,
        )
        expected_dir = tmp_path / "BTC_USD" / "bayesian"
        assert result_path.parent == expected_dir

    def test_save_creates_parent_dirs(self, tmp_path: Path) -> None:
        base = tmp_path / "deep" / "nested" / "models"
        artifact = _make_artifact(version=1)
        result_path = save_model(
            model_bytes=SAMPLE_MODEL_BYTES,
            artifact=artifact,
            base_dir=base,
        )
        assert result_path.exists()

    def test_save_returns_artifact_with_hash(self, tmp_path: Path) -> None:
        artifact = _make_artifact(version=1, artifact_hash="")
        result_path = save_model(
            model_bytes=SAMPLE_MODEL_BYTES,
            artifact=artifact,
            base_dir=tmp_path,
        )
        meta = json.loads(result_path.with_suffix(".meta.json").read_text())
        # Hash should be computed from model bytes, not empty
        assert meta["artifact_hash"] != ""


# --- load_model ---


class TestLoadModel:
    def test_load_round_trip(self, tmp_path: Path) -> None:
        artifact = _make_artifact(version=1)
        save_model(model_bytes=SAMPLE_MODEL_BYTES, artifact=artifact, base_dir=tmp_path)
        loaded_bytes, loaded_artifact = load_model(
            instrument="EUR_USD",
            model_type="xgboost",
            version=1,
            base_dir=tmp_path,
        )
        assert loaded_bytes == SAMPLE_MODEL_BYTES
        assert loaded_artifact.instrument == "EUR_USD"
        assert loaded_artifact.model_type == "xgboost"
        assert loaded_artifact.version == 1

    def test_load_latest_version(self, tmp_path: Path) -> None:
        for v in (1, 2, 3):
            data = f"model-v{v}".encode()
            artifact = _make_artifact(version=v)
            save_model(model_bytes=data, artifact=artifact, base_dir=tmp_path)
        loaded_bytes, loaded_artifact = load_model(
            instrument="EUR_USD",
            model_type="xgboost",
            version=None,
            base_dir=tmp_path,
        )
        assert loaded_bytes == b"model-v3"
        assert loaded_artifact.version == 3

    def test_load_specific_version(self, tmp_path: Path) -> None:
        for v in (1, 2, 3):
            data = f"model-v{v}".encode()
            artifact = _make_artifact(version=v)
            save_model(model_bytes=data, artifact=artifact, base_dir=tmp_path)
        loaded_bytes, loaded_artifact = load_model(
            instrument="EUR_USD",
            model_type="xgboost",
            version=2,
            base_dir=tmp_path,
        )
        assert loaded_bytes == b"model-v2"
        assert loaded_artifact.version == 2

    def test_load_integrity_error(self, tmp_path: Path) -> None:
        artifact = _make_artifact(version=1)
        result_path = save_model(
            model_bytes=SAMPLE_MODEL_BYTES, artifact=artifact, base_dir=tmp_path
        )
        # Corrupt the model file
        result_path.write_bytes(b"corrupted-data")
        with pytest.raises(ModelIntegrityError, match="hash mismatch"):
            load_model(
                instrument="EUR_USD",
                model_type="xgboost",
                version=1,
                base_dir=tmp_path,
            )

    def test_load_missing_model_file(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_model(
                instrument="EUR_USD",
                model_type="xgboost",
                version=1,
                base_dir=tmp_path,
            )

    def test_load_missing_metadata_file(self, tmp_path: Path) -> None:
        artifact = _make_artifact(version=1)
        result_path = save_model(
            model_bytes=SAMPLE_MODEL_BYTES, artifact=artifact, base_dir=tmp_path
        )
        # Remove the metadata file
        result_path.with_suffix(".meta.json").unlink()
        with pytest.raises(FileNotFoundError):
            load_model(
                instrument="EUR_USD",
                model_type="xgboost",
                version=1,
                base_dir=tmp_path,
            )

    def test_load_no_versions_exist(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_model(
                instrument="EUR_USD",
                model_type="xgboost",
                version=None,
                base_dir=tmp_path,
            )

    def test_load_preserves_metadata(self, tmp_path: Path) -> None:
        artifact = _make_artifact(version=1)
        save_model(model_bytes=SAMPLE_MODEL_BYTES, artifact=artifact, base_dir=tmp_path)
        _, loaded = load_model(
            instrument="EUR_USD",
            model_type="xgboost",
            version=1,
            base_dir=tmp_path,
        )
        assert loaded.hyperparameters == {"max_depth": 6, "learning_rate": 0.1}
        assert loaded.performance_metrics == {"auc_roc": 0.58, "accuracy": 0.62}
        assert loaded.data_hash == "abc123def456"
        assert loaded.training_date == datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC)


# --- get_latest_version ---


class TestGetLatestVersion:
    def test_no_versions(self, tmp_path: Path) -> None:
        result = get_latest_version(
            instrument="EUR_USD", model_type="xgboost", base_dir=tmp_path
        )
        assert result == 0

    def test_single_version(self, tmp_path: Path) -> None:
        artifact = _make_artifact(version=1)
        save_model(model_bytes=SAMPLE_MODEL_BYTES, artifact=artifact, base_dir=tmp_path)
        result = get_latest_version(
            instrument="EUR_USD", model_type="xgboost", base_dir=tmp_path
        )
        assert result == 1

    def test_multiple_versions(self, tmp_path: Path) -> None:
        for v in (1, 2, 3):
            artifact = _make_artifact(version=v)
            save_model(model_bytes=b"data", artifact=artifact, base_dir=tmp_path)
        result = get_latest_version(
            instrument="EUR_USD", model_type="xgboost", base_dir=tmp_path
        )
        assert result == 3

    def test_non_sequential_versions(self, tmp_path: Path) -> None:
        for v in (1, 5, 3):
            artifact = _make_artifact(version=v)
            save_model(model_bytes=b"data", artifact=artifact, base_dir=tmp_path)
        result = get_latest_version(
            instrument="EUR_USD", model_type="xgboost", base_dir=tmp_path
        )
        assert result == 5


# --- list_versions ---


class TestListVersions:
    def test_empty(self, tmp_path: Path) -> None:
        result = list_versions(
            instrument="EUR_USD", model_type="xgboost", base_dir=tmp_path
        )
        assert result == []

    def test_returns_sorted(self, tmp_path: Path) -> None:
        for v in (3, 1, 2):
            artifact = _make_artifact(version=v)
            save_model(model_bytes=b"data", artifact=artifact, base_dir=tmp_path)
        result = list_versions(
            instrument="EUR_USD", model_type="xgboost", base_dir=tmp_path
        )
        assert len(result) == 3
        assert [a.version for a in result] == [1, 2, 3]

    def test_multiple_instruments_isolated(self, tmp_path: Path) -> None:
        for inst in ("EUR_USD", "BTC_USD"):
            artifact = _make_artifact(instrument=inst, version=1)
            save_model(model_bytes=b"data", artifact=artifact, base_dir=tmp_path)
        eur = list_versions(instrument="EUR_USD", model_type="xgboost", base_dir=tmp_path)
        btc = list_versions(instrument="BTC_USD", model_type="xgboost", base_dir=tmp_path)
        assert len(eur) == 1
        assert len(btc) == 1
        assert eur[0].instrument == "EUR_USD"
        assert btc[0].instrument == "BTC_USD"

    def test_multiple_model_types_isolated(self, tmp_path: Path) -> None:
        for mt in ("xgboost", "bayesian"):
            artifact = _make_artifact(model_type=mt, version=1)
            save_model(model_bytes=b"data", artifact=artifact, base_dir=tmp_path)
        xgb = list_versions(instrument="EUR_USD", model_type="xgboost", base_dir=tmp_path)
        bay = list_versions(instrument="EUR_USD", model_type="bayesian", base_dir=tmp_path)
        assert len(xgb) == 1
        assert len(bay) == 1


# --- Path sanitization (T-306-FIX3) ---


class TestPathSanitization:
    def test_valid_instrument_names(self, tmp_path: Path) -> None:
        """Standard instrument names are accepted."""
        for name in ("EUR_USD", "BTC_USD", "ETH-USDT", "SP500"):
            artifact = _make_artifact(instrument=name, version=1)
            # Should not raise
            save_model(model_bytes=b"data", artifact=artifact, base_dir=tmp_path)

    def test_valid_model_types(self, tmp_path: Path) -> None:
        for name in ("xgboost", "bayesian", "meta-learner"):
            artifact = _make_artifact(model_type=name, version=1)
            save_model(model_bytes=b"data", artifact=artifact, base_dir=tmp_path)

    def test_path_traversal_instrument_raises(self, tmp_path: Path) -> None:
        """Path traversal in instrument should be rejected."""
        artifact = _make_artifact(instrument="../etc", version=1)
        with pytest.raises(ValueError, match="Invalid"):
            save_model(model_bytes=b"data", artifact=artifact, base_dir=tmp_path)

    def test_path_traversal_model_type_raises(self, tmp_path: Path) -> None:
        artifact = _make_artifact(model_type="../../passwd", version=1)
        with pytest.raises(ValueError, match="Invalid"):
            save_model(model_bytes=b"data", artifact=artifact, base_dir=tmp_path)

    def test_slash_in_name_raises(self, tmp_path: Path) -> None:
        artifact = _make_artifact(instrument="foo/bar", version=1)
        with pytest.raises(ValueError, match="Invalid"):
            save_model(model_bytes=b"data", artifact=artifact, base_dir=tmp_path)

    def test_dot_dot_in_name_raises(self, tmp_path: Path) -> None:
        artifact = _make_artifact(instrument="..", version=1)
        with pytest.raises(ValueError, match="Invalid"):
            save_model(model_bytes=b"data", artifact=artifact, base_dir=tmp_path)

    def test_load_rejects_path_traversal(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="Invalid"):
            load_model(
                instrument="../etc",
                model_type="xgboost",
                version=1,
                base_dir=tmp_path,
            )
