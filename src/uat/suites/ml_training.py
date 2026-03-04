"""ML Training UAT suite — feature engineering, walk-forward, model store, XGBoost."""

from __future__ import annotations

from src.uat.runner import UATTest

SUITE_ID = "ml_training"
SUITE_NAME = "ML Training"


def test_ml_01() -> str:
    """Feature engineering builds correct-shape feature matrix."""
    from datetime import datetime

    import numpy as np

    from src.analysis.feature_engineering import build_feature_matrix
    from src.uat.helpers import make_candles

    candles = make_candles(50, instrument="EUR_USD")

    # Synthetic indicator features for each timestamp
    indicator_features: dict[datetime, dict[str, float]] = {}
    for c in candles:
        indicator_features[c.time] = {
            "rsi_14": 50.0 + np.random.default_rng(42).uniform(-20, 20),
            "macd_12_26_9_line": 0.001,
            "macd_12_26_9_signal": 0.0005,
        }

    # Synthetic token sets
    token_sets: dict[datetime, frozenset[str]] = {}
    for c in candles:
        token_sets[c.time] = frozenset({"TOKEN_A"})

    selected_tokens = ("TOKEN_A",)
    lookback = 5

    matrix = build_feature_matrix(
        candles=candles,
        indicator_features=indicator_features,
        token_sets=token_sets,
        lookback_periods=lookback,
        selected_tokens=selected_tokens,
    )
    assert matrix.values.shape[0] > 0, "Should have rows"
    assert matrix.values.shape[1] > 0, "Should have columns"
    assert len(matrix.feature_names) == matrix.values.shape[1]
    assert matrix.instrument == "EUR_USD"
    return (
        f"Matrix shape: {matrix.values.shape}, "
        f"{len(matrix.feature_names)} features, instrument={matrix.instrument}"
    )


def test_ml_02() -> str:
    """Walk-forward generates non-overlapping folds with embargo."""
    from src.analysis.walk_forward import WalkForwardConfig, generate_folds, validate_no_lookahead

    config = WalkForwardConfig(
        train_periods=40,
        test_periods=15,
        step_periods=15,
        embargo_periods=2,
        min_folds=4,
    )
    folds = generate_folds(n_samples=150, config=config)
    assert len(folds) >= config.min_folds, (
        f"Expected >= {config.min_folds} folds, got {len(folds)}"
    )

    # Verify no overlap and embargo
    validate_no_lookahead(folds, embargo_periods=config.embargo_periods)

    # Check fold boundaries
    for fold in folds:
        assert fold.test_start_idx >= fold.train_end_idx + config.embargo_periods, (
            f"Fold {fold.fold_number}: test starts too close to train end"
        )
    return f"{len(folds)} folds, embargo={config.embargo_periods}, no lookahead"


def test_ml_03() -> str:
    """Model artifact save/load cycle with integrity check."""
    import tempfile
    from datetime import UTC, datetime
    from pathlib import Path

    from src.analysis.model_store import ModelArtifact, load_model, save_model

    artifact = ModelArtifact(
        model_type="xgboost",
        instrument="EUR_USD",
        version=1,
        training_date=datetime(2025, 6, 1, tzinfo=UTC),
        hyperparameters={"max_depth": 6, "learning_rate": 0.1},
        performance_metrics={"auc_roc": 0.62},
        data_hash="abc123",
        artifact_hash="",  # Will be computed by save
    )
    model_bytes = b"fake-model-bytes-for-testing"

    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir)
        saved_path = save_model(
            model_bytes=model_bytes, artifact=artifact, base_dir=base,
        )
        assert saved_path.exists(), "Saved model file should exist"

        loaded_bytes, loaded_artifact = load_model(
            instrument="EUR_USD",
            model_type="xgboost",
            version=1,
            base_dir=base,
        )
        assert loaded_bytes == model_bytes, "Loaded bytes should match saved bytes"
        assert loaded_artifact.instrument == "EUR_USD"
        assert loaded_artifact.version == 1
    return f"Save/load cycle passed, path={saved_path.name}"


def test_ml_04() -> str:
    """XGBoost training produces model with valid predictions."""
    import numpy as np
    import xgboost as xgb

    from src.analysis.xgboost_trainer import predict_xgboost

    # Train a tiny model directly (bypass walk-forward for speed)
    rng = np.random.default_rng(42)
    n_samples, n_features = 100, 5
    X = rng.standard_normal((n_samples, n_features))
    y = (X[:, 0] > 0).astype(np.int32)  # Simple decision boundary

    dtrain = xgb.DMatrix(X, label=y)
    params = {
        "objective": "binary:logistic",
        "max_depth": 3,
        "seed": 42,
        "verbosity": 0,
    }
    booster = xgb.train(params, dtrain, num_boost_round=10, verbose_eval=False)
    model_bytes = bytes(booster.save_raw(raw_format="ubj"))

    # Test prediction
    test_vector = rng.standard_normal(n_features)
    prob = predict_xgboost(model_bytes=model_bytes, feature_vector=test_vector)
    assert 0 <= prob <= 1, f"Prediction {prob} should be in [0, 1]"
    return f"Prediction={prob:.4f} from {n_features}-feature vector"


TESTS = [
    UATTest(id="ML-01", name="Feature engineering builds correct-shape matrix",
            suite=SUITE_ID, fn=test_ml_01),
    UATTest(id="ML-02", name="Walk-forward generates folds with embargo",
            suite=SUITE_ID, fn=test_ml_02),
    UATTest(id="ML-03", name="Model artifact save/load with integrity check",
            suite=SUITE_ID, fn=test_ml_03),
    UATTest(id="ML-04", name="XGBoost prediction produces valid probability",
            suite=SUITE_ID, fn=test_ml_04),
]
