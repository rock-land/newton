"""Event Detection UAT suite — event labeling, tokenization, token selection."""

from __future__ import annotations

from src.uat.helpers import make_trending_candles
from src.uat.runner import UATTest

SUITE_ID = "event_detection"
SUITE_NAME = "Event Detection"


def test_ed_01() -> str:
    """Event labeling produces correct binary labels from price moves."""
    from src.analysis.events import label_events

    # Clear upward trend: 0.5% per candle, so >1% after 3 candles
    candles = make_trending_candles(
        30, instrument="EUR_USD", base_price=100.0, pct_per_candle=0.005,
    )
    labels = label_events(candles, ["EURUSD_UP_1PCT_24H"])
    assert len(labels) > 0, "Should produce labels"
    true_labels = [la for la in labels if la.label]
    assert len(true_labels) > 0, "Should have positive labels with upward trend"
    assert all(la.event_type == "EURUSD_UP_1PCT_24H" for la in labels)
    return f"{len(true_labels)}/{len(labels)} positive labels with upward trend"


def test_ed_02() -> str:
    """Event labeling handles flat prices (no events triggered)."""
    from datetime import UTC, datetime, timedelta

    from src.analysis.events import label_events
    from src.data.fetcher_base import CandleRecord

    t = datetime(2025, 1, 1, tzinfo=UTC)
    flat_candles = [
        CandleRecord(
            time=t + timedelta(hours=i),
            instrument="EUR_USD",
            interval="1h",
            open=100.0, high=100.01, low=99.99, close=100.0,
            volume=1000.0, spread_avg=0.00015, verified=True, source="synthetic",
        )
        for i in range(30)
    ]
    labels = label_events(flat_candles, ["EURUSD_UP_1PCT_24H"])
    true_labels = [la for la in labels if la.label]
    assert len(true_labels) == 0, f"Flat prices should have no events, got {len(true_labels)}"
    return f"0/{len(labels)} events with flat prices — correct"


def test_ed_03() -> str:
    """Tokenizer maps indicator values to classification tokens."""
    from datetime import UTC, datetime

    from src.analysis.tokenizer import ClassificationRule, tokenize

    rules = [
        ClassificationRule(
            token="EUR_USD_RSI_14_VALUE_BELOW_30",
            feature_key="rsi_14",
            condition="below",
            threshold=30.0,
        ),
        ClassificationRule(
            token="EUR_USD_RSI_14_VALUE_ABOVE_70",
            feature_key="rsi_14",
            condition="above",
            threshold=70.0,
        ),
        ClassificationRule(
            token="EUR_USD_CLOSE_ABOVE_BB_UPPER",
            feature_key="_close",
            condition="above_ref",
            reference_key="bb_upper_20",
        ),
    ]
    features = {"rsi_14": 25.0, "bb_upper_20": 1.12}
    t = datetime(2025, 1, 1, tzinfo=UTC)
    result = tokenize("EUR_USD", t, features, rules, close=1.10)
    assert "EUR_USD_RSI_14_VALUE_BELOW_30" in result.tokens, "RSI < 30 should trigger"
    assert "EUR_USD_RSI_14_VALUE_ABOVE_70" not in result.tokens, "RSI < 30 should not trigger >70"
    assert "EUR_USD_CLOSE_ABOVE_BB_UPPER" not in result.tokens, "Close < BB upper should not trigger"
    return f"Active tokens: {sorted(result.tokens)}"


def test_ed_04() -> str:
    """Token selection ranks by MI score and deduplicates."""
    from datetime import UTC, datetime, timedelta

    from src.analysis.events import EventLabel
    from src.analysis.token_selection import select_tokens
    from src.analysis.tokenizer import TokenSet

    t = datetime(2025, 1, 1, tzinfo=UTC)
    token_sets: list[TokenSet] = []
    event_labels: list[EventLabel] = []

    # Create synthetic token sets with known MI relationship
    for i in range(100):
        # Token A correlates strongly with positive events
        has_event = i % 3 == 0
        tokens: set[str] = set()
        if has_event:
            tokens.add("TOKEN_A")
        if i % 2 == 0:
            tokens.add("TOKEN_B")  # Weak/no correlation
        tokens.add("TOKEN_C")  # Always present — zero MI

        token_sets.append(TokenSet(
            instrument="EUR_USD",
            time=t + timedelta(hours=i),
            tokens=frozenset(tokens),
        ))
        event_labels.append(EventLabel(
            event_type="EURUSD_UP_1PCT_24H",
            time=t + timedelta(hours=i),
            label=has_event,
        ))

    result = select_tokens(
        token_sets, event_labels, "EURUSD_UP_1PCT_24H", top_n=10,
    )
    assert len(result.tokens) > 0, "Should select at least one token"
    # TOKEN_A should rank highest (strongest correlation with event)
    top_token = result.tokens[0].token
    assert top_token == "TOKEN_A", f"Expected TOKEN_A as top, got {top_token}"
    return f"Selected {len(result.tokens)} tokens, top: {top_token} (MI={result.tokens[0].mi_score:.4f})"


TESTS = [
    UATTest(id="ED-01", name="Event labeling produces correct binary labels",
            suite=SUITE_ID, fn=test_ed_01),
    UATTest(id="ED-02", name="Event labeling handles flat prices",
            suite=SUITE_ID, fn=test_ed_02),
    UATTest(id="ED-03", name="Tokenizer maps indicator values to tokens",
            suite=SUITE_ID, fn=test_ed_03),
    UATTest(id="ED-04", name="Token selection ranks by MI and deduplicates",
            suite=SUITE_ID, fn=test_ed_04),
]
