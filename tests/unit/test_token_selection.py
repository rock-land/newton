"""Tests for token selection via mutual information (SPEC §5.4)."""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

import pytest

from src.analysis.events import EventLabel
from src.analysis.token_selection import (
    TokenScore,
    compute_mutual_information,
    jaccard_similarity,
    select_tokens,
)
from src.analysis.tokenizer import TokenSet


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ts(minute: int) -> datetime:
    """Create a UTC datetime with the given minute offset."""
    return datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=minute)


def _token_set(minute: int, tokens: frozenset[str]) -> TokenSet:
    return TokenSet(instrument="EUR_USD", time=_ts(minute), tokens=tokens)


def _event_label(minute: int, event_type: str, label: bool) -> EventLabel:
    return EventLabel(event_type=event_type, time=_ts(minute), label=label)


# ---------------------------------------------------------------------------
# TestComputeMutualInformation
# ---------------------------------------------------------------------------

class TestComputeMutualInformation:
    """Tests for compute_mutual_information()."""

    def test_perfect_correlation(self) -> None:
        """Token present iff event true → high MI."""
        token_sets = [
            _token_set(0, frozenset({"A"})),
            _token_set(1, frozenset()),
            _token_set(2, frozenset({"A"})),
            _token_set(3, frozenset()),
        ]
        labels = [
            _event_label(0, "EVT", True),
            _event_label(1, "EVT", False),
            _event_label(2, "EVT", True),
            _event_label(3, "EVT", False),
        ]
        scores = compute_mutual_information(token_sets, labels, "EVT")
        assert len(scores) == 1
        assert scores[0].token == "A"
        assert scores[0].mi_score > 0.5  # Perfect correlation gives ln(2) ≈ 0.693

    def test_no_correlation(self) -> None:
        """Token presence independent of event → MI near zero."""
        # Token present in 50% of cases, event true in 50%, no correlation
        token_sets = [
            _token_set(0, frozenset({"A"})),
            _token_set(1, frozenset({"A"})),
            _token_set(2, frozenset()),
            _token_set(3, frozenset()),
        ]
        labels = [
            _event_label(0, "EVT", True),
            _event_label(1, "EVT", False),
            _event_label(2, "EVT", True),
            _event_label(3, "EVT", False),
        ]
        scores = compute_mutual_information(token_sets, labels, "EVT")
        assert len(scores) == 1
        assert scores[0].mi_score == pytest.approx(0.0, abs=1e-10)

    def test_ranking_by_mi(self) -> None:
        """Multiple tokens ranked descending by MI score."""
        # A: perfectly correlated, B: independent
        token_sets = [
            _token_set(0, frozenset({"A", "B"})),
            _token_set(1, frozenset({"B"})),
            _token_set(2, frozenset({"A"})),
            _token_set(3, frozenset()),
        ]
        labels = [
            _event_label(0, "EVT", True),
            _event_label(1, "EVT", False),
            _event_label(2, "EVT", True),
            _event_label(3, "EVT", False),
        ]
        scores = compute_mutual_information(token_sets, labels, "EVT")
        assert len(scores) == 2
        assert scores[0].token == "A"
        assert scores[1].token == "B"
        assert scores[0].mi_score > scores[1].mi_score

    def test_token_always_present(self) -> None:
        """Token present in every candle → MI is zero."""
        token_sets = [
            _token_set(0, frozenset({"A"})),
            _token_set(1, frozenset({"A"})),
            _token_set(2, frozenset({"A"})),
            _token_set(3, frozenset({"A"})),
        ]
        labels = [
            _event_label(0, "EVT", True),
            _event_label(1, "EVT", False),
            _event_label(2, "EVT", True),
            _event_label(3, "EVT", False),
        ]
        scores = compute_mutual_information(token_sets, labels, "EVT")
        assert len(scores) == 1
        assert scores[0].mi_score == pytest.approx(0.0, abs=1e-10)

    def test_token_never_present(self) -> None:
        """Token never active → not in results (no observations)."""
        token_sets = [
            _token_set(0, frozenset()),
            _token_set(1, frozenset()),
        ]
        labels = [
            _event_label(0, "EVT", True),
            _event_label(1, "EVT", False),
        ]
        scores = compute_mutual_information(token_sets, labels, "EVT")
        assert len(scores) == 0

    def test_event_always_true(self) -> None:
        """Event always true → MI is zero (no event variation)."""
        token_sets = [
            _token_set(0, frozenset({"A"})),
            _token_set(1, frozenset()),
            _token_set(2, frozenset({"A"})),
            _token_set(3, frozenset()),
        ]
        labels = [
            _event_label(0, "EVT", True),
            _event_label(1, "EVT", True),
            _event_label(2, "EVT", True),
            _event_label(3, "EVT", True),
        ]
        scores = compute_mutual_information(token_sets, labels, "EVT")
        assert len(scores) == 1
        assert scores[0].mi_score == pytest.approx(0.0, abs=1e-10)

    def test_event_always_false(self) -> None:
        """Event always false → MI is zero."""
        token_sets = [
            _token_set(0, frozenset({"A"})),
            _token_set(1, frozenset()),
        ]
        labels = [
            _event_label(0, "EVT", False),
            _event_label(1, "EVT", False),
        ]
        scores = compute_mutual_information(token_sets, labels, "EVT")
        assert len(scores) == 1
        assert scores[0].mi_score == pytest.approx(0.0, abs=1e-10)

    def test_empty_token_sets(self) -> None:
        """Empty input returns empty results."""
        scores = compute_mutual_information([], [], "EVT")
        assert scores == []

    def test_filters_by_event_type(self) -> None:
        """Only labels matching the requested event_type are used."""
        token_sets = [
            _token_set(0, frozenset({"A"})),
            _token_set(1, frozenset()),
        ]
        labels = [
            _event_label(0, "EVT_A", True),
            _event_label(0, "EVT_B", False),
            _event_label(1, "EVT_A", False),
            _event_label(1, "EVT_B", True),
        ]
        scores = compute_mutual_information(token_sets, labels, "EVT_A")
        assert len(scores) == 1
        # A present when EVT_A=True, absent when EVT_A=False → perfect correlation
        assert scores[0].mi_score > 0.5

    def test_mismatched_timestamps_skipped(self) -> None:
        """Timestamps in labels but not in token_sets are skipped."""
        token_sets = [
            _token_set(0, frozenset({"A"})),
        ]
        labels = [
            _event_label(0, "EVT", True),
            _event_label(5, "EVT", False),  # no matching token set
        ]
        scores = compute_mutual_information(token_sets, labels, "EVT")
        # Only 1 matched sample — token always present → MI is 0
        assert len(scores) == 1
        assert scores[0].mi_score == pytest.approx(0.0, abs=1e-10)

    def test_token_set_time_not_in_labels(self) -> None:
        """Token sets with times not in label set are skipped (continue branch)."""
        token_sets = [
            _token_set(0, frozenset({"A"})),
            _token_set(99, frozenset({"A"})),  # no label for minute 99
        ]
        labels = [
            _event_label(0, "EVT", True),
        ]
        scores = compute_mutual_information(token_sets, labels, "EVT")
        assert len(scores) == 1
        # Only 1 matched sample → MI is 0
        assert scores[0].mi_score == pytest.approx(0.0, abs=1e-10)

    def test_all_timestamps_mismatched(self) -> None:
        """All token set times missing from labels → n=0 → empty results."""
        token_sets = [
            _token_set(10, frozenset({"A"})),
            _token_set(20, frozenset({"A"})),
        ]
        labels = [
            _event_label(30, "EVT", True),
            _event_label(40, "EVT", False),
        ]
        scores = compute_mutual_information(token_sets, labels, "EVT")
        assert scores == []


# ---------------------------------------------------------------------------
# TestJaccardSimilarity
# ---------------------------------------------------------------------------

class TestJaccardSimilarity:
    """Tests for jaccard_similarity()."""

    def test_identical_activation(self) -> None:
        """Tokens active at the same timestamps → Jaccard 1.0."""
        token_sets = [
            _token_set(0, frozenset({"A", "B"})),
            _token_set(1, frozenset({"A", "B"})),
            _token_set(2, frozenset()),
        ]
        assert jaccard_similarity(token_sets, "A", "B") == pytest.approx(1.0)

    def test_disjoint_activation(self) -> None:
        """Tokens never active together → Jaccard 0.0."""
        token_sets = [
            _token_set(0, frozenset({"A"})),
            _token_set(1, frozenset({"B"})),
            _token_set(2, frozenset()),
        ]
        assert jaccard_similarity(token_sets, "A", "B") == pytest.approx(0.0)

    def test_partial_overlap(self) -> None:
        """Known overlap: |A∩B|=1, |A∪B|=3 → Jaccard ≈ 0.333."""
        token_sets = [
            _token_set(0, frozenset({"A", "B"})),  # both
            _token_set(1, frozenset({"A"})),        # A only
            _token_set(2, frozenset({"B"})),        # B only
            _token_set(3, frozenset()),              # neither
        ]
        assert jaccard_similarity(token_sets, "A", "B") == pytest.approx(1 / 3)

    def test_both_never_active(self) -> None:
        """Neither token ever active → Jaccard 0.0."""
        token_sets = [
            _token_set(0, frozenset()),
            _token_set(1, frozenset()),
        ]
        assert jaccard_similarity(token_sets, "A", "B") == pytest.approx(0.0)

    def test_empty_token_sets(self) -> None:
        """No data → Jaccard 0.0."""
        assert jaccard_similarity([], "A", "B") == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# TestSelectTokens
# ---------------------------------------------------------------------------

class TestSelectTokens:
    """Tests for select_tokens() — the main entry point."""

    def test_basic_selection(self) -> None:
        """Selects tokens ranked by MI, respects top_n."""
        # A: perfectly correlated with event, B: independent
        token_sets = [
            _token_set(0, frozenset({"A", "B"})),
            _token_set(1, frozenset({"B"})),
            _token_set(2, frozenset({"A"})),
            _token_set(3, frozenset()),
        ]
        labels = [
            _event_label(0, "EVT", True),
            _event_label(1, "EVT", False),
            _event_label(2, "EVT", True),
            _event_label(3, "EVT", False),
        ]
        result = select_tokens(token_sets, labels, "EVT", top_n=2)
        assert result.event_type == "EVT"
        assert len(result.tokens) == 2
        assert result.tokens[0].token == "A"
        assert result.tokens[0].mi_score > result.tokens[1].mi_score

    def test_top_n_truncation(self) -> None:
        """Only top_n tokens returned even if more exist."""
        # Create tokens C, D, E with varying MI
        token_sets = [
            _token_set(0, frozenset({"C", "D", "E"})),
            _token_set(1, frozenset({"C", "D"})),
            _token_set(2, frozenset({"C"})),
            _token_set(3, frozenset()),
        ]
        labels = [
            _event_label(0, "EVT", True),
            _event_label(1, "EVT", True),
            _event_label(2, "EVT", False),
            _event_label(3, "EVT", False),
        ]
        result = select_tokens(token_sets, labels, "EVT", top_n=1)
        assert len(result.tokens) == 1

    def test_top_n_max_cap(self) -> None:
        """top_n > 50 is capped to 50."""
        # Only 2 tokens available, request 100
        token_sets = [
            _token_set(0, frozenset({"A"})),
            _token_set(1, frozenset()),
        ]
        labels = [
            _event_label(0, "EVT", True),
            _event_label(1, "EVT", False),
        ]
        result = select_tokens(token_sets, labels, "EVT", top_n=100)
        # Should not error; returns only what's available (1 token)
        assert len(result.tokens) <= 50

    def test_jaccard_dedup(self) -> None:
        """Redundant token (Jaccard > threshold) is dropped."""
        # A and B activate at exact same timestamps (Jaccard=1.0)
        # A has higher MI
        token_sets = [
            _token_set(0, frozenset({"A", "B"})),
            _token_set(1, frozenset()),
            _token_set(2, frozenset({"A", "B"})),
            _token_set(3, frozenset()),
        ]
        labels = [
            _event_label(0, "EVT", True),
            _event_label(1, "EVT", False),
            _event_label(2, "EVT", True),
            _event_label(3, "EVT", False),
        ]
        result = select_tokens(
            token_sets, labels, "EVT", top_n=20, jaccard_threshold=0.85,
        )
        # Both have same MI, but Jaccard=1.0 → second one dropped
        assert len(result.tokens) == 1
        assert "B" in result.dropped_redundant or "A" in result.dropped_redundant

    def test_jaccard_below_threshold_both_kept(self) -> None:
        """Non-redundant tokens (Jaccard < threshold) are both kept."""
        token_sets = [
            _token_set(0, frozenset({"A"})),
            _token_set(1, frozenset({"B"})),
            _token_set(2, frozenset({"A"})),
            _token_set(3, frozenset({"B"})),
        ]
        labels = [
            _event_label(0, "EVT", True),
            _event_label(1, "EVT", False),
            _event_label(2, "EVT", True),
            _event_label(3, "EVT", False),
        ]
        result = select_tokens(
            token_sets, labels, "EVT", top_n=20, jaccard_threshold=0.85,
        )
        assert len(result.tokens) == 2
        assert result.dropped_redundant == ()

    def test_empty_inputs(self) -> None:
        """Empty inputs produce empty selection."""
        result = select_tokens([], [], "EVT")
        assert result.tokens == ()
        assert result.dropped_redundant == ()

    def test_selected_token_set_frozen(self) -> None:
        """SelectedTokenSet is immutable."""
        token_sets = [
            _token_set(0, frozenset({"A"})),
            _token_set(1, frozenset()),
        ]
        labels = [
            _event_label(0, "EVT", True),
            _event_label(1, "EVT", False),
        ]
        result = select_tokens(token_sets, labels, "EVT")
        with pytest.raises(AttributeError):
            result.event_type = "CHANGED"  # type: ignore[misc]

    def test_token_score_frozen(self) -> None:
        """TokenScore is immutable."""
        score = TokenScore(token="X", mi_score=0.5)
        with pytest.raises(AttributeError):
            score.mi_score = 0.9  # type: ignore[misc]


# ---------------------------------------------------------------------------
# TestMIStability
# ---------------------------------------------------------------------------

class TestMIStability:
    """Tests for numerical stability of MI computation."""

    def test_mi_nonnegative(self) -> None:
        """MI should always be non-negative."""
        token_sets = [
            _token_set(i, frozenset({"A"}) if i % 3 == 0 else frozenset())
            for i in range(20)
        ]
        labels = [
            _event_label(i, "EVT", i % 2 == 0)
            for i in range(20)
        ]
        scores = compute_mutual_information(token_sets, labels, "EVT")
        for s in scores:
            assert s.mi_score >= 0.0

    def test_single_sample(self) -> None:
        """Single data point → MI is zero (no variation possible)."""
        token_sets = [_token_set(0, frozenset({"A"}))]
        labels = [_event_label(0, "EVT", True)]
        scores = compute_mutual_information(token_sets, labels, "EVT")
        assert len(scores) == 1
        assert scores[0].mi_score == pytest.approx(0.0, abs=1e-10)

    def test_large_dataset_stable(self) -> None:
        """MI computation with many samples does not produce NaN or Inf."""
        n = 1000
        token_sets = [
            _token_set(i, frozenset({"A"}) if i % 4 < 2 else frozenset())
            for i in range(n)
        ]
        labels = [
            _event_label(i, "EVT", i % 4 == 0 or i % 4 == 1)
            for i in range(n)
        ]
        scores = compute_mutual_information(token_sets, labels, "EVT")
        assert len(scores) == 1
        assert math.isfinite(scores[0].mi_score)
        assert scores[0].mi_score >= 0.0


# ---------------------------------------------------------------------------
# TestLogging
# ---------------------------------------------------------------------------

class TestLogging:
    """Tests for SPEC §5.4 step 5: logging of selected tokens and MI scores."""

    def test_logs_selected_tokens(self, caplog: pytest.LogCaptureFixture) -> None:
        """select_tokens logs the selected token set."""
        import logging
        token_sets = [
            _token_set(0, frozenset({"A"})),
            _token_set(1, frozenset()),
            _token_set(2, frozenset({"A"})),
            _token_set(3, frozenset()),
        ]
        labels = [
            _event_label(0, "EVT", True),
            _event_label(1, "EVT", False),
            _event_label(2, "EVT", True),
            _event_label(3, "EVT", False),
        ]
        with caplog.at_level(logging.INFO, logger="src.analysis.token_selection"):
            select_tokens(token_sets, labels, "EVT")
        assert any("selected" in record.message.lower() for record in caplog.records)
