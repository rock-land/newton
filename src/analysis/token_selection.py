"""Token selection via mutual information (SPEC §5.4).

For each event type, computes mutual information I(Token; Event) across all
candidate tokens, removes redundant tokens using Jaccard similarity, and
selects the top-N tokens for the Bayesian inference engine.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime

from src.analysis.events import EventLabel
from src.analysis.tokenizer import TokenSet

logger = logging.getLogger(__name__)

# Absolute maximum tokens the SPEC allows (§5.4 step 4).
_MAX_TOKENS = 50


@dataclass(frozen=True)
class TokenScore:
    """A token with its mutual information score."""

    token: str
    mi_score: float


@dataclass(frozen=True)
class SelectedTokenSet:
    """Result of token selection for a single event type."""

    event_type: str
    tokens: tuple[TokenScore, ...]
    dropped_redundant: tuple[str, ...]


def compute_mutual_information(
    token_sets: list[TokenSet],
    event_labels: list[EventLabel],
    event_type: str,
) -> list[TokenScore]:
    """Compute I(Token; Event) for every token that appears in *token_sets*.

    Returns a list of :class:`TokenScore` sorted descending by MI.  Tokens
    that never appear in any token set are excluded from results.
    """
    if not token_sets or not event_labels:
        return []

    # Build a lookup: time → event label (True/False) for the requested type.
    label_by_time: dict[datetime, bool] = {}
    for lbl in event_labels:
        if lbl.event_type == event_type:
            label_by_time[lbl.time] = lbl.label

    # Collect the vocabulary and build per-timestamp presence flags.
    vocab: set[str] = set()
    for ts in token_sets:
        vocab.update(ts.tokens)

    if not vocab:
        return []

    # Build contingency tables: for each token count (a, b, c, d).
    #   a = token present  AND event true
    #   b = token present  AND event false
    #   c = token absent   AND event true
    #   d = token absent   AND event false
    counts: dict[str, list[int]] = {t: [0, 0, 0, 0] for t in vocab}
    n = 0

    for ts in token_sets:
        if ts.time not in label_by_time:
            continue
        event_true = label_by_time[ts.time]
        n += 1
        for token in vocab:
            present = token in ts.tokens
            idx = _cell_index(present, event_true)
            counts[token][idx] += 1

    if n == 0:
        return []

    scores: list[TokenScore] = []
    for token, cells in counts.items():
        mi = _mi_from_contingency(cells, n)
        scores.append(TokenScore(token=token, mi_score=mi))

    scores.sort(key=lambda s: s.mi_score, reverse=True)
    return scores


def jaccard_similarity(
    token_sets: list[TokenSet],
    token_a: str,
    token_b: str,
) -> float:
    """Compute Jaccard similarity between two tokens' activation sets.

    Returns ``|A ∩ B| / |A ∪ B|`` where A and B are the sets of timestamps
    at which each token is active.  Returns 0.0 if both sets are empty.
    """
    intersection = 0
    union = 0
    for ts in token_sets:
        a_present = token_a in ts.tokens
        b_present = token_b in ts.tokens
        if a_present or b_present:
            union += 1
        if a_present and b_present:
            intersection += 1

    if union == 0:
        return 0.0
    return intersection / union


def select_tokens(
    token_sets: list[TokenSet],
    event_labels: list[EventLabel],
    event_type: str,
    *,
    top_n: int = 20,
    jaccard_threshold: float = 0.85,
) -> SelectedTokenSet:
    """Select the top tokens for *event_type* ranked by mutual information.

    1. Compute MI for all candidate tokens.
    2. Sort descending by MI.
    3. Greedily select tokens; skip any whose Jaccard similarity with an
       already-selected token exceeds *jaccard_threshold*.
    4. Return at most ``min(top_n, 50)`` tokens.

    Per SPEC §5.4 step 5, logs the selected token set and MI scores.
    """
    effective_top_n = min(top_n, _MAX_TOKENS)

    mi_scores = compute_mutual_information(token_sets, event_labels, event_type)

    if not mi_scores:
        return SelectedTokenSet(event_type=event_type, tokens=(), dropped_redundant=())

    selected: list[TokenScore] = []
    dropped: list[str] = []

    for candidate in mi_scores:
        if len(selected) >= effective_top_n:
            break

        redundant = False
        for kept in selected:
            sim = jaccard_similarity(token_sets, candidate.token, kept.token)
            if sim > jaccard_threshold:
                redundant = True
                break

        if redundant:
            dropped.append(candidate.token)
        else:
            selected.append(candidate)

    result = SelectedTokenSet(
        event_type=event_type,
        tokens=tuple(selected),
        dropped_redundant=tuple(dropped),
    )

    # SPEC §5.4 step 5: log selected token set and MI scores.
    token_summary = ", ".join(
        f"{s.token}={s.mi_score:.4f}" for s in selected
    )
    logger.info(
        "Token selection for %s: selected %d tokens [%s]; dropped %d redundant",
        event_type,
        len(selected),
        token_summary,
        len(dropped),
    )

    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _cell_index(present: bool, event: bool) -> int:
    """Map (token_present, event_true) to contingency table index [a,b,c,d]."""
    if present and event:
        return 0  # a
    if present and not event:
        return 1  # b
    if not present and event:
        return 2  # c
    return 3  # d


def _mi_from_contingency(cells: list[int], n: int) -> float:
    """Compute mutual information from a 2×2 contingency table.

    Uses the convention 0 * log(0) = 0 to handle zero-count cells.
    """
    a, b, c, d = cells
    mi = 0.0
    for count, row_total, col_total in [
        (a, a + b, a + c),
        (b, a + b, b + d),
        (c, c + d, a + c),
        (d, c + d, b + d),
    ]:
        if count == 0 or row_total == 0 or col_total == 0:
            continue
        p_joint = count / n
        p_row = row_total / n
        p_col = col_total / n
        mi += p_joint * math.log(p_joint / (p_row * p_col))
    return mi
