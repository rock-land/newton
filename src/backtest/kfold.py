"""Purged K-fold cross-validation (T-604, SPEC §9.1).

Secondary validation method: K=5 with 48-hour purge zones between
train/test boundaries to prevent temporal data leakage.  Complements
walk-forward (T-303) as a robustness check.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Domain models — all frozen per DEC-010
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class KFoldConfig:
    """Configuration for purged K-fold cross-validation.

    Defaults per SPEC §9.1: K=5, 48-hour purge zones (hourly data).
    """

    k: int
    purge_periods: int


@dataclass(frozen=True)
class KFoldSplit:
    """Index boundaries for a single K-fold split.

    train_ranges: non-contiguous (start, end) exclusive ranges for training data.
        Gaps exist where the test set and purge zones are.
    test_start_idx / test_end_idx: contiguous test range [start, end).
    """

    fold_number: int
    train_ranges: tuple[tuple[int, int], ...]
    test_start_idx: int
    test_end_idx: int


@dataclass(frozen=True)
class KFoldFoldResult:
    """Results from a single K-fold split."""

    fold_number: int
    metrics: dict[str, float]
    test_predictions: tuple[float, ...]
    test_labels: tuple[int, ...]


@dataclass(frozen=True)
class KFoldResult:
    """Aggregated results across all K-fold splits."""

    config: KFoldConfig
    folds: tuple[KFoldFoldResult, ...]
    mean_metrics: dict[str, float]


# ---------------------------------------------------------------------------
# Fold generation
# ---------------------------------------------------------------------------


def generate_kfold_splits(
    *,
    n_samples: int,
    config: KFoldConfig,
) -> tuple[KFoldSplit, ...]:
    """Generate purged K-fold split boundaries.

    Divides data into K contiguous blocks.  For each fold, the test set
    is one block; the training set is all other data minus purge zones
    around the test boundaries.

    Args:
        n_samples: Total number of data points.
        config: K-fold configuration (k, purge_periods).

    Returns:
        Tuple of K ``KFoldSplit`` objects.

    Raises:
        ValueError: If n_samples < k (not enough data for K folds).
    """
    k = config.k
    purge = config.purge_periods

    if n_samples < k:
        raise ValueError(
            f"Insufficient samples: {n_samples} < k={k}. "
            f"Need at least {k} samples for {k}-fold split."
        )

    block_size = n_samples // k
    splits: list[KFoldSplit] = []

    for i in range(k):
        test_start = i * block_size
        test_end = (i + 1) * block_size if i < k - 1 else n_samples

        # Purge zones: remove purge_periods before test_start and after test_end
        purge_start = max(0, test_start - purge)
        purge_end = min(n_samples, test_end + purge)

        # Build training ranges (non-contiguous)
        train_ranges: list[tuple[int, int]] = []
        if purge_start > 0:
            train_ranges.append((0, purge_start))
        if purge_end < n_samples:
            train_ranges.append((purge_end, n_samples))

        splits.append(KFoldSplit(
            fold_number=i + 1,
            train_ranges=tuple(train_ranges),
            test_start_idx=test_start,
            test_end_idx=test_end,
        ))

    logger.info(
        "Generated %d purged K-fold splits (purge=%d periods, n_samples=%d)",
        k, purge, n_samples,
    )

    return tuple(splits)


# ---------------------------------------------------------------------------
# Leakage validation
# ---------------------------------------------------------------------------


def validate_no_leakage(
    splits: tuple[KFoldSplit, ...],
    purge_periods: int,
) -> None:
    """Verify that no fold has temporal data leakage.

    Checks that no training index falls within the test set or
    within purge_periods of the test boundaries.

    Args:
        splits: Generated K-fold splits to validate.
        purge_periods: Number of periods for purge zones.

    Raises:
        ValueError: If any split has leakage.
    """
    for split in splits:
        excluded_start = max(0, split.test_start_idx - purge_periods)
        excluded_end = split.test_end_idx + purge_periods

        for train_start, train_end in split.train_ranges:
            # Check if any training range overlaps with the excluded zone
            if train_start < excluded_end and train_end > excluded_start:
                raise ValueError(
                    f"Fold {split.fold_number} has temporal data leakage: "
                    f"training range [{train_start}, {train_end}) overlaps "
                    f"excluded zone [{excluded_start}, {excluded_end})"
                )


# ---------------------------------------------------------------------------
# Result aggregation
# ---------------------------------------------------------------------------


def collect_kfold_results(
    *,
    fold_results: list[KFoldFoldResult],
    config: KFoldConfig,
) -> KFoldResult:
    """Aggregate per-fold results into a single KFoldResult.

    Computes mean metrics across all folds.

    Args:
        fold_results: List of per-fold results.
        config: K-fold configuration.

    Returns:
        Frozen KFoldResult with aggregated mean metrics.
    """
    if not fold_results:
        return KFoldResult(
            config=config,
            folds=(),
            mean_metrics={},
        )

    # Collect all metric keys and sum values
    metric_sums: dict[str, float] = defaultdict(float)
    for fr in fold_results:
        for key, value in fr.metrics.items():
            metric_sums[key] += value

    n = len(fold_results)
    mean_metrics = {key: total / n for key, total in metric_sums.items()}

    result = KFoldResult(
        config=config,
        folds=tuple(fold_results),
        mean_metrics=mean_metrics,
    )

    logger.info(
        "K-fold complete: %d folds, mean metrics: %s",
        n,
        {k: f"{v:.4f}" for k, v in mean_metrics.items()},
    )

    return result
