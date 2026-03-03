"""Tokenizer: converts indicator feature values into discrete binary tokens (SPEC §5.3).

Token format: {INSTRUMENT}_{PREFIX}_{PARAM}_{DATAPOINT}_{TYPE}_{VALUE}

Classification rules are loaded from per-instrument JSON config files
(``config/classifications/{INSTRUMENT}_classifications.json``).  Each rule
defines one token and the condition under which it is active.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime

# Feature key used internally to expose the candle close price to rules.
CLOSE_FEATURE_KEY = "_close"

# Conditions that require ``previous_features`` to evaluate.
_REQUIRES_PREVIOUS = frozenset({
    "cross_above", "cross_below",
    "cross_above_val", "cross_below_val",
    "rising", "falling",
})


@dataclass(frozen=True)
class ClassificationRule:
    """A rule mapping indicator feature values to a binary token."""

    token: str
    feature_key: str
    condition: str
    threshold: float | None = None
    reference_key: str | None = None


@dataclass(frozen=True)
class TokenSet:
    """Set of active tokens for a single candle timestamp."""

    instrument: str
    time: datetime
    tokens: frozenset[str]


def load_classifications(path: str) -> list[ClassificationRule]:
    """Load classification rules from a JSON config file.

    Raises ``FileNotFoundError`` if the file does not exist.
    """
    with open(path) as f:
        data = json.load(f)
    rules: list[ClassificationRule] = []
    for entry in data["tokens"]:
        rules.append(ClassificationRule(
            token=entry["token"],
            feature_key=entry["feature_key"],
            condition=entry["condition"],
            threshold=entry.get("threshold"),
            reference_key=entry.get("reference_key"),
        ))
    return rules


def tokenize(
    instrument: str,
    time: datetime,
    features: dict[str, float],
    rules: list[ClassificationRule],
    *,
    close: float,
    previous_features: dict[str, float] | None = None,
) -> TokenSet:
    """Apply classification rules to feature values and return active tokens.

    Args:
        instrument: Instrument ID (e.g., ``"EUR_USD"``).
        time: Timestamp for the token set.
        features: Indicator feature values (from TechnicalIndicatorProvider).
        rules: Classification rules loaded from config.
        close: Close price for the candle (exposed as ``"_close"`` for BB rules).
        previous_features: Previous candle's feature values.  Required for
            crossover, rising, and falling rules.  If *None*, those rules
            are silently skipped.

    Returns:
        ``TokenSet`` with all active tokens as a ``frozenset``.
    """
    all_values = {**features, CLOSE_FEATURE_KEY: close}
    active: set[str] = set()
    for rule in rules:
        if _evaluate_rule(rule, all_values, previous_features):
            active.add(rule.token)
    return TokenSet(instrument=instrument, time=time, tokens=frozenset(active))


def _evaluate_rule(
    rule: ClassificationRule,
    values: dict[str, float],
    previous: dict[str, float] | None,
) -> bool:
    """Evaluate a single classification rule against feature values."""
    condition = rule.condition

    # Bail out early if the primary feature is missing.
    if rule.feature_key not in values:
        return False
    current_val = values[rule.feature_key]

    # --- Simple threshold conditions (no previous needed) ---

    if condition == "below":
        return rule.threshold is not None and current_val < rule.threshold

    if condition == "above":
        return rule.threshold is not None and current_val > rule.threshold

    if condition == "above_ref":
        return (
            rule.reference_key is not None
            and rule.reference_key in values
            and current_val > values[rule.reference_key]
        )

    if condition == "below_ref":
        return (
            rule.reference_key is not None
            and rule.reference_key in values
            and current_val < values[rule.reference_key]
        )

    # --- Conditions requiring previous features ---

    if previous is None:
        return False

    if condition == "cross_above":
        if rule.reference_key is None or rule.reference_key not in values:
            return False
        if rule.feature_key not in previous or rule.reference_key not in previous:
            return False
        return (
            current_val > values[rule.reference_key]
            and previous[rule.feature_key] <= previous[rule.reference_key]
        )

    if condition == "cross_below":
        if rule.reference_key is None or rule.reference_key not in values:
            return False
        if rule.feature_key not in previous or rule.reference_key not in previous:
            return False
        return (
            current_val < values[rule.reference_key]
            and previous[rule.feature_key] >= previous[rule.reference_key]
        )

    if condition == "cross_above_val":
        if rule.threshold is None or rule.feature_key not in previous:
            return False
        return current_val > rule.threshold and previous[rule.feature_key] <= rule.threshold

    if condition == "cross_below_val":
        if rule.threshold is None or rule.feature_key not in previous:
            return False
        return current_val < rule.threshold and previous[rule.feature_key] >= rule.threshold

    if condition == "rising":
        if rule.feature_key not in previous:
            return False
        return current_val > previous[rule.feature_key]

    if condition == "falling":
        if rule.feature_key not in previous:
            return False
        return current_val < previous[rule.feature_key]

    return False
