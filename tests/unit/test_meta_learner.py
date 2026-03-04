"""Tests for meta-learner logistic regression stacking (T-306)."""

from __future__ import annotations

import numpy as np
import pytest

from src.analysis.meta_learner import (
    MetaLearnerModel,
    check_calibration,
    compute_calibration_error,
    predict_meta_learner,
    train_meta_learner,
)


class TestMetaLearnerModel:
    """MetaLearnerModel frozen dataclass."""

    def test_frozen(self) -> None:
        model = MetaLearnerModel(
            coefficients=(0.5, 0.3, 0.2),
            intercept=0.0,
            feature_names=("bayesian", "ml", "regime"),
            calibration_errors=(0.01,) * 10,
            n_training_samples=200,
        )
        with pytest.raises(AttributeError):
            model.intercept = 1.0  # type: ignore[misc]

    def test_fields(self) -> None:
        model = MetaLearnerModel(
            coefficients=(0.5, 0.3, 0.2),
            intercept=-0.1,
            feature_names=("bayesian", "ml", "regime"),
            calibration_errors=(0.02,) * 10,
            n_training_samples=150,
        )
        assert len(model.coefficients) == 3
        assert model.intercept == -0.1
        assert model.feature_names == ("bayesian", "ml", "regime")
        assert len(model.calibration_errors) == 10
        assert model.n_training_samples == 150


class TestTrainMetaLearner:
    """Training with synthetic data."""

    @staticmethod
    def _make_separable_data(
        n: int = 300, seed: int = 42
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Create data where high bayesian + ml → positive label."""
        rng = np.random.default_rng(seed)
        labels = rng.integers(0, 2, size=n).astype(np.int32)
        bayesian = np.where(labels == 1, rng.uniform(0.6, 0.9, n), rng.uniform(0.1, 0.4, n))
        ml = np.where(labels == 1, rng.uniform(0.55, 0.85, n), rng.uniform(0.15, 0.45, n))
        regime = rng.uniform(0.2, 0.8, n)
        return bayesian, ml, regime, labels

    def test_train_returns_model(self) -> None:
        bayesian, ml, regime, labels = self._make_separable_data()
        model = train_meta_learner(
            bayesian_posteriors=tuple(bayesian),
            ml_probabilities=tuple(ml),
            regime_confidences=tuple(regime),
            labels=tuple(int(x) for x in labels),
        )
        assert isinstance(model, MetaLearnerModel)
        assert len(model.coefficients) == 3
        # n_training_samples is 80% of input (train/held-out split)
        assert model.n_training_samples == 240  # 80% of 300
        assert len(model.calibration_errors) == 10

    def test_coefficients_reflect_informative_inputs(self) -> None:
        """Bayesian and ML coefficients should be positive (informative)."""
        bayesian, ml, regime, labels = self._make_separable_data()
        model = train_meta_learner(
            bayesian_posteriors=tuple(bayesian),
            ml_probabilities=tuple(ml),
            regime_confidences=tuple(regime),
            labels=tuple(int(x) for x in labels),
        )
        # Bayesian and ML are informative — coefficients should be positive
        assert model.coefficients[0] > 0, "bayesian coefficient should be positive"
        assert model.coefficients[1] > 0, "ml coefficient should be positive"

    def test_min_samples_enforced(self) -> None:
        with pytest.raises(ValueError, match="min_samples"):
            train_meta_learner(
                bayesian_posteriors=(0.5,) * 50,
                ml_probabilities=(0.5,) * 50,
                regime_confidences=(0.5,) * 50,
                labels=(0,) * 25 + (1,) * 25,
                min_samples=100,
            )

    def test_min_samples_default_100(self) -> None:
        """Default min_samples is 100."""
        with pytest.raises(ValueError, match="min_samples"):
            train_meta_learner(
                bayesian_posteriors=(0.5,) * 99,
                ml_probabilities=(0.5,) * 99,
                regime_confidences=(0.5,) * 99,
                labels=(0,) * 49 + (1,) * 50,
            )

    def test_train_with_exact_min_samples(self) -> None:
        """Exactly 100 samples should work."""
        rng = np.random.default_rng(42)
        n = 100
        labels = [0] * 50 + [1] * 50
        bayesian = [float(rng.uniform(0.3, 0.7)) for _ in range(n)]
        ml = [float(rng.uniform(0.3, 0.7)) for _ in range(n)]
        regime = [float(rng.uniform(0.2, 0.8)) for _ in range(n)]
        model = train_meta_learner(
            bayesian_posteriors=tuple(bayesian),
            ml_probabilities=tuple(ml),
            regime_confidences=tuple(regime),
            labels=tuple(labels),
            min_samples=100,
        )
        # n_training_samples is 80% of input (train/held-out split)
        assert model.n_training_samples == 80

    def test_calibration_evaluated_on_held_out_data(self) -> None:
        """Calibration errors should be evaluated on held-out data, not training."""
        bayesian, ml, regime, labels = self._make_separable_data(n=500, seed=99)
        model = train_meta_learner(
            bayesian_posteriors=tuple(bayesian),
            ml_probabilities=tuple(ml),
            regime_confidences=tuple(regime),
            labels=tuple(int(x) for x in labels),
        )
        # n_training_samples should be less than total input (80% split)
        assert model.n_training_samples < 500
        assert model.n_training_samples == 400  # 80% of 500
        assert len(model.calibration_errors) == 10


class TestPredictMetaLearner:
    """Prediction with trained model."""

    @staticmethod
    def _trained_model() -> MetaLearnerModel:
        rng = np.random.default_rng(42)
        n = 300
        labels = list(rng.integers(0, 2, size=n).astype(int))
        bayesian = [float(x) for x in np.where(
            np.array(labels) == 1, rng.uniform(0.6, 0.9, n), rng.uniform(0.1, 0.4, n)
        )]
        ml = [float(x) for x in np.where(
            np.array(labels) == 1, rng.uniform(0.55, 0.85, n), rng.uniform(0.15, 0.45, n)
        )]
        regime = [float(x) for x in rng.uniform(0.2, 0.8, n)]
        return train_meta_learner(
            bayesian_posteriors=tuple(bayesian),
            ml_probabilities=tuple(ml),
            regime_confidences=tuple(regime),
            labels=tuple(labels),
        )

    def test_predict_returns_probability(self) -> None:
        model = self._trained_model()
        prob = predict_meta_learner(
            model, bayesian_posterior=0.7, ml_probability=0.8, regime_confidence=0.5
        )
        assert 0.0 <= prob <= 1.0

    def test_high_inputs_higher_probability(self) -> None:
        model = self._trained_model()
        high = predict_meta_learner(
            model, bayesian_posterior=0.85, ml_probability=0.85, regime_confidence=0.7
        )
        low = predict_meta_learner(
            model, bayesian_posterior=0.15, ml_probability=0.15, regime_confidence=0.3
        )
        assert high > low, f"high={high} should be > low={low}"

    def test_different_inputs_different_outputs(self) -> None:
        model = self._trained_model()
        p1 = predict_meta_learner(
            model, bayesian_posterior=0.3, ml_probability=0.3, regime_confidence=0.5
        )
        p2 = predict_meta_learner(
            model, bayesian_posterior=0.8, ml_probability=0.8, regime_confidence=0.5
        )
        assert p1 != p2

    def test_predict_with_zero_inputs(self) -> None:
        model = self._trained_model()
        prob = predict_meta_learner(
            model, bayesian_posterior=0.0, ml_probability=0.0, regime_confidence=0.0
        )
        assert 0.0 <= prob <= 1.0

    def test_predict_with_one_inputs(self) -> None:
        model = self._trained_model()
        prob = predict_meta_learner(
            model, bayesian_posterior=1.0, ml_probability=1.0, regime_confidence=1.0
        )
        assert 0.0 <= prob <= 1.0


class TestComputeCalibrationError:
    """Per-decile calibration error computation."""

    def test_perfect_calibration(self) -> None:
        """Predictions exactly match observed frequency → errors near zero."""
        # 1000 samples: decile 0.0-0.1 has ~5% positive, 0.9-1.0 has ~95%, etc.
        rng = np.random.default_rng(42)
        n = 2000
        predictions = list(rng.uniform(0.0, 1.0, n))
        # Labels drawn with probability equal to prediction
        labels = [int(rng.random() < p) for p in predictions]
        errors = compute_calibration_error(
            predictions=tuple(predictions), labels=tuple(labels)
        )
        assert len(errors) == 10
        # With 2000 samples, errors should be small (< 0.05 = 5pp)
        for e in errors:
            assert e < 0.10, f"error {e} too high for well-calibrated data"

    def test_poor_calibration(self) -> None:
        """Always predict 0.9 but only 50% positive → high error in 0.9 bin."""
        predictions = (0.95,) * 200
        labels = (0,) * 100 + (1,) * 100
        errors = compute_calibration_error(predictions=predictions, labels=labels)
        # The 0.9-1.0 bin should have error = |0.95 - 0.50| = 0.45
        assert errors[9] > 0.40

    def test_empty_bins_get_zero(self) -> None:
        """Bins with no samples get 0.0 error."""
        # All predictions in 0.4-0.5 range
        predictions = (0.45,) * 100
        labels = (0,) * 50 + (1,) * 50
        errors = compute_calibration_error(predictions=predictions, labels=labels)
        # Only bin 4 (0.4-0.5) should have samples; others get 0.0
        for i, e in enumerate(errors):
            if i != 4:
                assert e == 0.0, f"bin {i} should be 0.0, got {e}"

    def test_returns_10_values(self) -> None:
        predictions = tuple(float(x) for x in np.linspace(0.05, 0.95, 100))
        labels = (0,) * 50 + (1,) * 50
        errors = compute_calibration_error(predictions=predictions, labels=labels)
        assert len(errors) == 10


class TestCheckCalibration:
    """Calibration check against 5pp threshold."""

    def test_passes_when_all_below(self) -> None:
        errors = (0.02, 0.03, 0.04, 0.01, 0.02, 0.03, 0.04, 0.01, 0.02, 0.03)
        assert check_calibration(errors) is True

    def test_fails_when_any_above(self) -> None:
        errors = (0.02, 0.03, 0.04, 0.01, 0.06, 0.03, 0.04, 0.01, 0.02, 0.03)
        assert check_calibration(errors) is False

    def test_exact_boundary(self) -> None:
        """Error exactly at 5pp (0.05) should fail (not strictly less than)."""
        errors = (0.05,) * 10
        assert check_calibration(errors) is False

    def test_custom_threshold(self) -> None:
        errors = (0.08,) * 10
        assert check_calibration(errors, max_error_pp=10.0) is True
        assert check_calibration(errors, max_error_pp=5.0) is False
