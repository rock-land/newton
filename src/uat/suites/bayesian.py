"""Bayesian UAT suite — model training, prediction, calibration, correlation."""

from __future__ import annotations

from src.uat.runner import UATTest

SUITE_ID = "bayesian"
SUITE_NAME = "Bayesian"


def test_ba_01() -> str:
    """Model training with Laplace smoothing produces valid params."""
    from datetime import UTC, datetime, timedelta

    from src.analysis.bayesian import train
    from src.analysis.events import EventLabel
    from src.analysis.tokenizer import TokenSet

    t = datetime(2025, 1, 1, tzinfo=UTC)
    token_sets: list[TokenSet] = []
    event_labels: list[EventLabel] = []

    for i in range(200):
        has_event = i % 4 == 0
        tokens: set[str] = set()
        if has_event:
            tokens.add("T_SIGNAL")
        if i % 2 == 0:
            tokens.add("T_NOISE")

        token_sets.append(TokenSet(
            instrument="EUR_USD",
            time=t + timedelta(hours=i),
            tokens=frozenset(tokens),
        ))
        event_labels.append(EventLabel(
            event_type="EURUSD_UP_1PCT_24H",
            time=t + timedelta(hours=i),
            label=has_event,
        ))

    model = train(
        token_sets, event_labels,
        selected_tokens=["T_SIGNAL", "T_NOISE"],
        event_type="EURUSD_UP_1PCT_24H",
        laplace_alpha=1.0,
        posterior_cap=0.90,
    )
    assert 0 < model.prior < 1, f"Prior should be in (0,1), got {model.prior}"
    assert len(model.likelihoods) == 2, f"Expected 2 likelihoods, got {len(model.likelihoods)}"
    assert model.posterior_cap == 0.90
    return f"Prior={model.prior:.3f}, {len(model.likelihoods)} likelihoods, cap={model.posterior_cap}"


def test_ba_02() -> str:
    """Posterior prediction clamped within configured bounds."""
    from datetime import UTC, datetime, timedelta

    from src.analysis.bayesian import predict, train
    from src.analysis.events import EventLabel
    from src.analysis.tokenizer import TokenSet

    t = datetime(2025, 1, 1, tzinfo=UTC)
    token_sets: list[TokenSet] = []
    event_labels: list[EventLabel] = []

    for i in range(200):
        has_event = i % 3 == 0
        tokens = frozenset({"T_A"} if has_event else set())
        token_sets.append(TokenSet(
            instrument="EUR_USD",
            time=t + timedelta(hours=i),
            tokens=tokens,
        ))
        event_labels.append(EventLabel(
            event_type="TEST_EVENT",
            time=t + timedelta(hours=i),
            label=has_event,
        ))

    cap = 0.85
    model = train(
        token_sets, event_labels,
        selected_tokens=["T_A"],
        event_type="TEST_EVENT",
        posterior_cap=cap,
    )

    # Predict with all tokens active (should push probability up)
    prob = predict(model, frozenset({"T_A"}))
    assert 0 <= prob <= cap, f"Prediction {prob} should be in [0, {cap}]"

    # Predict with no tokens
    prob_empty = predict(model, frozenset())
    assert 0 <= prob_empty <= 1, f"Empty prediction {prob_empty} should be in [0, 1]"
    return f"With token: {prob:.3f} (cap={cap}), without: {prob_empty:.3f}"


def test_ba_03() -> str:
    """Isotonic calibration populates calibration arrays."""
    from datetime import UTC, datetime, timedelta

    from src.analysis.bayesian import train
    from src.analysis.events import EventLabel
    from src.analysis.tokenizer import TokenSet

    t = datetime(2025, 1, 1, tzinfo=UTC)
    token_sets: list[TokenSet] = []
    event_labels: list[EventLabel] = []

    for i in range(200):
        has_event = i % 5 == 0
        tokens = frozenset({"T_X"} if has_event else set())
        token_sets.append(TokenSet(
            instrument="EUR_USD",
            time=t + timedelta(hours=i),
            tokens=tokens,
        ))
        event_labels.append(EventLabel(
            event_type="TEST_EVENT",
            time=t + timedelta(hours=i),
            label=has_event,
        ))

    model = train(
        token_sets, event_labels,
        selected_tokens=["T_X"],
        event_type="TEST_EVENT",
    )
    assert len(model.calibration_x) > 0, "Calibration X should be populated"
    assert len(model.calibration_y) > 0, "Calibration Y should be populated"
    assert len(model.calibration_x) == len(model.calibration_y)
    return (
        f"Calibration: {len(model.calibration_x)} points, "
        f"X range [{min(model.calibration_x):.3f}, {max(model.calibration_x):.3f}]"
    )


def test_ba_04() -> str:
    """Phi correlation check warns on highly correlated tokens."""
    from datetime import UTC, datetime, timedelta

    from src.analysis.bayesian import check_correlations
    from src.analysis.tokenizer import TokenSet

    t = datetime(2025, 1, 1, tzinfo=UTC)
    token_sets: list[TokenSet] = []

    # Create perfectly correlated tokens (T_A and T_B always appear together)
    for i in range(100):
        if i % 3 == 0:
            tokens = frozenset({"T_A", "T_B"})
        else:
            tokens = frozenset()
        token_sets.append(TokenSet(
            instrument="EUR_USD",
            time=t + timedelta(hours=i),
            tokens=tokens,
        ))

    warnings = check_correlations(
        token_sets, ["T_A", "T_B"], threshold=0.7,
    )
    assert len(warnings) > 0, "Should warn about perfectly correlated tokens"
    assert abs(warnings[0].phi) > 0.7, f"Phi should be > 0.7, got {warnings[0].phi}"
    return f"{len(warnings)} warning(s), phi={warnings[0].phi:.3f}"


TESTS = [
    UATTest(id="BA-01", name="Model training with Laplace smoothing",
            suite=SUITE_ID, fn=test_ba_01),
    UATTest(id="BA-02", name="Posterior prediction clamped within bounds",
            suite=SUITE_ID, fn=test_ba_02),
    UATTest(id="BA-03", name="Isotonic calibration populates arrays",
            suite=SUITE_ID, fn=test_ba_03),
    UATTest(id="BA-04", name="Phi correlation warns on correlated tokens",
            suite=SUITE_ID, fn=test_ba_04),
]
