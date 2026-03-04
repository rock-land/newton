"""Tests for walk-forward training framework (T-303)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from src.analysis.walk_forward import (
    FoldResult,
    WalkForwardConfig,
    WalkForwardFold,
    collect_results,
    generate_folds,
    validate_no_lookahead,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _default_config(
    *,
    train_periods: int = 100,
    test_periods: int = 30,
    step_periods: int = 30,
    embargo_periods: int = 5,
    min_folds: int = 4,
) -> WalkForwardConfig:
    return WalkForwardConfig(
        train_periods=train_periods,
        test_periods=test_periods,
        step_periods=step_periods,
        embargo_periods=embargo_periods,
        min_folds=min_folds,
    )


def _make_fold_result(
    fold_number: int,
    *,
    auc_roc: float = 0.60,
    n_predictions: int = 5,
) -> FoldResult:
    base = datetime(2024, 1, 1, tzinfo=UTC)
    return FoldResult(
        fold_number=fold_number,
        metrics={"auc_roc": auc_roc},
        test_predictions=tuple(0.5 + i * 0.01 for i in range(n_predictions)),
        test_labels=tuple(1 if i % 2 == 0 else 0 for i in range(n_predictions)),
        test_timestamps=tuple(base + timedelta(hours=i) for i in range(n_predictions)),
    )


# ---------------------------------------------------------------------------
# WalkForwardConfig frozen
# ---------------------------------------------------------------------------

class TestWalkForwardConfigFrozen:
    def test_frozen(self) -> None:
        cfg = _default_config()
        with pytest.raises(AttributeError):
            cfg.train_periods = 999  # type: ignore[misc]


# ---------------------------------------------------------------------------
# WalkForwardFold frozen
# ---------------------------------------------------------------------------

class TestWalkForwardFoldFrozen:
    def test_frozen(self) -> None:
        fold = WalkForwardFold(
            fold_number=1,
            train_start_idx=0,
            train_end_idx=100,
            test_start_idx=105,
            test_end_idx=135,
        )
        with pytest.raises(AttributeError):
            fold.fold_number = 2  # type: ignore[misc]


# ---------------------------------------------------------------------------
# generate_folds
# ---------------------------------------------------------------------------

class TestGenerateFolds:
    def test_basic_fold_generation(self) -> None:
        """With 250 samples and small windows, should produce at least 4 folds."""
        cfg = _default_config(
            train_periods=100, test_periods=30, step_periods=30,
            embargo_periods=5, min_folds=4,
        )
        folds = generate_folds(n_samples=250, config=cfg)
        assert len(folds) >= 4

    def test_fold_boundaries_correct(self) -> None:
        """First fold starts at 0, train end < test start, etc."""
        cfg = _default_config(
            train_periods=100, test_periods=30, step_periods=30,
            embargo_periods=5, min_folds=1,
        )
        folds = generate_folds(n_samples=250, config=cfg)
        first = folds[0]
        assert first.train_start_idx == 0
        assert first.train_end_idx == 100
        assert first.test_start_idx == 105  # 100 + 5 embargo
        assert first.test_end_idx == 135

    def test_embargo_enforced(self) -> None:
        """Gap between train_end and test_start equals embargo_periods."""
        cfg = _default_config(embargo_periods=10, min_folds=1)
        folds = generate_folds(n_samples=300, config=cfg)
        for fold in folds:
            gap = fold.test_start_idx - fold.train_end_idx
            assert gap == 10, f"Fold {fold.fold_number}: gap={gap}, expected 10"

    def test_rolling_window_steps(self) -> None:
        """Each fold's train_start advances by step_periods."""
        cfg = _default_config(step_periods=30, min_folds=2)
        folds = generate_folds(n_samples=300, config=cfg)
        for i in range(1, len(folds)):
            step = folds[i].train_start_idx - folds[i - 1].train_start_idx
            assert step == 30

    def test_test_sets_non_overlapping(self) -> None:
        """Consecutive test sets do not overlap."""
        cfg = _default_config(min_folds=2)
        folds = generate_folds(n_samples=300, config=cfg)
        for i in range(1, len(folds)):
            assert folds[i].test_start_idx >= folds[i - 1].test_end_idx

    def test_all_indices_within_bounds(self) -> None:
        """No fold index exceeds n_samples."""
        n = 300
        cfg = _default_config(min_folds=2)
        folds = generate_folds(n_samples=n, config=cfg)
        for fold in folds:
            assert fold.train_start_idx >= 0
            assert fold.train_end_idx <= n
            assert fold.test_start_idx >= 0
            assert fold.test_end_idx <= n

    def test_fold_numbers_sequential(self) -> None:
        """Fold numbers are 1-indexed and sequential."""
        cfg = _default_config(min_folds=2)
        folds = generate_folds(n_samples=300, config=cfg)
        for i, fold in enumerate(folds):
            assert fold.fold_number == i + 1

    def test_insufficient_data_raises(self) -> None:
        """Not enough data for min_folds raises ValueError."""
        cfg = _default_config(
            train_periods=100, test_periods=30, embargo_periods=5, min_folds=4,
        )
        # Need at least: train + embargo + test + 3 * step for 4 folds
        # 100 + 5 + 30 + 3*30 = 225; use less
        with pytest.raises(ValueError, match="Insufficient data"):
            generate_folds(n_samples=50, config=cfg)

    def test_exact_minimum_data(self) -> None:
        """With exactly enough data for min_folds, generation succeeds."""
        cfg = _default_config(
            train_periods=50, test_periods=20, step_periods=20,
            embargo_periods=5, min_folds=4,
        )
        # Fold 1: train [0:50], test [55:75]
        # Fold 2: train [20:70], test [75:95]
        # Fold 3: train [40:90], test [95:115]
        # Fold 4: train [60:110], test [115:135]
        folds = generate_folds(n_samples=135, config=cfg)
        assert len(folds) >= 4

    def test_zero_samples_raises(self) -> None:
        """Zero samples always raises ValueError."""
        cfg = _default_config(min_folds=1)
        with pytest.raises(ValueError, match="Insufficient data"):
            generate_folds(n_samples=0, config=cfg)

    def test_no_lookahead_in_folds(self) -> None:
        """Train indices are always strictly before test indices."""
        cfg = _default_config(min_folds=2)
        folds = generate_folds(n_samples=300, config=cfg)
        for fold in folds:
            assert fold.train_end_idx < fold.test_start_idx


# ---------------------------------------------------------------------------
# validate_no_lookahead
# ---------------------------------------------------------------------------

class TestValidateNoLookahead:
    def test_valid_folds_pass(self) -> None:
        """Well-formed folds pass validation without error."""
        cfg = _default_config(min_folds=2)
        folds = generate_folds(n_samples=300, config=cfg)
        # Should not raise
        validate_no_lookahead(folds, embargo_periods=5)

    def test_overlapping_train_test_raises(self) -> None:
        """Fold where test starts before train ends + embargo raises ValueError."""
        bad_fold = WalkForwardFold(
            fold_number=1,
            train_start_idx=0,
            train_end_idx=100,
            test_start_idx=102,  # only 2 gap, embargo is 5
            test_end_idx=132,
        )
        with pytest.raises(ValueError, match="lookahead"):
            validate_no_lookahead((bad_fold,), embargo_periods=5)

    def test_train_after_test_raises(self) -> None:
        """Fold where train_end > test_start raises ValueError."""
        bad_fold = WalkForwardFold(
            fold_number=1,
            train_start_idx=0,
            train_end_idx=110,
            test_start_idx=105,
            test_end_idx=135,
        )
        with pytest.raises(ValueError, match="lookahead"):
            validate_no_lookahead((bad_fold,), embargo_periods=5)


# ---------------------------------------------------------------------------
# FoldResult frozen
# ---------------------------------------------------------------------------

class TestFoldResultFrozen:
    def test_frozen(self) -> None:
        result = _make_fold_result(1)
        with pytest.raises(AttributeError):
            result.fold_number = 2  # type: ignore[misc]


# ---------------------------------------------------------------------------
# collect_results
# ---------------------------------------------------------------------------

class TestCollectResults:
    def test_aggregates_oof_predictions(self) -> None:
        """OOF predictions are concatenated from all folds."""
        r1 = _make_fold_result(1, n_predictions=3)
        r2 = _make_fold_result(2, n_predictions=4)
        result = collect_results(
            fold_results=[r1, r2],
            config=_default_config(),
        )
        assert len(result.oof_predictions) == 7
        assert len(result.oof_labels) == 7
        assert len(result.oof_timestamps) == 7

    def test_aggregates_oof_labels(self) -> None:
        """OOF labels match the concatenation of fold labels."""
        r1 = _make_fold_result(1, n_predictions=2)
        r2 = _make_fold_result(2, n_predictions=3)
        result = collect_results(
            fold_results=[r1, r2],
            config=_default_config(),
        )
        expected_labels = r1.test_labels + r2.test_labels
        assert result.oof_labels == expected_labels

    def test_mean_auc_roc(self) -> None:
        """Mean AUC-ROC is the average of per-fold AUC-ROC."""
        r1 = _make_fold_result(1, auc_roc=0.55)
        r2 = _make_fold_result(2, auc_roc=0.65)
        r3 = _make_fold_result(3, auc_roc=0.60)
        result = collect_results(
            fold_results=[r1, r2, r3],
            config=_default_config(),
        )
        assert abs(result.mean_auc_roc - 0.60) < 1e-10

    def test_folds_tuple(self) -> None:
        """Folds are stored as a tuple in the result."""
        r1 = _make_fold_result(1)
        r2 = _make_fold_result(2)
        result = collect_results(
            fold_results=[r1, r2],
            config=_default_config(),
        )
        assert len(result.folds) == 2
        assert result.folds[0].fold_number == 1
        assert result.folds[1].fold_number == 2

    def test_result_is_frozen(self) -> None:
        """WalkForwardResult is frozen."""
        r1 = _make_fold_result(1)
        result = collect_results(
            fold_results=[r1],
            config=_default_config(),
        )
        with pytest.raises(AttributeError):
            result.mean_auc_roc = 0.99  # type: ignore[misc]

    def test_empty_fold_results(self) -> None:
        """Empty fold results produces empty aggregation."""
        result = collect_results(
            fold_results=[],
            config=_default_config(),
        )
        assert len(result.oof_predictions) == 0
        assert len(result.oof_labels) == 0
        assert result.mean_auc_roc == 0.0

    def test_preserves_timestamps_order(self) -> None:
        """OOF timestamps maintain fold ordering."""
        base = datetime(2024, 1, 1, tzinfo=UTC)
        r1 = FoldResult(
            fold_number=1,
            metrics={"auc_roc": 0.6},
            test_predictions=(0.5, 0.6),
            test_labels=(1, 0),
            test_timestamps=(base, base + timedelta(hours=1)),
        )
        r2 = FoldResult(
            fold_number=2,
            metrics={"auc_roc": 0.7},
            test_predictions=(0.7,),
            test_labels=(1,),
            test_timestamps=(base + timedelta(hours=100),),
        )
        result = collect_results(
            fold_results=[r1, r2],
            config=_default_config(),
        )
        assert result.oof_timestamps[0] == base
        assert result.oof_timestamps[2] == base + timedelta(hours=100)

    def test_config_preserved(self) -> None:
        """The config is preserved in the result."""
        cfg = _default_config(train_periods=200)
        result = collect_results(fold_results=[], config=cfg)
        assert result.config.train_periods == 200
