"""Tests for purged K-fold cross-validation (T-604)."""

from __future__ import annotations

import pytest

from src.backtest.kfold import (
    KFoldConfig,
    KFoldFoldResult,
    KFoldResult,
    KFoldSplit,
    collect_kfold_results,
    generate_kfold_splits,
    validate_no_leakage,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _default_config(
    *,
    k: int = 5,
    purge_periods: int = 48,
) -> KFoldConfig:
    return KFoldConfig(k=k, purge_periods=purge_periods)


def _make_fold_result(
    fold_number: int,
    *,
    auc_roc: float = 0.60,
    sharpe: float = 1.0,
    n_predictions: int = 5,
) -> KFoldFoldResult:
    return KFoldFoldResult(
        fold_number=fold_number,
        metrics={"auc_roc": auc_roc, "sharpe_ratio": sharpe},
        test_predictions=tuple(0.5 + i * 0.01 for i in range(n_predictions)),
        test_labels=tuple(1 if i % 2 == 0 else 0 for i in range(n_predictions)),
    )


# ---------------------------------------------------------------------------
# Frozen dataclasses
# ---------------------------------------------------------------------------

class TestDataclassImmutability:
    def test_config_frozen(self) -> None:
        cfg = _default_config()
        with pytest.raises(AttributeError):
            cfg.k = 10  # type: ignore[misc]

    def test_split_frozen(self) -> None:
        split = KFoldSplit(
            fold_number=1,
            train_ranges=((0, 50), (150, 200)),
            test_start_idx=50,
            test_end_idx=150,
        )
        with pytest.raises(AttributeError):
            split.fold_number = 2  # type: ignore[misc]

    def test_fold_result_frozen(self) -> None:
        fr = _make_fold_result(1)
        with pytest.raises(AttributeError):
            fr.fold_number = 2  # type: ignore[misc]

    def test_kfold_result_frozen(self) -> None:
        result = KFoldResult(
            config=_default_config(),
            folds=(),
            mean_metrics={},
        )
        with pytest.raises(AttributeError):
            result.config = _default_config(k=3)  # type: ignore[misc]


# ---------------------------------------------------------------------------
# generate_kfold_splits — basic
# ---------------------------------------------------------------------------

class TestGenerateKFoldSplits:
    def test_produces_k_splits(self) -> None:
        """Should produce exactly K splits."""
        cfg = _default_config(k=5, purge_periods=2)
        splits = generate_kfold_splits(n_samples=500, config=cfg)
        assert len(splits) == 5

    def test_fold_numbers_sequential(self) -> None:
        """Fold numbers are 1-indexed and sequential."""
        cfg = _default_config(k=5, purge_periods=2)
        splits = generate_kfold_splits(n_samples=500, config=cfg)
        for i, split in enumerate(splits):
            assert split.fold_number == i + 1

    def test_test_sets_cover_all_data(self) -> None:
        """Union of all test sets should cover all indices."""
        cfg = _default_config(k=5, purge_periods=2)
        splits = generate_kfold_splits(n_samples=500, config=cfg)
        all_test = set()
        for s in splits:
            all_test.update(range(s.test_start_idx, s.test_end_idx))
        assert all_test == set(range(500))

    def test_test_sets_non_overlapping(self) -> None:
        """Test sets should not overlap between folds."""
        cfg = _default_config(k=5, purge_periods=2)
        splits = generate_kfold_splits(n_samples=500, config=cfg)
        all_test: list[int] = []
        for s in splits:
            all_test.extend(range(s.test_start_idx, s.test_end_idx))
        assert len(all_test) == len(set(all_test))

    def test_last_fold_extends_to_end(self) -> None:
        """Last fold should cover remaining samples when n_samples not divisible by k."""
        cfg = _default_config(k=3, purge_periods=2)
        splits = generate_kfold_splits(n_samples=100, config=cfg)
        assert splits[-1].test_end_idx == 100

    def test_first_fold_test_starts_at_zero(self) -> None:
        """First fold's test set starts at index 0."""
        cfg = _default_config(k=5, purge_periods=2)
        splits = generate_kfold_splits(n_samples=500, config=cfg)
        assert splits[0].test_start_idx == 0


# ---------------------------------------------------------------------------
# generate_kfold_splits — purge zones
# ---------------------------------------------------------------------------

class TestPurgeZones:
    def test_purge_zone_before_test(self) -> None:
        """Training data should not include indices within purge_periods before test start."""
        cfg = _default_config(k=5, purge_periods=10)
        splits = generate_kfold_splits(n_samples=500, config=cfg)
        # Check a middle fold (fold 3) where there's data before and after
        mid = splits[2]
        train_indices = set()
        for start, end in mid.train_ranges:
            train_indices.update(range(start, end))
        purge_before = set(range(max(0, mid.test_start_idx - 10), mid.test_start_idx))
        assert train_indices.isdisjoint(purge_before)

    def test_purge_zone_after_test(self) -> None:
        """Training data should not include indices within purge_periods after test end."""
        cfg = _default_config(k=5, purge_periods=10)
        splits = generate_kfold_splits(n_samples=500, config=cfg)
        mid = splits[2]
        train_indices = set()
        for start, end in mid.train_ranges:
            train_indices.update(range(start, end))
        purge_after = set(range(mid.test_end_idx, min(500, mid.test_end_idx + 10)))
        assert train_indices.isdisjoint(purge_after)

    def test_no_training_in_test_set(self) -> None:
        """Training indices must never overlap with test indices."""
        cfg = _default_config(k=5, purge_periods=10)
        splits = generate_kfold_splits(n_samples=500, config=cfg)
        for s in splits:
            train_indices = set()
            for start, end in s.train_ranges:
                train_indices.update(range(start, end))
            test_indices = set(range(s.test_start_idx, s.test_end_idx))
            assert train_indices.isdisjoint(test_indices)

    def test_first_fold_no_before_purge(self) -> None:
        """First fold has no purge zone before (nothing before index 0)."""
        cfg = _default_config(k=5, purge_periods=10)
        splits = generate_kfold_splits(n_samples=500, config=cfg)
        first = splits[0]
        # Train should start right after test_end + purge
        assert first.train_ranges[0][0] == first.test_end_idx + 10

    def test_last_fold_no_after_purge(self) -> None:
        """Last fold has no purge zone after (nothing after n_samples)."""
        cfg = _default_config(k=5, purge_periods=10)
        splits = generate_kfold_splits(n_samples=500, config=cfg)
        last = splits[-1]
        # Train should end before test_start - purge
        for start, end in last.train_ranges:
            assert end <= last.test_start_idx - 10

    def test_zero_purge(self) -> None:
        """With purge=0, all non-test data is used for training."""
        cfg = _default_config(k=5, purge_periods=0)
        splits = generate_kfold_splits(n_samples=500, config=cfg)
        for s in splits:
            train_indices = set()
            for start, end in s.train_ranges:
                train_indices.update(range(start, end))
            test_indices = set(range(s.test_start_idx, s.test_end_idx))
            assert train_indices | test_indices == set(range(500))

    def test_large_purge_reduces_training(self) -> None:
        """Larger purge zones result in fewer training samples."""
        small = _default_config(k=5, purge_periods=5)
        large = _default_config(k=5, purge_periods=50)
        splits_small = generate_kfold_splits(n_samples=500, config=small)
        splits_large = generate_kfold_splits(n_samples=500, config=large)
        # Compare training sizes for a middle fold
        train_small = sum(e - s for s, e in splits_small[2].train_ranges)
        train_large = sum(e - s for s, e in splits_large[2].train_ranges)
        assert train_large < train_small


# ---------------------------------------------------------------------------
# validate_no_leakage
# ---------------------------------------------------------------------------

class TestValidateNoLeakage:
    def test_valid_splits_pass(self) -> None:
        """Well-formed splits pass validation."""
        cfg = _default_config(k=5, purge_periods=10)
        splits = generate_kfold_splits(n_samples=500, config=cfg)
        validate_no_leakage(splits, purge_periods=10)

    def test_leakage_in_purge_zone_raises(self) -> None:
        """Training index within purge zone raises ValueError."""
        bad_split = KFoldSplit(
            fold_number=1,
            train_ranges=((0, 98),),  # ends at 98, but test starts at 100, purge=10
            test_start_idx=100,
            test_end_idx=200,
        )
        with pytest.raises(ValueError, match="leakage"):
            validate_no_leakage((bad_split,), purge_periods=10)

    def test_leakage_after_test_raises(self) -> None:
        """Training index within purge zone after test raises ValueError."""
        bad_split = KFoldSplit(
            fold_number=1,
            train_ranges=((205, 300),),  # starts at 205, but test ends at 200, purge=10
            test_start_idx=100,
            test_end_idx=200,
        )
        with pytest.raises(ValueError, match="leakage"):
            validate_no_leakage((bad_split,), purge_periods=10)

    def test_train_overlaps_test_raises(self) -> None:
        """Training indices overlapping test set raises ValueError."""
        bad_split = KFoldSplit(
            fold_number=1,
            train_ranges=((0, 150),),  # overlaps test [100, 200)
            test_start_idx=100,
            test_end_idx=200,
        )
        with pytest.raises(ValueError, match="leakage"):
            validate_no_leakage((bad_split,), purge_periods=10)


# ---------------------------------------------------------------------------
# collect_kfold_results
# ---------------------------------------------------------------------------

class TestCollectKFoldResults:
    def test_aggregates_mean_metrics(self) -> None:
        """Mean metrics should average across folds."""
        r1 = _make_fold_result(1, auc_roc=0.55, sharpe=1.2)
        r2 = _make_fold_result(2, auc_roc=0.65, sharpe=0.8)
        result = collect_kfold_results(
            fold_results=[r1, r2],
            config=_default_config(),
        )
        assert abs(result.mean_metrics["auc_roc"] - 0.60) < 1e-10
        assert abs(result.mean_metrics["sharpe_ratio"] - 1.0) < 1e-10

    def test_preserves_folds(self) -> None:
        """All fold results should be preserved in order."""
        r1 = _make_fold_result(1)
        r2 = _make_fold_result(2)
        r3 = _make_fold_result(3)
        result = collect_kfold_results(
            fold_results=[r1, r2, r3],
            config=_default_config(),
        )
        assert len(result.folds) == 3
        assert result.folds[0].fold_number == 1
        assert result.folds[2].fold_number == 3

    def test_empty_folds(self) -> None:
        """Empty fold list produces empty result."""
        result = collect_kfold_results(
            fold_results=[],
            config=_default_config(),
        )
        assert len(result.folds) == 0
        assert result.mean_metrics == {}

    def test_config_preserved(self) -> None:
        """Config is preserved in the result."""
        cfg = _default_config(k=3)
        result = collect_kfold_results(fold_results=[], config=cfg)
        assert result.config.k == 3


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_too_few_samples_raises(self) -> None:
        """Fewer samples than K raises ValueError."""
        cfg = _default_config(k=5, purge_periods=2)
        with pytest.raises(ValueError, match="samples"):
            generate_kfold_splits(n_samples=3, config=cfg)

    def test_k_equals_2(self) -> None:
        """K=2 should work (split in half)."""
        cfg = _default_config(k=2, purge_periods=5)
        splits = generate_kfold_splits(n_samples=200, config=cfg)
        assert len(splits) == 2

    def test_purge_larger_than_fold_clamps(self) -> None:
        """If purge is larger than adjacent data, training range is simply empty/smaller."""
        cfg = _default_config(k=5, purge_periods=200)
        splits = generate_kfold_splits(n_samples=500, config=cfg)
        # Should still produce K splits (train may be very small)
        assert len(splits) == 5
        # No leakage even with huge purge
        validate_no_leakage(splits, purge_periods=200)

    def test_n_samples_not_divisible_by_k(self) -> None:
        """Remainder samples go to the last fold."""
        cfg = _default_config(k=3, purge_periods=2)
        splits = generate_kfold_splits(n_samples=101, config=cfg)
        # First two folds: 33 each, last fold: 35
        assert splits[0].test_end_idx - splits[0].test_start_idx == 33
        assert splits[-1].test_end_idx - splits[-1].test_start_idx == 35
