"""Tests for Bayesian inference engine (SPEC §5.5)."""

from __future__ import annotations

import logging
import math
from datetime import UTC, datetime, timedelta

import pytest

from src.analysis.bayesian import (
    BayesianModel,
    CorrelationWarning,
    TokenLikelihood,
    check_correlations,
    compute_phi_coefficient,
    predict,
    train,
)
from src.analysis.events import EventLabel
from src.analysis.tokenizer import TokenSet


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ts(minute: int) -> datetime:
    """UTC timestamp offset by *minute* minutes from a fixed epoch."""
    return datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=minute)


def _build_synthetic_data(
    n: int,
    event_rate: float,
    token_rates_event: dict[str, float],
    token_rates_no_event: dict[str, float],
    event_type: str = "TEST_UP_1PCT_24H",
    instrument: str = "TEST",
) -> tuple[list[TokenSet], list[EventLabel]]:
    """Build deterministic synthetic data with controlled rates.

    First ``floor(n * event_rate)`` timestamps are events.
    For each token, the first ``floor(group_size * rate)`` timestamps
    in the event/no-event group have the token present.
    """
    n_event = int(n * event_rate)
    all_tokens = set(token_rates_event.keys()) | set(token_rates_no_event.keys())

    event_indices = list(range(n_event))
    no_event_indices = list(range(n_event, n))

    token_active: dict[str, set[int]] = {}
    for token in all_tokens:
        active: set[int] = set()
        count_e = int(n_event * token_rates_event.get(token, 0.0))
        active.update(event_indices[:count_e])
        count_ne = int(len(no_event_indices) * token_rates_no_event.get(token, 0.0))
        active.update(no_event_indices[:count_ne])
        token_active[token] = active

    token_sets: list[TokenSet] = []
    event_labels: list[EventLabel] = []
    for i in range(n):
        tokens = frozenset(t for t in all_tokens if i in token_active[t])
        token_sets.append(TokenSet(instrument=instrument, time=_ts(i), tokens=tokens))
        event_labels.append(EventLabel(event_type=event_type, time=_ts(i), label=i < n_event))

    return token_sets, event_labels


# ---------------------------------------------------------------------------
# Dataclass tests
# ---------------------------------------------------------------------------


class TestBayesianModel:
    def test_frozen(self) -> None:
        model = BayesianModel(
            event_type="X", prior=0.5, likelihoods=(),
            calibration_x=(), calibration_y=(), posterior_cap=0.9,
        )
        with pytest.raises(AttributeError):
            model.prior = 0.6  # type: ignore[misc]

    def test_fields_present(self) -> None:
        tl = TokenLikelihood("T", 0.8, 0.2)
        model = BayesianModel(
            event_type="X", prior=0.4, likelihoods=(tl,),
            calibration_x=(0.0, 1.0), calibration_y=(0.0, 1.0), posterior_cap=0.9,
        )
        assert model.event_type == "X"
        assert model.prior == 0.4
        assert len(model.likelihoods) == 1
        assert model.posterior_cap == 0.9


class TestTokenLikelihood:
    def test_frozen(self) -> None:
        tl = TokenLikelihood(token="T", p_given_event=0.8, p_given_no_event=0.2)
        with pytest.raises(AttributeError):
            tl.token = "X"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Training tests
# ---------------------------------------------------------------------------


class TestTrain:
    def test_prior_computation(self) -> None:
        token_sets, labels = _build_synthetic_data(
            n=100, event_rate=0.4,
            token_rates_event={"T_A": 0.8}, token_rates_no_event={"T_A": 0.2},
        )
        model = train(token_sets, labels, ["T_A"], "TEST_UP_1PCT_24H",
                       laplace_alpha=1, posterior_cap=0.9)
        assert model.prior == pytest.approx(0.4, abs=0.01)

    def test_likelihood_with_laplace_smoothing(self) -> None:
        # 100 ts, 40 events. T_A present in 32/40 events, 12/60 non-events.
        # P(T|E) = (32+1)/(40+2) = 33/42;  P(T|~E) = (12+1)/(60+2) = 13/62
        token_sets, labels = _build_synthetic_data(
            n=100, event_rate=0.4,
            token_rates_event={"T_A": 0.8}, token_rates_no_event={"T_A": 0.2},
        )
        model = train(token_sets, labels, ["T_A"], "TEST_UP_1PCT_24H",
                       laplace_alpha=1, posterior_cap=0.9)
        tl = model.likelihoods[0]
        assert tl.token == "T_A"
        assert tl.p_given_event == pytest.approx(33 / 42, abs=0.01)
        assert tl.p_given_no_event == pytest.approx(13 / 62, abs=0.01)

    def test_laplace_alpha_configurable(self) -> None:
        token_sets, labels = _build_synthetic_data(
            n=100, event_rate=0.4,
            token_rates_event={"T_A": 0.8}, token_rates_no_event={"T_A": 0.2},
        )
        m1 = train(token_sets, labels, ["T_A"], "TEST_UP_1PCT_24H",
                    laplace_alpha=1, posterior_cap=0.9)
        m5 = train(token_sets, labels, ["T_A"], "TEST_UP_1PCT_24H",
                    laplace_alpha=5, posterior_cap=0.9)
        # Higher alpha pushes likelihoods toward 0.5
        assert abs(m5.likelihoods[0].p_given_event - 0.5) < abs(m1.likelihoods[0].p_given_event - 0.5)

    def test_empty_inputs(self) -> None:
        model = train([], [], ["T_A"], "TEST_UP_1PCT_24H",
                       laplace_alpha=1, posterior_cap=0.9)
        assert model.prior == 0.5
        assert model.likelihoods == ()

    def test_empty_selected_tokens(self) -> None:
        token_sets, labels = _build_synthetic_data(
            n=50, event_rate=0.5,
            token_rates_event={"T_A": 0.8}, token_rates_no_event={"T_A": 0.2},
        )
        model = train(token_sets, labels, [], "TEST_UP_1PCT_24H",
                       laplace_alpha=1, posterior_cap=0.9)
        assert len(model.likelihoods) == 0

    def test_multiple_tokens(self) -> None:
        token_sets, labels = _build_synthetic_data(
            n=100, event_rate=0.5,
            token_rates_event={"T_A": 0.9, "T_B": 0.6},
            token_rates_no_event={"T_A": 0.1, "T_B": 0.4},
        )
        model = train(token_sets, labels, ["T_A", "T_B"], "TEST_UP_1PCT_24H",
                       laplace_alpha=1, posterior_cap=0.9)
        assert len(model.likelihoods) == 2
        assert {tl.token for tl in model.likelihoods} == {"T_A", "T_B"}

    def test_stores_posterior_cap(self) -> None:
        token_sets, labels = _build_synthetic_data(
            n=50, event_rate=0.5,
            token_rates_event={"T_A": 0.8}, token_rates_no_event={"T_A": 0.2},
        )
        model = train(token_sets, labels, ["T_A"], "TEST_UP_1PCT_24H",
                       laplace_alpha=1, posterior_cap=0.85)
        assert model.posterior_cap == 0.85

    def test_calibration_present(self) -> None:
        token_sets, labels = _build_synthetic_data(
            n=100, event_rate=0.4,
            token_rates_event={"T_A": 0.8}, token_rates_no_event={"T_A": 0.2},
        )
        model = train(token_sets, labels, ["T_A"], "TEST_UP_1PCT_24H",
                       laplace_alpha=1, posterior_cap=0.9)
        assert len(model.calibration_x) > 0
        assert len(model.calibration_x) == len(model.calibration_y)


# ---------------------------------------------------------------------------
# Prediction tests
# ---------------------------------------------------------------------------


class TestPredict:
    def test_no_active_tokens_returns_prior(self) -> None:
        model = BayesianModel(
            event_type="X", prior=0.4,
            likelihoods=(TokenLikelihood("T_A", 0.8, 0.2),),
            calibration_x=(0.0, 1.0), calibration_y=(0.0, 1.0),
            posterior_cap=0.9,
        )
        p = predict(model, frozenset())
        assert p == pytest.approx(0.4, abs=0.01)

    def test_unknown_tokens_ignored(self) -> None:
        model = BayesianModel(
            event_type="X", prior=0.4,
            likelihoods=(TokenLikelihood("T_A", 0.8, 0.2),),
            calibration_x=(0.0, 1.0), calibration_y=(0.0, 1.0),
            posterior_cap=0.9,
        )
        p_unknown = predict(model, frozenset(["T_UNKNOWN"]))
        p_empty = predict(model, frozenset())
        assert p_unknown == pytest.approx(p_empty, abs=1e-10)

    def test_log_odds_math(self) -> None:
        # prior=0.4 → log(0.4/0.6); T_A: log(0.8/0.2); sigmoid(sum)
        model = BayesianModel(
            event_type="X", prior=0.4,
            likelihoods=(TokenLikelihood("T_A", 0.8, 0.2),),
            calibration_x=(0.0, 1.0), calibration_y=(0.0, 1.0),
            posterior_cap=0.9,
        )
        p = predict(model, frozenset(["T_A"]))
        expected = 1.0 / (1.0 + math.exp(-(math.log(0.4 / 0.6) + math.log(0.8 / 0.2))))
        assert p == pytest.approx(expected, abs=1e-4)

    def test_multiple_tokens_combine(self) -> None:
        model = BayesianModel(
            event_type="X", prior=0.5,
            likelihoods=(
                TokenLikelihood("T_A", 0.8, 0.2),
                TokenLikelihood("T_B", 0.7, 0.3),
            ),
            calibration_x=(0.0, 1.0), calibration_y=(0.0, 1.0),
            posterior_cap=0.95,
        )
        p = predict(model, frozenset(["T_A", "T_B"]))
        lo = math.log(0.5 / 0.5) + math.log(0.8 / 0.2) + math.log(0.7 / 0.3)
        expected = 1.0 / (1.0 + math.exp(-lo))
        assert p == pytest.approx(expected, abs=1e-4)

    def test_posterior_cap_applied(self) -> None:
        model = BayesianModel(
            event_type="X", prior=0.5,
            likelihoods=(
                TokenLikelihood("T_A", 0.99, 0.01),
                TokenLikelihood("T_B", 0.99, 0.01),
            ),
            calibration_x=(0.0, 1.0), calibration_y=(0.0, 1.0),
            posterior_cap=0.90,
        )
        p = predict(model, frozenset(["T_A", "T_B"]))
        assert p <= 0.90

    def test_custom_posterior_cap(self) -> None:
        model = BayesianModel(
            event_type="X", prior=0.5,
            likelihoods=(TokenLikelihood("T_A", 0.99, 0.01),),
            calibration_x=(0.0, 1.0), calibration_y=(0.0, 1.0),
            posterior_cap=0.75,
        )
        p = predict(model, frozenset(["T_A"]))
        assert p <= 0.75


# ---------------------------------------------------------------------------
# Calibration tests
# ---------------------------------------------------------------------------


class TestCalibration:
    def test_calibration_monotonic(self) -> None:
        token_sets, labels = _build_synthetic_data(
            n=200, event_rate=0.3,
            token_rates_event={"T_A": 0.9, "T_B": 0.7},
            token_rates_no_event={"T_A": 0.1, "T_B": 0.3},
        )
        model = train(token_sets, labels, ["T_A", "T_B"], "TEST_UP_1PCT_24H",
                       laplace_alpha=1, posterior_cap=0.9)
        for i in range(1, len(model.calibration_y)):
            assert model.calibration_y[i] >= model.calibration_y[i - 1]

    def test_calibration_x_sorted(self) -> None:
        token_sets, labels = _build_synthetic_data(
            n=200, event_rate=0.4,
            token_rates_event={"T_A": 0.8}, token_rates_no_event={"T_A": 0.2},
        )
        model = train(token_sets, labels, ["T_A"], "TEST_UP_1PCT_24H",
                       laplace_alpha=1, posterior_cap=0.9)
        for i in range(1, len(model.calibration_x)):
            assert model.calibration_x[i] >= model.calibration_x[i - 1]

    def test_identity_calibration_passthrough(self) -> None:
        model = BayesianModel(
            event_type="X", prior=0.4,
            likelihoods=(TokenLikelihood("T_A", 0.7, 0.3),),
            calibration_x=(0.0, 1.0), calibration_y=(0.0, 1.0),
            posterior_cap=0.9,
        )
        p = predict(model, frozenset(["T_A"]))
        lo = math.log(0.4 / 0.6) + math.log(0.7 / 0.3)
        raw = 1.0 / (1.0 + math.exp(-lo))
        assert p == pytest.approx(raw, abs=1e-4)

    def test_higher_raw_gives_higher_calibrated(self) -> None:
        model = BayesianModel(
            event_type="X", prior=0.5,
            likelihoods=(
                TokenLikelihood("T_A", 0.8, 0.2),
                TokenLikelihood("T_B", 0.7, 0.3),
            ),
            calibration_x=(0.0, 0.3, 0.5, 0.7, 1.0),
            calibration_y=(0.0, 0.2, 0.5, 0.8, 1.0),
            posterior_cap=0.95,
        )
        p_one = predict(model, frozenset(["T_A"]))
        p_two = predict(model, frozenset(["T_A", "T_B"]))
        assert p_two >= p_one


# ---------------------------------------------------------------------------
# Phi correlation tests
# ---------------------------------------------------------------------------


class TestPhiCorrelation:
    def test_identical_tokens_phi_one(self) -> None:
        token_sets = [
            TokenSet("T", _ts(i), frozenset(["A", "B"]) if i < 5 else frozenset())
            for i in range(10)
        ]
        phi = compute_phi_coefficient(token_sets, "A", "B")
        assert phi == pytest.approx(1.0, abs=1e-6)

    def test_anti_correlated_tokens(self) -> None:
        token_sets = [
            TokenSet("T", _ts(i), frozenset(["A"]) if i < 5 else frozenset(["B"]))
            for i in range(10)
        ]
        phi = compute_phi_coefficient(token_sets, "A", "B")
        assert phi < -0.5

    def test_phi_zero_marginal(self) -> None:
        token_sets = [
            TokenSet("T", _ts(i), frozenset(["A"]) if i < 5 else frozenset())
            for i in range(10)
        ]
        phi = compute_phi_coefficient(token_sets, "A", "NEVER")
        assert phi == 0.0

    def test_check_correlations_warns(self, caplog: pytest.LogCaptureFixture) -> None:
        token_sets = [
            TokenSet("T", _ts(i), frozenset(["A", "B", "C"]) if i < 5 else frozenset())
            for i in range(10)
        ]
        with caplog.at_level(logging.WARNING, logger="src.analysis.bayesian"):
            warnings = check_correlations(token_sets, ["A", "B", "C"], threshold=0.7)
        assert len(warnings) == 3  # C(3,2) = 3
        assert all(isinstance(w, CorrelationWarning) for w in warnings)

    def test_check_correlations_alert_many_pairs(self, caplog: pytest.LogCaptureFixture) -> None:
        tokens = ["A", "B", "C", "D", "E"]
        token_sets = [
            TokenSet("T", _ts(i), frozenset(tokens) if i < 5 else frozenset())
            for i in range(10)
        ]
        with caplog.at_level(logging.WARNING, logger="src.analysis.bayesian"):
            warnings = check_correlations(token_sets, tokens, threshold=0.7)
        assert len(warnings) == 10  # C(5,2) = 10
        assert any("reducing" in r.message.lower() for r in caplog.records)

    def test_check_correlations_no_warnings(self) -> None:
        # A present at 0-9, B present at 5-14 → phi = 0.0 (independent)
        token_sets = []
        for i in range(20):
            tokens: set[str] = set()
            if i < 10:
                tokens.add("A")
            if 5 <= i < 15:
                tokens.add("B")
            token_sets.append(TokenSet("T", _ts(i), frozenset(tokens)))
        warnings = check_correlations(token_sets, ["A", "B"], threshold=0.7)
        assert len(warnings) == 0


# ---------------------------------------------------------------------------
# Numerical stability tests
# ---------------------------------------------------------------------------


class TestNumericalStability:
    def test_very_rare_event(self) -> None:
        token_sets, labels = _build_synthetic_data(
            n=200, event_rate=0.05,
            token_rates_event={"T_A": 0.8}, token_rates_no_event={"T_A": 0.1},
        )
        model = train(token_sets, labels, ["T_A"], "TEST_UP_1PCT_24H",
                       laplace_alpha=1, posterior_cap=0.9)
        p = predict(model, frozenset(["T_A"]))
        assert 0.0 <= p <= 0.9
        assert not math.isnan(p)

    def test_very_common_event(self) -> None:
        token_sets, labels = _build_synthetic_data(
            n=200, event_rate=0.95,
            token_rates_event={"T_A": 0.8}, token_rates_no_event={"T_A": 0.1},
        )
        model = train(token_sets, labels, ["T_A"], "TEST_UP_1PCT_24H",
                       laplace_alpha=1, posterior_cap=0.9)
        p = predict(model, frozenset(["T_A"]))
        assert 0.0 <= p <= 0.9
        assert not math.isnan(p)

    def test_extreme_likelihood_ratio(self) -> None:
        model = BayesianModel(
            event_type="X", prior=0.5,
            likelihoods=(
                TokenLikelihood("T_A", 0.999, 0.001),
                TokenLikelihood("T_B", 0.999, 0.001),
                TokenLikelihood("T_C", 0.999, 0.001),
            ),
            calibration_x=(0.0, 1.0), calibration_y=(0.0, 1.0),
            posterior_cap=0.9,
        )
        p = predict(model, frozenset(["T_A", "T_B", "T_C"]))
        assert 0.0 <= p <= 0.9
        assert not math.isnan(p)

    def test_single_sample(self) -> None:
        token_sets = [TokenSet("T", _ts(0), frozenset(["T_A"]))]
        labels = [EventLabel("TEST_UP_1PCT_24H", _ts(0), True)]
        model = train(token_sets, labels, ["T_A"], "TEST_UP_1PCT_24H",
                       laplace_alpha=1, posterior_cap=0.9)
        p = predict(model, frozenset(["T_A"]))
        assert 0.0 <= p <= 0.9


# ---------------------------------------------------------------------------
# End-to-end tests
# ---------------------------------------------------------------------------


class TestEndToEnd:
    def test_informative_token_increases_posterior(self) -> None:
        token_sets, labels = _build_synthetic_data(
            n=200, event_rate=0.3,
            token_rates_event={"T_A": 0.9}, token_rates_no_event={"T_A": 0.1},
        )
        model = train(token_sets, labels, ["T_A"], "TEST_UP_1PCT_24H",
                       laplace_alpha=1, posterior_cap=0.9)
        p_active = predict(model, frozenset(["T_A"]))
        p_inactive = predict(model, frozenset())
        assert p_active > p_inactive

    def test_uninformative_token_near_prior(self) -> None:
        token_sets, labels = _build_synthetic_data(
            n=200, event_rate=0.5,
            token_rates_event={"T_A": 0.5}, token_rates_no_event={"T_A": 0.5},
        )
        model = train(token_sets, labels, ["T_A"], "TEST_UP_1PCT_24H",
                       laplace_alpha=1, posterior_cap=0.9)
        p = predict(model, frozenset(["T_A"]))
        assert p == pytest.approx(0.5, abs=0.1)

    def test_mismatched_event_type_returns_default(self) -> None:
        """Token sets exist but no labels match the event type."""
        token_sets = [TokenSet("T", _ts(0), frozenset(["T_A"]))]
        labels = [EventLabel("WRONG_EVENT", _ts(0), True)]
        model = train(token_sets, labels, ["T_A"], "TEST_UP_1PCT_24H",
                       laplace_alpha=1, posterior_cap=0.9)
        assert model.prior == 0.5
        assert model.likelihoods == ()

    def test_calibration_clamps_below_min(self) -> None:
        """Raw posterior below calibration range returns minimum calibrated value."""
        model = BayesianModel(
            event_type="X", prior=0.01,
            likelihoods=(TokenLikelihood("T_A", 0.01, 0.99),),
            calibration_x=(0.3, 0.5, 0.7), calibration_y=(0.2, 0.5, 0.8),
            posterior_cap=0.9,
        )
        # With very low prior and anti-informative token, raw << 0.3
        p = predict(model, frozenset(["T_A"]))
        assert p == pytest.approx(0.2, abs=0.01)

    def test_train_runs_correlation_check(self, caplog: pytest.LogCaptureFixture) -> None:
        """Training with perfectly correlated tokens logs phi warnings."""
        token_sets = [
            TokenSet("T", _ts(i), frozenset(["A", "B"]) if i < 5 else frozenset())
            for i in range(10)
        ]
        labels = [EventLabel("EVT", _ts(i), i < 3) for i in range(10)]
        with caplog.at_level(logging.WARNING, logger="src.analysis.bayesian"):
            train(token_sets, labels, ["A", "B"], "EVT",
                  laplace_alpha=1, posterior_cap=0.9)
        assert any("phi" in r.message.lower() or "correlation" in r.message.lower()
                    for r in caplog.records)
