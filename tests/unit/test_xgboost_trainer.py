"""Tests for XGBoost model training and inference (T-304)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from src.analysis.feature_engineering import FeatureMatrix
from src.analysis.walk_forward import WalkForwardConfig
from src.analysis.xgboost_trainer import (
    TrainingResult,
    XGBoostHyperparameters,
    predict_xgboost,
    train_xgboost,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_synthetic_data(
    n_samples: int = 250,
    n_features: int = 5,
    random_seed: int = 42,
) -> tuple[FeatureMatrix, tuple[int, ...]]:
    """Synthetic feature matrix with labels correlated to first feature."""
    rng = np.random.default_rng(random_seed)
    X = rng.standard_normal((n_samples, n_features))
    logits = X[:, 0] * 1.5 + rng.standard_normal(n_samples) * 0.5
    labels = tuple(int(v > 0) for v in logits)
    base = datetime(2024, 1, 1, tzinfo=UTC)
    timestamps = tuple(base + timedelta(hours=i) for i in range(n_samples))
    feature_names = tuple(f"f{i}" for i in range(n_features))
    fm = FeatureMatrix(
        timestamps=timestamps,
        feature_names=feature_names,
        values=X,
        instrument="EUR_USD",
    )
    return fm, labels


def _small_wf_config(min_folds: int = 2) -> WalkForwardConfig:
    return WalkForwardConfig(
        train_periods=100,
        test_periods=30,
        step_periods=30,
        embargo_periods=5,
        min_folds=min_folds,
    )


# ---------------------------------------------------------------------------
# XGBoostHyperparameters frozen
# ---------------------------------------------------------------------------

class TestXGBoostHyperparameters:
    def test_frozen(self) -> None:
        hp = XGBoostHyperparameters()
        with pytest.raises(AttributeError):
            hp.max_depth = 99  # type: ignore[misc]

    def test_defaults(self) -> None:
        hp = XGBoostHyperparameters()
        assert hp.max_depth == 6
        assert hp.learning_rate == 0.1
        assert hp.n_estimators == 100


# ---------------------------------------------------------------------------
# TrainingResult frozen
# ---------------------------------------------------------------------------

class TestTrainingResult:
    def test_frozen(self) -> None:
        fm, labels = _make_synthetic_data()
        result = train_xgboost(
            feature_matrix=fm,
            labels=labels,
            walk_forward_config=_small_wf_config(),
            n_optuna_trials=2,
            early_stopping_rounds=5,
        )
        with pytest.raises(AttributeError):
            result.below_auc_threshold = True  # type: ignore[misc]


# ---------------------------------------------------------------------------
# train_xgboost
# ---------------------------------------------------------------------------

class TestTrainXGBoost:
    def test_basic_training(self) -> None:
        fm, labels = _make_synthetic_data()
        result = train_xgboost(
            feature_matrix=fm,
            labels=labels,
            walk_forward_config=_small_wf_config(),
            n_optuna_trials=2,
            early_stopping_rounds=5,
        )
        assert isinstance(result, TrainingResult)
        assert result.instrument == "EUR_USD"
        assert result.production_model_bytes is not None
        assert len(result.production_model_bytes) > 0
        assert isinstance(result.production_hyperparameters, XGBoostHyperparameters)

    def test_walk_forward_folds_populated(self) -> None:
        fm, labels = _make_synthetic_data()
        result = train_xgboost(
            feature_matrix=fm,
            labels=labels,
            walk_forward_config=_small_wf_config(),
            n_optuna_trials=2,
            early_stopping_rounds=5,
        )
        wf = result.walk_forward_result
        assert len(wf.folds) >= 2
        assert len(wf.oof_predictions) > 0
        assert len(wf.oof_labels) > 0

    def test_mean_auc_roc_computed(self) -> None:
        fm, labels = _make_synthetic_data()
        result = train_xgboost(
            feature_matrix=fm,
            labels=labels,
            walk_forward_config=_small_wf_config(),
            n_optuna_trials=2,
            early_stopping_rounds=5,
        )
        assert result.walk_forward_result.mean_auc_roc > 0.0

    def test_below_auc_threshold_true_returns_none_model(self) -> None:
        """SPEC §5.6: below AUC threshold → disable ML (production_model_bytes=None)."""
        fm, labels = _make_synthetic_data()
        result = train_xgboost(
            feature_matrix=fm,
            labels=labels,
            walk_forward_config=_small_wf_config(),
            n_optuna_trials=2,
            early_stopping_rounds=5,
            auc_threshold=0.99,
        )
        assert result.below_auc_threshold is True
        assert result.production_model_bytes is None

    def test_below_auc_threshold_false(self) -> None:
        fm, labels = _make_synthetic_data()
        result = train_xgboost(
            feature_matrix=fm,
            labels=labels,
            walk_forward_config=_small_wf_config(),
            n_optuna_trials=2,
            early_stopping_rounds=5,
            auc_threshold=0.0,
        )
        assert result.below_auc_threshold is False
        assert result.production_model_bytes is not None
        assert len(result.production_model_bytes) > 0

    def test_production_model_predicts(self) -> None:
        fm, labels = _make_synthetic_data()
        result = train_xgboost(
            feature_matrix=fm,
            labels=labels,
            walk_forward_config=_small_wf_config(),
            n_optuna_trials=2,
            early_stopping_rounds=5,
        )
        assert result.production_model_bytes is not None
        prob = predict_xgboost(
            model_bytes=result.production_model_bytes,
            feature_vector=fm.values[0],
        )
        assert 0.0 <= prob <= 1.0

    def test_predictions_in_probability_range(self) -> None:
        fm, labels = _make_synthetic_data()
        result = train_xgboost(
            feature_matrix=fm,
            labels=labels,
            walk_forward_config=_small_wf_config(),
            n_optuna_trials=2,
            early_stopping_rounds=5,
        )
        for pred in result.walk_forward_result.oof_predictions:
            assert 0.0 <= pred <= 1.0

    def test_oof_labels_are_binary(self) -> None:
        fm, labels = _make_synthetic_data()
        result = train_xgboost(
            feature_matrix=fm,
            labels=labels,
            walk_forward_config=_small_wf_config(),
            n_optuna_trials=2,
            early_stopping_rounds=5,
        )
        for label in result.walk_forward_result.oof_labels:
            assert label in (0, 1)

    def test_hyperparameters_in_valid_range(self) -> None:
        fm, labels = _make_synthetic_data()
        result = train_xgboost(
            feature_matrix=fm,
            labels=labels,
            walk_forward_config=_small_wf_config(),
            n_optuna_trials=3,
            early_stopping_rounds=5,
        )
        hp = result.production_hyperparameters
        assert 3 <= hp.max_depth <= 10
        assert 0.01 <= hp.learning_rate <= 0.3
        assert 0.5 <= hp.subsample <= 1.0
        assert 0.5 <= hp.colsample_bytree <= 1.0

    def test_reproducible_with_seed(self) -> None:
        fm, labels = _make_synthetic_data()
        r1 = train_xgboost(
            feature_matrix=fm, labels=labels,
            walk_forward_config=_small_wf_config(),
            n_optuna_trials=2, early_stopping_rounds=5, random_seed=42,
        )
        r2 = train_xgboost(
            feature_matrix=fm, labels=labels,
            walk_forward_config=_small_wf_config(),
            n_optuna_trials=2, early_stopping_rounds=5, random_seed=42,
        )
        assert r1.walk_forward_result.mean_auc_roc == r2.walk_forward_result.mean_auc_roc


# ---------------------------------------------------------------------------
# predict_xgboost
# ---------------------------------------------------------------------------

class TestPredictXGBoost:
    def test_round_trip(self) -> None:
        import xgboost as xgb

        X = np.array([[1.0, 2.0], [3.0, 4.0], [5.0, 6.0], [7.0, 8.0]])
        y = np.array([0, 0, 1, 1])
        dtrain = xgb.DMatrix(X, label=y)
        booster = xgb.train(
            {"objective": "binary:logistic", "verbosity": 0},
            dtrain, num_boost_round=10,
        )
        model_bytes = booster.save_raw(raw_format="ubj")

        prob = predict_xgboost(model_bytes=model_bytes, feature_vector=X[2])
        assert 0.0 <= prob <= 1.0

    def test_different_inputs_different_outputs(self) -> None:
        import xgboost as xgb

        rng = np.random.default_rng(42)
        X = rng.standard_normal((50, 3))
        y = (X[:, 0] > 0).astype(int)
        dtrain = xgb.DMatrix(X, label=y)
        booster = xgb.train(
            {"objective": "binary:logistic", "verbosity": 0},
            dtrain, num_boost_round=20,
        )
        model_bytes = booster.save_raw(raw_format="ubj")

        p_high = predict_xgboost(
            model_bytes=model_bytes,
            feature_vector=np.array([3.0, 0.0, 0.0]),
        )
        p_low = predict_xgboost(
            model_bytes=model_bytes,
            feature_vector=np.array([-3.0, 0.0, 0.0]),
        )
        assert p_high != p_low
        assert p_high > p_low

    def test_cached_deserialization(self) -> None:
        """Second call with same model bytes should use cached booster."""
        import xgboost as xgb
        from src.analysis.xgboost_trainer import _get_booster

        X = np.array([[1.0, 2.0], [3.0, 4.0], [5.0, 6.0], [7.0, 8.0]])
        y = np.array([0, 0, 1, 1])
        dtrain = xgb.DMatrix(X, label=y)
        booster = xgb.train(
            {"objective": "binary:logistic", "verbosity": 0},
            dtrain, num_boost_round=10,
        )
        model_bytes = bytes(booster.save_raw(raw_format="ubj"))

        # Clear cache
        _get_booster.cache_clear()
        b1 = _get_booster(model_bytes)
        b2 = _get_booster(model_bytes)
        assert b1 is b2  # Same object (cached)
        info = _get_booster.cache_info()
        assert info.hits >= 1


# ---------------------------------------------------------------------------
# MLV1Generator with real model
# ---------------------------------------------------------------------------

class TestMLV1GeneratorRealInference:
    @staticmethod
    def _train_tiny_model() -> tuple[bytes, tuple[str, ...]]:
        import xgboost as xgb

        X = np.array([
            [1.0, 2.0], [3.0, 4.0], [5.0, 6.0], [7.0, 8.0],
            [1.5, 2.5], [3.5, 4.5], [5.5, 6.5], [7.5, 8.5],
        ])
        y = np.array([0, 0, 1, 1, 0, 0, 1, 1])
        dtrain = xgb.DMatrix(X, label=y)
        booster = xgb.train(
            {"objective": "binary:logistic", "verbosity": 0},
            dtrain, num_boost_round=10,
        )
        return booster.save_raw(raw_format="ubj"), ("f0", "f1")

    def test_real_inference_path(self) -> None:
        from src.analysis.signal_contract import FeatureSnapshot, GeneratorConfig
        from src.trading.signal import MLV1Generator

        model_bytes, feature_names = self._train_tiny_model()
        gen = MLV1Generator()
        features = FeatureSnapshot(
            instrument="EUR_USD", interval="H1",
            time=datetime(2024, 6, 1, tzinfo=UTC),
            values={"f0": 5.0, "f1": 6.0, "confidence": 0.8},
            metadata={},
        )
        config = GeneratorConfig(
            enabled=True,
            parameters={"model_bytes": model_bytes, "feature_names": feature_names},
        )
        signal = gen.generate("EUR_USD", features, config)
        assert signal.generator_id == "ml_v1"
        assert 0.0 <= signal.probability <= 1.0
        assert signal.metadata["source"] == "xgboost_engine"
        assert signal.component_scores["ml"] == signal.probability

    def test_scaffold_fallback_without_model(self) -> None:
        from src.analysis.signal_contract import FeatureSnapshot, GeneratorConfig
        from src.trading.signal import MLV1Generator

        gen = MLV1Generator()
        features = FeatureSnapshot(
            instrument="EUR_USD", interval="H1",
            time=datetime(2024, 6, 1, tzinfo=UTC),
            values={"score": 0.7, "confidence": 0.5},
            metadata={},
        )
        config = GeneratorConfig(enabled=True, parameters={})
        signal = gen.generate("EUR_USD", features, config)
        assert signal.metadata["source"] == "scaffold"
        assert signal.probability == pytest.approx(0.7)

    def test_missing_feature_raises(self) -> None:
        from src.analysis.signal_contract import FeatureSnapshot, GeneratorConfig
        from src.trading.signal import MLV1Generator, RecoverableSignalError

        model_bytes, feature_names = self._train_tiny_model()
        gen = MLV1Generator()
        features = FeatureSnapshot(
            instrument="EUR_USD", interval="H1",
            time=datetime(2024, 6, 1, tzinfo=UTC),
            values={"f0": 5.0},  # f1 missing
            metadata={},
        )
        config = GeneratorConfig(
            enabled=True,
            parameters={"model_bytes": model_bytes, "feature_names": feature_names},
        )
        with pytest.raises(RecoverableSignalError, match="Missing feature"):
            gen.generate("EUR_USD", features, config)

    def test_generate_batch_with_model(self) -> None:
        from src.analysis.signal_contract import FeatureSnapshot, GeneratorConfig
        from src.trading.signal import MLV1Generator

        model_bytes, feature_names = self._train_tiny_model()
        gen = MLV1Generator()
        base = datetime(2024, 6, 1, tzinfo=UTC)
        snapshots = [
            FeatureSnapshot(
                instrument="EUR_USD", interval="H1",
                time=base + timedelta(hours=i),
                values={"f0": float(i), "f1": float(i + 1), "confidence": 0.5},
                metadata={},
            )
            for i in range(3)
        ]
        config = GeneratorConfig(
            enabled=True,
            parameters={"model_bytes": model_bytes, "feature_names": feature_names},
        )
        results = gen.generate_batch("EUR_USD", snapshots, config)
        assert len(results) == 3
        for _, sig in results:
            assert sig.metadata["source"] == "xgboost_engine"
            assert 0.0 <= sig.probability <= 1.0
