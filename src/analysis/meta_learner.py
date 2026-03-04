"""Meta-learner logistic regression stacking (T-306).

Combines Bayesian posterior, ML probability, and regime confidence into
a single calibrated probability via logistic regression trained on
out-of-fold walk-forward predictions.

SPEC §5.7: Logistic regression stacking.  Inputs: Bayesian posterior,
ML probability, current regime confidence.  Calibration < 5pp per decile
(§9.5).
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass

import numpy as np
from sklearn.linear_model import LogisticRegression

logger = logging.getLogger(__name__)

_FEATURE_NAMES: tuple[str, ...] = ("bayesian", "ml", "regime")


@dataclass(frozen=True)
class MetaLearnerModel:
    """Trained meta-learner parameters.

    Stores raw logistic regression coefficients (not the sklearn object)
    for clean serialization via the model store.
    """

    coefficients: tuple[float, ...]
    intercept: float
    feature_names: tuple[str, ...]
    calibration_errors: tuple[float, ...]
    n_training_samples: int


def train_meta_learner(
    *,
    bayesian_posteriors: tuple[float, ...],
    ml_probabilities: tuple[float, ...],
    regime_confidences: tuple[float, ...],
    labels: tuple[int, ...],
    min_samples: int = 100,
) -> MetaLearnerModel:
    """Train logistic regression meta-learner on OOF predictions.

    Args:
        bayesian_posteriors: Bayesian posterior probabilities per timestamp.
        ml_probabilities: ML (XGBoost) probabilities per timestamp.
        regime_confidences: Regime detection confidence per timestamp.
        labels: Binary event labels (0/1) per timestamp.
        min_samples: Minimum samples required (default 100 per SPEC §5.7).

    Returns:
        Frozen MetaLearnerModel with coefficients and calibration stats.

    Raises:
        ValueError: If fewer than min_samples are provided.
    """
    n = len(bayesian_posteriors)
    if n < min_samples:
        raise ValueError(
            f"Insufficient training data: {n} samples, min_samples={min_samples} required"
        )

    X = np.column_stack([bayesian_posteriors, ml_probabilities, regime_confidences])
    y = np.array(labels, dtype=np.int32)

    clf = LogisticRegression(solver="lbfgs", max_iter=1000)
    clf.fit(X, y)

    coefficients = tuple(float(c) for c in clf.coef_[0])
    intercept = float(clf.intercept_[0])

    # Compute calibration on training data (OOF predictions)
    predictions = tuple(float(p) for p in clf.predict_proba(X)[:, 1])
    calibration_errors = compute_calibration_error(
        predictions=predictions, labels=labels,
    )

    passes = check_calibration(calibration_errors)
    if not passes:
        logger.warning(
            "Meta-learner calibration check FAILED: max error %.4f > 5pp. "
            "Consider retraining with more data.",
            max(calibration_errors),
        )

    logger.info(
        "Meta-learner trained: %d samples, coefficients=%s, intercept=%.4f, "
        "max calibration error=%.4f",
        n, coefficients, intercept, max(calibration_errors),
    )

    return MetaLearnerModel(
        coefficients=coefficients,
        intercept=intercept,
        feature_names=_FEATURE_NAMES,
        calibration_errors=calibration_errors,
        n_training_samples=n,
    )


def predict_meta_learner(
    model: MetaLearnerModel,
    *,
    bayesian_posterior: float,
    ml_probability: float,
    regime_confidence: float,
) -> float:
    """Predict combined probability using trained meta-learner.

    Applies logistic regression: sigmoid(coefficients · features + intercept).

    Returns:
        Probability in [0, 1].
    """
    features = (bayesian_posterior, ml_probability, regime_confidence)
    logit = sum(c * f for c, f in zip(model.coefficients, features)) + model.intercept
    return _sigmoid(logit)


def compute_calibration_error(
    *,
    predictions: tuple[float, ...],
    labels: tuple[int, ...],
) -> tuple[float, ...]:
    """Compute per-decile calibration error.

    Bins predictions into 10 deciles [0-0.1, 0.1-0.2, ..., 0.9-1.0].
    For each bin: |mean_predicted - observed_frequency|.
    Empty bins get 0.0.

    Returns:
        10-element tuple of absolute errors per decile.
    """
    preds = np.array(predictions)
    labs = np.array(labels)

    errors: list[float] = []
    for i in range(10):
        lo = i * 0.1
        hi = (i + 1) * 0.1
        if i == 9:
            mask = (preds >= lo) & (preds <= hi)
        else:
            mask = (preds >= lo) & (preds < hi)

        if mask.sum() == 0:
            errors.append(0.0)
            continue

        mean_pred = float(preds[mask].mean())
        observed_freq = float(labs[mask].mean())
        errors.append(abs(mean_pred - observed_freq))

    return tuple(errors)


def check_calibration(
    calibration_errors: tuple[float, ...],
    *,
    max_error_pp: float = 5.0,
) -> bool:
    """Check if all decile calibration errors are below threshold.

    Args:
        calibration_errors: Per-decile absolute errors.
        max_error_pp: Maximum allowed error in percentage points (default 5.0).

    Returns:
        True if all errors are strictly below the threshold.
    """
    threshold = max_error_pp / 100.0
    passed = all(e < threshold for e in calibration_errors)
    if not passed:
        offending = [
            (i, e) for i, e in enumerate(calibration_errors) if e >= threshold
        ]
        logger.warning(
            "Calibration check failed: %d decile(s) exceed %.1fpp threshold: %s",
            len(offending),
            max_error_pp,
            [(f"decile_{i}", f"{e:.4f}") for i, e in offending],
        )
    return passed


def _sigmoid(x: float) -> float:
    """Numerically stable sigmoid."""
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    exp_x = math.exp(x)
    return exp_x / (1.0 + exp_x)
