"""Model artifact storage and versioning (T-302).

Save/load trained model artifacts to disk with SHA-256 integrity
verification, metadata tracking, and per-instrument version management.

Storage layout:
    {base_dir}/{instrument}/{model_type}/v{version}.model
    {base_dir}/{instrument}/{model_type}/v{version}.meta.json
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class ModelIntegrityError(Exception):
    """Raised when a loaded model's SHA-256 hash does not match its metadata."""


@dataclass(frozen=True)
class ModelArtifact:
    """Immutable metadata for a trained model artifact."""

    model_type: str
    instrument: str
    version: int
    training_date: datetime
    hyperparameters: dict[str, Any]
    performance_metrics: dict[str, float]
    data_hash: str
    artifact_hash: str


def _compute_hash(data: bytes) -> str:
    """Compute SHA-256 hex digest of raw bytes."""
    return hashlib.sha256(data).hexdigest()


def _model_dir(base_dir: Path, instrument: str, model_type: str) -> Path:
    return base_dir / instrument / model_type


def _model_path(base_dir: Path, instrument: str, model_type: str, version: int) -> Path:
    return _model_dir(base_dir, instrument, model_type) / f"v{version}.model"


def _meta_path(base_dir: Path, instrument: str, model_type: str, version: int) -> Path:
    return _model_dir(base_dir, instrument, model_type) / f"v{version}.meta.json"


def _serialize_artifact(artifact: ModelArtifact) -> str:
    """Serialize ModelArtifact to JSON string."""
    d = asdict(artifact)
    d["training_date"] = artifact.training_date.isoformat()
    return json.dumps(d, indent=2, sort_keys=True)


def _deserialize_artifact(raw: str) -> ModelArtifact:
    """Deserialize JSON string to ModelArtifact."""
    d = json.loads(raw)
    d["training_date"] = datetime.fromisoformat(d["training_date"]).replace(tzinfo=UTC)
    return ModelArtifact(**d)


def save_model(
    *,
    model_bytes: bytes,
    artifact: ModelArtifact,
    base_dir: Path,
) -> Path:
    """Save model bytes and metadata to disk.

    Computes SHA-256 of model_bytes and stores it in the metadata sidecar.
    Creates parent directories as needed.

    Returns the path to the saved model file.
    """
    artifact_hash = _compute_hash(model_bytes)

    # Build artifact with computed hash
    stored = ModelArtifact(
        model_type=artifact.model_type,
        instrument=artifact.instrument,
        version=artifact.version,
        training_date=artifact.training_date,
        hyperparameters=artifact.hyperparameters,
        performance_metrics=artifact.performance_metrics,
        data_hash=artifact.data_hash,
        artifact_hash=artifact_hash,
    )

    model_file = _model_path(base_dir, stored.instrument, stored.model_type, stored.version)
    meta_file = _meta_path(base_dir, stored.instrument, stored.model_type, stored.version)

    model_file.parent.mkdir(parents=True, exist_ok=True)
    model_file.write_bytes(model_bytes)
    meta_file.write_text(_serialize_artifact(stored))

    return model_file


def load_model(
    *,
    instrument: str,
    model_type: str,
    version: int | None,
    base_dir: Path,
) -> tuple[bytes, ModelArtifact]:
    """Load model bytes and metadata from disk.

    If version is None, loads the latest version.
    Verifies SHA-256 hash on load — raises ModelIntegrityError on mismatch.

    Raises:
        FileNotFoundError: If the model or metadata file does not exist.
        ModelIntegrityError: If the loaded bytes don't match the stored hash.
    """
    if version is None:
        latest = get_latest_version(
            instrument=instrument, model_type=model_type, base_dir=base_dir
        )
        if latest == 0:
            raise FileNotFoundError(
                f"No model versions found for {instrument}/{model_type} in {base_dir}"
            )
        version = latest

    model_file = _model_path(base_dir, instrument, model_type, version)
    meta_file = _meta_path(base_dir, instrument, model_type, version)

    if not model_file.exists():
        raise FileNotFoundError(f"Model file not found: {model_file}")
    if not meta_file.exists():
        raise FileNotFoundError(f"Metadata file not found: {meta_file}")

    model_bytes = model_file.read_bytes()
    artifact = _deserialize_artifact(meta_file.read_text())

    actual_hash = _compute_hash(model_bytes)
    if actual_hash != artifact.artifact_hash:
        raise ModelIntegrityError(
            f"Integrity hash mismatch for {instrument}/{model_type}/v{version}: "
            f"expected {artifact.artifact_hash[:16]}..., got {actual_hash[:16]}..."
        )

    return model_bytes, artifact


def get_latest_version(
    *,
    instrument: str,
    model_type: str,
    base_dir: Path,
) -> int:
    """Return the highest version number for the given instrument/model_type.

    Returns 0 if no versions exist.
    """
    model_dir = _model_dir(base_dir, instrument, model_type)
    if not model_dir.exists():
        return 0

    versions: list[int] = []
    for f in model_dir.iterdir():
        m = re.match(r"^v(\d+)\.model$", f.name)
        if m:
            versions.append(int(m.group(1)))

    return max(versions) if versions else 0


def list_versions(
    *,
    instrument: str,
    model_type: str,
    base_dir: Path,
) -> list[ModelArtifact]:
    """Return metadata for all versions, sorted ascending by version number."""
    model_dir = _model_dir(base_dir, instrument, model_type)
    if not model_dir.exists():
        return []

    artifacts: list[ModelArtifact] = []
    for f in sorted(model_dir.iterdir()):
        if f.suffix == ".model":
            meta_file = f.with_suffix(".meta.json")
            if meta_file.exists():
                artifacts.append(_deserialize_artifact(meta_file.read_text()))

    artifacts.sort(key=lambda a: a.version)
    return artifacts
