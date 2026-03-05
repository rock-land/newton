"""Regime-aware backtest reporting (T-605, SPEC §9.3–9.4).

Produces a BacktestReport with per-regime performance breakdown,
regime transition timeline, regime-adjusted metrics weighted by
time-in-regime, low-sample flagging, and bias controls checklist.
"""

from __future__ import annotations

import logging
import math
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone

from src.backtest.engine import BacktestResult, BacktestTrade
from src.backtest.metrics import (
    GateEvaluation,
    PerformanceMetrics,
    compute_metrics,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Domain models — all frozen per DEC-010
# ---------------------------------------------------------------------------

_PF_CAP = 999.9
_LOW_SAMPLE_DEFAULT = 20


@dataclass(frozen=True)
class ReportConfig:
    """Configuration for report generation."""

    low_sample_threshold: int
    annualization_factor: float


@dataclass(frozen=True)
class RegimePerformance:
    """Performance metrics for a single regime label."""

    regime_label: str
    sharpe_ratio: float
    profit_factor: float
    win_rate: float
    trade_count: int
    total_pnl: float
    low_sample_flag: bool


@dataclass(frozen=True)
class RegimeTransition:
    """A single regime transition point."""

    time: datetime
    regime_label: str


@dataclass(frozen=True)
class BiasControl:
    """One entry from the §9.3 bias controls checklist."""

    bias_name: str
    mitigation: str
    status: str  # "APPLIED", "FLAGGED", "NOT_APPLICABLE"


@dataclass(frozen=True)
class BacktestReport:
    """Complete regime-aware backtest report."""

    instrument: str
    metrics: PerformanceMetrics
    gate_evaluation: GateEvaluation
    regime_breakdown: dict[str, RegimePerformance]
    regime_timeline: tuple[RegimeTransition, ...]
    regime_adjusted_metrics: dict[str, float]
    bias_controls: tuple[BiasControl, ...]
    low_sample_regimes: tuple[str, ...]
    generated_at: datetime


# ---------------------------------------------------------------------------
# Regime breakdown
# ---------------------------------------------------------------------------


def compute_regime_breakdown(
    trades: Sequence[BacktestTrade],
    annualization_factor: float,
    *,
    low_sample_threshold: int = _LOW_SAMPLE_DEFAULT,
) -> dict[str, RegimePerformance]:
    """Compute per-regime performance metrics.

    Groups trades by ``regime_label`` and computes Sharpe, profit factor,
    win rate, trade count, and total PnL per group.  Flags regimes with
    fewer than ``low_sample_threshold`` trades.

    Args:
        trades: Completed backtest trades.
        annualization_factor: sqrt(252) for forex, sqrt(365) for crypto.
        low_sample_threshold: Minimum trade count before flagging.

    Returns:
        Dict mapping regime label to RegimePerformance.
    """
    if not trades:
        return {}

    grouped: dict[str, list[BacktestTrade]] = defaultdict(list)
    for t in trades:
        grouped[t.regime_label].append(t)

    result: dict[str, RegimePerformance] = {}
    for label, regime_trades in grouped.items():
        pnls = [t.pnl for t in regime_trades]
        total_pnl = sum(pnls)
        n = len(regime_trades)
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]
        win_rate = len(wins) / n

        # Profit factor
        winning_sum = sum(wins)
        losing_sum = abs(sum(losses))
        if losing_sum == 0:
            profit_factor = _PF_CAP if winning_sum > 0 else 0.0
        else:
            profit_factor = winning_sum / losing_sum

        # Sharpe from trade PnLs
        sharpe = _sharpe_from_pnls(pnls, annualization_factor)

        result[label] = RegimePerformance(
            regime_label=label,
            sharpe_ratio=sharpe,
            profit_factor=profit_factor,
            win_rate=win_rate,
            trade_count=n,
            total_pnl=total_pnl,
            low_sample_flag=n < low_sample_threshold,
        )

    logger.info(
        "Regime breakdown: %s",
        {k: f"{v.trade_count} trades, Sharpe={v.sharpe_ratio:.3f}" for k, v in result.items()},
    )

    return result


# ---------------------------------------------------------------------------
# Regime timeline
# ---------------------------------------------------------------------------


def build_regime_timeline(
    regime_labels: Sequence[tuple[datetime, str]],
) -> tuple[RegimeTransition, ...]:
    """Build regime transition timeline from per-bar labels.

    Emits a ``RegimeTransition`` at each point where the regime label
    changes (including the first point).

    Args:
        regime_labels: Sequence of (timestamp, regime_label) pairs, ordered
            chronologically.

    Returns:
        Tuple of RegimeTransition objects at transition points.
    """
    if not regime_labels:
        return ()

    transitions: list[RegimeTransition] = []
    prev_label: str | None = None

    for time, label in regime_labels:
        if label != prev_label:
            transitions.append(RegimeTransition(time=time, regime_label=label))
            prev_label = label

    return tuple(transitions)


# ---------------------------------------------------------------------------
# Regime-adjusted metrics
# ---------------------------------------------------------------------------


def compute_regime_adjusted_metrics(
    regime_breakdown: dict[str, RegimePerformance],
    regime_durations: dict[str, float],
) -> dict[str, float]:
    """Compute regime-adjusted metrics weighted by time-in-regime.

    Excludes low-sample regimes from weighting and renormalizes weights
    for remaining regimes.

    Args:
        regime_breakdown: Per-regime performance from compute_regime_breakdown().
        regime_durations: Fraction of time in each regime (values should sum ~1.0).

    Returns:
        Dict with weighted 'sharpe_ratio', 'profit_factor', 'win_rate'.
        Empty dict if no valid (non-low-sample) regimes.
    """
    if not regime_breakdown:
        return {}

    # Filter to non-low-sample regimes that have durations
    valid: list[tuple[str, RegimePerformance, float]] = []
    for label, perf in regime_breakdown.items():
        if not perf.low_sample_flag and label in regime_durations:
            valid.append((label, perf, regime_durations[label]))

    if not valid:
        return {}

    # Renormalize weights
    total_weight = sum(w for _, _, w in valid)
    if total_weight == 0:
        return {}

    weighted_sharpe = sum(p.sharpe_ratio * (w / total_weight) for _, p, w in valid)
    weighted_pf = sum(p.profit_factor * (w / total_weight) for _, p, w in valid)
    weighted_wr = sum(p.win_rate * (w / total_weight) for _, p, w in valid)

    return {
        "sharpe_ratio": weighted_sharpe,
        "profit_factor": weighted_pf,
        "win_rate": weighted_wr,
    }


# ---------------------------------------------------------------------------
# Bias controls checklist
# ---------------------------------------------------------------------------

_BIAS_CONTROLS = [
    (
        "look_ahead",
        "Walk-forward with 48h embargo; events use only past data",
    ),
    (
        "overfitting",
        "Walk-forward + purged K-fold; minimum trade count per fold",
    ),
    (
        "survivorship",
        "Flagged for BTC/USDT",
    ),
    (
        "selection",
        "Fixed event catalog and token methodology",
    ),
    (
        "data_snooping",
        "Hyperparameter search within training windows only",
    ),
]


def build_bias_controls(
    *,
    has_walk_forward: bool = True,
    has_kfold: bool = True,
    instrument: str = "EUR_USD",
) -> tuple[BiasControl, ...]:
    """Build §9.3 bias controls checklist.

    Args:
        has_walk_forward: Whether walk-forward validation was performed.
        has_kfold: Whether purged K-fold validation was performed.
        instrument: Instrument identifier (survivorship flagged for BTC).

    Returns:
        Tuple of 5 BiasControl entries per §9.3 table.
    """
    controls: list[BiasControl] = []

    for name, mitigation in _BIAS_CONTROLS:
        if name == "look_ahead":
            status = "APPLIED" if has_walk_forward else "FLAGGED"
        elif name == "overfitting":
            status = "APPLIED" if (has_walk_forward and has_kfold) else "FLAGGED"
        elif name == "survivorship":
            status = "FLAGGED" if "BTC" in instrument.upper() else "NOT_APPLICABLE"
        else:
            # selection and data_snooping are always APPLIED
            status = "APPLIED"

        controls.append(BiasControl(
            bias_name=name,
            mitigation=mitigation,
            status=status,
        ))

    return tuple(controls)


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def generate_report(
    result: BacktestResult,
    *,
    config: ReportConfig,
    gate_evaluation: GateEvaluation,
    regime_labels: Sequence[tuple[datetime, str]] | None = None,
    has_walk_forward: bool = True,
    has_kfold: bool = True,
) -> BacktestReport:
    """Generate a complete regime-aware backtest report.

    Args:
        result: Output of run_backtest().
        config: Report configuration (thresholds, annualization).
        gate_evaluation: Pre-computed gate evaluation from metrics module.
        regime_labels: Optional per-bar (timestamp, regime_label) for timeline.
        has_walk_forward: Whether walk-forward validation was performed.
        has_kfold: Whether purged K-fold validation was performed.

    Returns:
        Frozen BacktestReport dataclass.
    """
    instrument = result.config.instrument

    # Compute overall metrics
    metrics = compute_metrics(
        result,
        annualization_factor=config.annualization_factor,
    )

    # Per-regime breakdown
    breakdown = compute_regime_breakdown(
        result.trades,
        config.annualization_factor,
        low_sample_threshold=config.low_sample_threshold,
    )

    # Regime timeline
    timeline = build_regime_timeline(regime_labels) if regime_labels else ()

    # Regime durations (from labels if available, else equal weighting)
    durations = _compute_durations(regime_labels, breakdown)

    # Regime-adjusted metrics
    adjusted = compute_regime_adjusted_metrics(breakdown, durations)

    # Low-sample regimes
    low_sample = tuple(
        label for label, perf in breakdown.items() if perf.low_sample_flag
    )

    # Bias controls
    bias = build_bias_controls(
        has_walk_forward=has_walk_forward,
        has_kfold=has_kfold,
        instrument=instrument,
    )

    report = BacktestReport(
        instrument=instrument,
        metrics=metrics,
        gate_evaluation=gate_evaluation,
        regime_breakdown=breakdown,
        regime_timeline=timeline,
        regime_adjusted_metrics=adjusted,
        bias_controls=bias,
        low_sample_regimes=low_sample,
        generated_at=datetime.now(timezone.utc),
    )

    logger.info(
        "Report generated for %s: %d regimes, %d low-sample, %d bias controls",
        instrument,
        len(breakdown),
        len(low_sample),
        len(bias),
    )

    return report


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _sharpe_from_pnls(pnls: list[float], annualization_factor: float) -> float:
    """Sharpe ratio from a list of trade PnLs."""
    if len(pnls) < 2:
        return 0.0
    mean_pnl = sum(pnls) / len(pnls)
    variance = sum((p - mean_pnl) ** 2 for p in pnls) / (len(pnls) - 1)
    std_pnl = math.sqrt(variance)
    if std_pnl == 0:
        return 0.0
    return (mean_pnl / std_pnl) * annualization_factor


def _compute_durations(
    regime_labels: Sequence[tuple[datetime, str]] | None,
    breakdown: dict[str, RegimePerformance],
) -> dict[str, float]:
    """Derive regime time fractions from labels or equal-weight from breakdown."""
    if regime_labels and len(regime_labels) > 0:
        counts: dict[str, int] = defaultdict(int)
        for _, label in regime_labels:
            counts[label] += 1
        total = sum(counts.values())
        return {label: count / total for label, count in counts.items()}

    # Fallback: equal weight per regime
    n = len(breakdown)
    if n == 0:
        return {}
    weight = 1.0 / n
    return {label: weight for label in breakdown}
