"""Walk-forward training framework (T-303).

Provides walk-forward cross-validation with configurable train/test window
sizes, embargo periods between train and test sets, and out-of-fold
prediction collection for meta-learner training.

SPEC §5.6: "Walk-forward: train on rolling 2-year window, validate on
next 6 months."  Window sizes are configurable in period units.

This module defines fold boundaries and aggregates results.  Model training
is performed by the caller (T-304 XGBoost, T-306 meta-learner).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WalkForwardConfig:
    """Configuration for walk-forward cross-validation.

    All window sizes are in period units (e.g., hourly candles).
    Defaults assume hourly data:
      - train_periods: 17520 (~2 years)
      - test_periods: 4380 (~6 months)
      - step_periods: 4380 (~6 months)
      - embargo_periods: 48 (48 hours)
    """

    train_periods: int
    test_periods: int
    step_periods: int
    embargo_periods: int
    min_folds: int


@dataclass(frozen=True)
class WalkForwardFold:
    """Index boundaries for a single walk-forward fold.

    Indices are into the FeatureMatrix rows:
      - train: [train_start_idx, train_end_idx)  (exclusive end)
      - test:  [test_start_idx, test_end_idx)     (exclusive end)
    """

    fold_number: int
    train_start_idx: int
    train_end_idx: int
    test_start_idx: int
    test_end_idx: int


@dataclass(frozen=True)
class FoldResult:
    """Results from a single walk-forward fold."""

    fold_number: int
    metrics: dict[str, float]
    test_predictions: tuple[float, ...]
    test_labels: tuple[int, ...]
    test_timestamps: tuple[datetime, ...]


@dataclass(frozen=True)
class WalkForwardResult:
    """Aggregated results across all walk-forward folds."""

    config: WalkForwardConfig
    folds: tuple[FoldResult, ...]
    oof_predictions: tuple[float, ...]
    oof_labels: tuple[int, ...]
    oof_timestamps: tuple[datetime, ...]
    mean_auc_roc: float


def generate_folds(
    *,
    n_samples: int,
    config: WalkForwardConfig,
) -> tuple[WalkForwardFold, ...]:
    """Generate walk-forward fold boundaries using a rolling window.

    Each fold's training window advances by ``step_periods``.  An embargo
    gap of ``embargo_periods`` separates train end from test start to
    prevent look-ahead bias.

    Raises:
        ValueError: If insufficient data to produce ``min_folds`` folds.
    """
    folds: list[WalkForwardFold] = []
    fold_num = 0

    train_start = 0
    while True:
        train_end = train_start + config.train_periods
        test_start = train_end + config.embargo_periods
        test_end = test_start + config.test_periods

        if test_end > n_samples:
            break

        fold_num += 1
        folds.append(
            WalkForwardFold(
                fold_number=fold_num,
                train_start_idx=train_start,
                train_end_idx=train_end,
                test_start_idx=test_start,
                test_end_idx=test_end,
            )
        )

        train_start += config.step_periods

    if len(folds) < config.min_folds:
        raise ValueError(
            f"Insufficient data: {n_samples} samples produce {len(folds)} folds, "
            f"but min_folds={config.min_folds} required. "
            f"Need at least {_min_samples(config)} samples."
        )

    logger.info(
        "Generated %d walk-forward folds (train=%d, test=%d, embargo=%d, step=%d)",
        len(folds),
        config.train_periods,
        config.test_periods,
        config.embargo_periods,
        config.step_periods,
    )

    return tuple(folds)


def validate_no_lookahead(
    folds: tuple[WalkForwardFold, ...],
    embargo_periods: int,
) -> None:
    """Verify that no fold has look-ahead bias.

    Checks:
      1. For every fold, train_end + embargo <= test_start.
      2. Train end is strictly before test start.

    Raises:
        ValueError: If any fold violates the no-lookahead constraint.
    """
    for fold in folds:
        if fold.train_end_idx + embargo_periods > fold.test_start_idx:
            raise ValueError(
                f"Fold {fold.fold_number} has lookahead violation: "
                f"train_end={fold.train_end_idx} + embargo={embargo_periods} "
                f"= {fold.train_end_idx + embargo_periods} > "
                f"test_start={fold.test_start_idx}"
            )
        if fold.train_end_idx >= fold.test_start_idx:
            raise ValueError(
                f"Fold {fold.fold_number} has lookahead violation: "
                f"train_end={fold.train_end_idx} >= test_start={fold.test_start_idx}"
            )


def collect_results(
    *,
    fold_results: list[FoldResult],
    config: WalkForwardConfig,
) -> WalkForwardResult:
    """Aggregate per-fold results into a single WalkForwardResult.

    Concatenates out-of-fold predictions, labels, and timestamps across
    all folds.  Computes mean AUC-ROC from per-fold metrics.
    """
    all_predictions: list[float] = []
    all_labels: list[int] = []
    all_timestamps: list[datetime] = []
    auc_values: list[float] = []

    for fr in fold_results:
        all_predictions.extend(fr.test_predictions)
        all_labels.extend(fr.test_labels)
        all_timestamps.extend(fr.test_timestamps)
        auc = fr.metrics.get("auc_roc", 0.0)
        auc_values.append(auc)

    mean_auc = sum(auc_values) / len(auc_values) if auc_values else 0.0

    result = WalkForwardResult(
        config=config,
        folds=tuple(fold_results),
        oof_predictions=tuple(all_predictions),
        oof_labels=tuple(all_labels),
        oof_timestamps=tuple(all_timestamps),
        mean_auc_roc=mean_auc,
    )

    logger.info(
        "Walk-forward complete: %d folds, mean AUC-ROC=%.4f, %d OOF predictions",
        len(fold_results),
        mean_auc,
        len(all_predictions),
    )

    return result


def _min_samples(config: WalkForwardConfig) -> int:
    """Compute minimum samples needed for min_folds folds."""
    return (
        config.train_periods
        + config.embargo_periods
        + config.test_periods
        + (config.min_folds - 1) * config.step_periods
    )
