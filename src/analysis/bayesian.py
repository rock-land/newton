"""Bayesian inference engine (SPEC §5.5).

Naïve Bayes classifier with Laplace-smoothed likelihoods, log-odds prediction,
isotonic calibration on out-of-fold predictions, configurable posterior cap,
and pairwise phi correlation checks.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime

from src.analysis.events import EventLabel
from src.analysis.tokenizer import TokenSet

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TokenLikelihood:
    """Per-token conditional probabilities."""

    token: str
    p_given_event: float
    p_given_no_event: float


@dataclass(frozen=True)
class BayesianModel:
    """Trained Bayesian model parameters (frozen, serializable)."""

    event_type: str
    prior: float
    likelihoods: tuple[TokenLikelihood, ...]
    calibration_x: tuple[float, ...]
    calibration_y: tuple[float, ...]
    posterior_cap: float


@dataclass(frozen=True)
class CorrelationWarning:
    """Record of a high inter-token phi correlation."""

    token_a: str
    token_b: str
    phi: float


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def train(
    token_sets: list[TokenSet],
    event_labels: list[EventLabel],
    selected_tokens: list[str],
    event_type: str,
    *,
    laplace_alpha: float = 1.0,
    posterior_cap: float = 0.90,
    n_folds: int = 5,
) -> BayesianModel:
    """Train a Bayesian model for *event_type*.

    1. Aligns token sets and event labels by timestamp.
    2. Computes prior P(Event) and per-token likelihoods with Laplace smoothing.
    3. Generates out-of-fold predictions via K-fold cross-validation.
    4. Fits isotonic calibration on out-of-fold predictions.
    5. Runs pairwise phi correlation check on selected tokens.
    """
    _default = BayesianModel(
        event_type=event_type,
        prior=0.5,
        likelihoods=(),
        calibration_x=(0.0, 1.0),
        calibration_y=(0.0, 1.0),
        posterior_cap=posterior_cap,
    )

    if not token_sets or not event_labels:
        return _default

    aligned = _align_data(token_sets, event_labels, selected_tokens, event_type)
    if not aligned:
        return _default

    # Prior and likelihoods on full dataset.
    labels = [lab for _, lab in aligned]
    prior = _compute_prior(labels)
    likes = _compute_likelihoods(aligned, selected_tokens, laplace_alpha)

    # Out-of-fold predictions for calibration.
    raw_preds, true_labs = _out_of_fold_predictions(
        aligned, selected_tokens, laplace_alpha, n_folds,
    )
    cal_x, cal_y = _fit_isotonic(raw_preds, true_labs)

    # Phi correlation check at training time (SPEC §5.5).
    if selected_tokens:
        check_correlations(token_sets, selected_tokens)

    return BayesianModel(
        event_type=event_type,
        prior=prior,
        likelihoods=tuple(likes),
        calibration_x=cal_x,
        calibration_y=cal_y,
        posterior_cap=posterior_cap,
    )


def predict(model: BayesianModel, active_tokens: frozenset[str]) -> float:
    """Predict posterior probability using log-odds form with calibration.

    Per SPEC §5.5::

        log_odds = log(P(E)/P(~E)) + sum(log(P(Ti|E)/P(Ti|~E)))
        raw = sigmoid(log_odds)
        calibrated = isotonic(raw)
        result = min(calibrated, posterior_cap)
    """
    raw = _raw_predict(model.prior, model.likelihoods, active_tokens)
    calibrated = _apply_calibration(raw, model.calibration_x, model.calibration_y)
    return min(calibrated, model.posterior_cap)


def compute_phi_coefficient(
    token_sets: list[TokenSet],
    token_a: str,
    token_b: str,
) -> float:
    """Compute Matthews (phi) correlation coefficient between two tokens.

    ``phi = (ad - bc) / sqrt((a+b)(c+d)(a+c)(b+d))``
    where a=both, b=only_a, c=only_b, d=neither.
    Returns 0.0 if any marginal is zero.
    """
    a = b = c = d = 0
    for ts in token_sets:
        has_a = token_a in ts.tokens
        has_b = token_b in ts.tokens
        if has_a and has_b:
            a += 1
        elif has_a:
            b += 1
        elif has_b:
            c += 1
        else:
            d += 1

    denom_sq = (a + b) * (c + d) * (a + c) * (b + d)
    if denom_sq == 0:
        return 0.0
    return (a * d - b * c) / math.sqrt(denom_sq)


def check_correlations(
    token_sets: list[TokenSet],
    selected_tokens: list[str],
    *,
    threshold: float = 0.7,
) -> list[CorrelationWarning]:
    """Check pairwise phi correlations and log warnings per SPEC §5.5.

    Warns per pair if ``|phi| > threshold``.  Alerts and recommends reducing
    the token set if more than 3 pairs exceed the threshold.
    """
    warnings: list[CorrelationWarning] = []
    for i, ta in enumerate(selected_tokens):
        for tb in selected_tokens[i + 1 :]:
            phi = compute_phi_coefficient(token_sets, ta, tb)
            if abs(phi) > threshold:
                warnings.append(CorrelationWarning(token_a=ta, token_b=tb, phi=phi))
                logger.warning(
                    "High phi correlation between %s and %s: phi=%.4f "
                    "(threshold=%.2f)",
                    ta,
                    tb,
                    phi,
                    threshold,
                )

    if len(warnings) > 3:
        logger.warning(
            "ALERT: %d token pairs exceed phi threshold %.2f. "
            "Consider reducing token set to improve independence assumption.",
            len(warnings),
            threshold,
        )

    return warnings


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _align_data(
    token_sets: list[TokenSet],
    event_labels: list[EventLabel],
    selected_tokens: list[str],
    event_type: str,
) -> list[tuple[frozenset[str], bool]]:
    """Align token sets and event labels by timestamp.

    Filters tokens to only those in *selected_tokens*.
    """
    selected_set = frozenset(selected_tokens)

    label_by_time: dict[datetime, bool] = {}
    for lbl in event_labels:
        if lbl.event_type == event_type:
            label_by_time[lbl.time] = lbl.label

    aligned: list[tuple[frozenset[str], bool]] = []
    for ts in token_sets:
        if ts.time in label_by_time:
            active = ts.tokens & selected_set
            aligned.append((active, label_by_time[ts.time]))
    return aligned


def _compute_prior(labels: list[bool]) -> float:
    """``P(Event) = count(True) / count(all)``."""
    if not labels:
        return 0.5
    return sum(1 for lab in labels if lab) / len(labels)


def _compute_likelihoods(
    aligned: list[tuple[frozenset[str], bool]],
    selected_tokens: list[str],
    alpha: float,
) -> list[TokenLikelihood]:
    """Compute ``P(Token|Event)`` and ``P(Token|~Event)`` with Laplace smoothing."""
    n_event = sum(1 for _, lab in aligned if lab)
    n_no_event = len(aligned) - n_event

    result: list[TokenLikelihood] = []
    for token in selected_tokens:
        present_event = sum(1 for toks, lab in aligned if lab and token in toks)
        present_no_event = sum(
            1 for toks, lab in aligned if not lab and token in toks
        )

        p_given_event = (present_event + alpha) / (n_event + 2 * alpha)
        p_given_no_event = (present_no_event + alpha) / (n_no_event + 2 * alpha)

        result.append(
            TokenLikelihood(
                token=token,
                p_given_event=p_given_event,
                p_given_no_event=p_given_no_event,
            )
        )
    return result


def _out_of_fold_predictions(
    aligned: list[tuple[frozenset[str], bool]],
    selected_tokens: list[str],
    laplace_alpha: float,
    n_folds: int,
) -> tuple[list[float], list[bool]]:
    """Generate out-of-fold raw posteriors via K-fold cross-validation."""
    n = len(aligned)
    if n < 2:
        return [], []

    effective_folds = min(n_folds, n)
    fold_size = n // effective_folds

    raw_preds: list[float] = []
    true_labs: list[bool] = []

    for fold in range(effective_folds):
        start = fold * fold_size
        end = (start + fold_size) if fold < effective_folds - 1 else n

        train_data = aligned[:start] + aligned[end:]
        test_data = aligned[start:end]

        if not train_data:
            continue

        fold_prior = _compute_prior([lab for _, lab in train_data])
        fold_likes = _compute_likelihoods(train_data, selected_tokens, laplace_alpha)

        for active_tokens, label in test_data:
            raw = _raw_predict(fold_prior, tuple(fold_likes), active_tokens)
            raw_preds.append(raw)
            true_labs.append(label)

    return raw_preds, true_labs


def _raw_predict(
    prior: float,
    likelihoods: tuple[TokenLikelihood, ...],
    active_tokens: frozenset[str],
) -> float:
    """Log-odds prediction without calibration."""
    # Clamp prior to avoid log(0).
    p = max(1e-10, min(1.0 - 1e-10, prior))
    log_odds = math.log(p / (1.0 - p))

    for tl in likelihoods:
        if tl.token in active_tokens:
            p_e = max(1e-10, tl.p_given_event)
            p_ne = max(1e-10, tl.p_given_no_event)
            log_odds += math.log(p_e / p_ne)

    return _sigmoid(log_odds)


def _sigmoid(x: float) -> float:
    """Numerically stable sigmoid function."""
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    exp_x = math.exp(x)
    return exp_x / (1.0 + exp_x)


def _fit_isotonic(
    raw_probs: list[float],
    true_labels: list[bool],
) -> tuple[tuple[float, ...], tuple[float, ...]]:
    """Fit isotonic regression via pool-adjacent-violators algorithm (PAVA).

    Returns ``(x_values, y_values)`` for piecewise-linear interpolation.
    Falls back to identity mapping ``(0, 1) → (0, 1)`` when input is empty.
    """
    if not raw_probs:
        return (0.0, 1.0), (0.0, 1.0)

    pairs = sorted(zip(raw_probs, (1.0 if lab else 0.0 for lab in true_labels)))

    # PAVA — each block tracks [sum_y, count, min_x, max_x].
    blocks: list[list[float]] = []
    for x, y in pairs:
        blocks.append([y, 1.0, x, x])
        while len(blocks) >= 2:
            prev_mean = blocks[-2][0] / blocks[-2][1]
            curr_mean = blocks[-1][0] / blocks[-1][1]
            if prev_mean > curr_mean:
                merged = [
                    blocks[-2][0] + blocks[-1][0],
                    blocks[-2][1] + blocks[-1][1],
                    blocks[-2][2],
                    blocks[-1][3],
                ]
                blocks.pop()
                blocks.pop()
                blocks.append(merged)
            else:
                break

    x_vals = tuple((blk[2] + blk[3]) / 2.0 for blk in blocks)
    y_vals = tuple(blk[0] / blk[1] for blk in blocks)
    return x_vals, y_vals


def _apply_calibration(
    raw: float,
    cal_x: tuple[float, ...],
    cal_y: tuple[float, ...],
) -> float:
    """Apply isotonic calibration via piecewise-linear interpolation."""
    if not cal_x:
        return raw
    if len(cal_x) == 1:
        return cal_y[0]
    if raw <= cal_x[0]:
        return cal_y[0]
    if raw >= cal_x[-1]:
        return cal_y[-1]

    for i in range(len(cal_x) - 1):
        if cal_x[i] <= raw <= cal_x[i + 1]:
            span = cal_x[i + 1] - cal_x[i]
            t = (raw - cal_x[i]) / span if span > 0 else 0.0
            return cal_y[i] + t * (cal_y[i + 1] - cal_y[i])

    return cal_y[-1]
