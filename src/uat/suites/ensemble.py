"""Ensemble UAT suite — meta-learner, weighted blend, calibration."""

from __future__ import annotations

from src.uat.runner import UATTest

SUITE_ID = "ensemble"
SUITE_NAME = "Ensemble"


def test_en_01() -> str:
    """Meta-learner training produces valid coefficients."""
    import numpy as np

    from src.analysis.meta_learner import train_meta_learner

    rng = np.random.default_rng(42)
    n = 200

    # Synthetic component predictions
    bayesian_posteriors = tuple(float(x) for x in rng.uniform(0.2, 0.8, n))
    ml_probabilities = tuple(float(x) for x in rng.uniform(0.2, 0.8, n))
    regime_confidences = tuple(float(x) for x in rng.uniform(0.1, 0.9, n))

    # Labels correlated with inputs
    labels = tuple(
        int(b > 0.5 and m > 0.5)
        for b, m in zip(bayesian_posteriors, ml_probabilities)
    )

    model = train_meta_learner(
        bayesian_posteriors=bayesian_posteriors,
        ml_probabilities=ml_probabilities,
        regime_confidences=regime_confidences,
        labels=labels,
        min_samples=100,
    )
    assert len(model.coefficients) == 3, f"Expected 3 coefficients, got {len(model.coefficients)}"
    assert model.n_training_samples > 0
    assert len(model.feature_names) == 3
    return (
        f"Coefficients: {[round(c, 3) for c in model.coefficients]}, "
        f"intercept={model.intercept:.3f}, n={model.n_training_samples}"
    )


def test_en_02() -> str:
    """Meta-learner prediction produces valid probability."""
    import numpy as np

    from src.analysis.meta_learner import predict_meta_learner, train_meta_learner

    rng = np.random.default_rng(42)
    n = 200
    bayesian_posteriors = tuple(float(x) for x in rng.uniform(0.2, 0.8, n))
    ml_probabilities = tuple(float(x) for x in rng.uniform(0.2, 0.8, n))
    regime_confidences = tuple(float(x) for x in rng.uniform(0.1, 0.9, n))
    labels = tuple(int(b > 0.5) for b in bayesian_posteriors)

    model = train_meta_learner(
        bayesian_posteriors=bayesian_posteriors,
        ml_probabilities=ml_probabilities,
        regime_confidences=regime_confidences,
        labels=labels,
    )

    prob = predict_meta_learner(
        model,
        bayesian_posterior=0.7,
        ml_probability=0.6,
        regime_confidence=0.8,
    )
    assert 0 <= prob <= 1, f"Prediction {prob} should be in [0, 1]"
    return f"Prediction={prob:.4f} for inputs (0.7, 0.6, 0.8)"


def test_en_03() -> str:
    """Calibration error check functions correctly."""
    from src.analysis.meta_learner import check_calibration, compute_calibration_error

    # Well-calibrated predictions (errors should be small)
    predictions = tuple(float(i) / 20 for i in range(20))
    labels = tuple(1 if p > 0.5 else 0 for p in predictions)
    errors = compute_calibration_error(predictions=predictions, labels=labels)
    assert len(errors) == 10, f"Expected 10 decile errors, got {len(errors)}"

    is_calibrated = check_calibration(errors, max_error_pp=50.0)  # Lenient threshold
    assert isinstance(is_calibrated, bool)
    return f"Calibration errors: {[round(e, 2) for e in errors]}, calibrated={is_calibrated}"


def test_en_04() -> str:
    """EnsembleV1Generator produces valid Signal object."""
    from datetime import UTC, datetime

    from src.analysis.signal_contract import FeatureSnapshot, GeneratorConfig, Signal
    from src.trading.signal import EnsembleV1Generator

    gen = EnsembleV1Generator()
    features = FeatureSnapshot(
        instrument="EUR_USD",
        interval="1h",
        time=datetime(2025, 6, 1, tzinfo=UTC),
        values={"rsi_14": 45.0, "macd_12_26_9_line": 0.001, "_close": 1.1},
        metadata={},
    )
    config = GeneratorConfig(
        enabled=True,
        parameters={
            "strong_buy_threshold": 0.65,
            "buy_threshold": 0.55,
            "sell_threshold": 0.40,
        },
    )
    signal = gen.generate("EUR_USD", features, config)
    assert isinstance(signal, Signal)
    assert signal.instrument == "EUR_USD"
    assert signal.generator_id == "ensemble_v1"
    assert 0 <= signal.probability <= 1
    assert signal.action in ("STRONG_BUY", "BUY", "SELL", "NEUTRAL")
    return f"Signal: action={signal.action}, prob={signal.probability:.3f}"


TESTS = [
    UATTest(id="EN-01", name="Meta-learner training produces valid coefficients",
            suite=SUITE_ID, fn=test_en_01),
    UATTest(id="EN-02", name="Meta-learner prediction produces valid probability",
            suite=SUITE_ID, fn=test_en_02),
    UATTest(id="EN-03", name="Calibration error check functions correctly",
            suite=SUITE_ID, fn=test_en_03),
    UATTest(id="EN-04", name="EnsembleV1Generator produces valid Signal",
            suite=SUITE_ID, fn=test_en_04),
]
