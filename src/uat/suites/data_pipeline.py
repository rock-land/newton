"""Data Pipeline UAT suite — candle normalization, verification, indicators."""

from __future__ import annotations

from src.uat.helpers import make_candles
from src.uat.runner import UATTest

SUITE_ID = "data_pipeline"
SUITE_NAME = "Data Pipeline"


def test_dp_01() -> str:
    """Candle normalization produces valid CandleRecord fields."""
    from datetime import UTC, datetime
    from typing import Any

    from src.data.fetcher_binance import normalize_binance_candles

    # Synthetic raw Binance kline (12 fields per SPEC)
    close_time_ms = 1704070799999  # 2024-01-01 ~01:00 UTC
    raw: list[list[Any]] = [
        [
            1704067200000,  # open time
            "42000.00",     # open
            "42500.00",     # high
            "41800.00",     # low
            "42200.00",     # close
            "100.5",        # volume
            close_time_ms,  # close time
            "4230000.00",   # quote asset volume
            500,            # number of trades
            "50.2",         # taker buy base
            "2115000.00",   # taker buy quote
            "0",            # ignore
        ],
    ]
    now = datetime(2025, 1, 1, tzinfo=UTC)
    candles = normalize_binance_candles(raw, interval="1h", now=now)
    assert len(candles) == 1, f"Expected 1 candle, got {len(candles)}"
    c = candles[0]
    assert c.instrument == "BTC_USD"
    assert c.interval == "1h"
    assert c.open == 42000.0
    assert c.high == 42500.0
    assert c.low == 41800.0
    assert c.close == 42200.0
    assert c.volume > 0
    assert c.source == "binance"
    return f"1 candle normalized: OHLCV={c.open}/{c.high}/{c.low}/{c.close}/{c.volume}"


def test_dp_02() -> str:
    """Verifier detects OHLC integrity violations (high < low)."""
    from datetime import UTC, datetime

    from src.data.fetcher_base import CandleRecord
    from src.data.verifier import verify_candles

    bad_candle = CandleRecord(
        time=datetime(2025, 1, 1, tzinfo=UTC),
        instrument="EUR_USD",
        interval="1h",
        open=1.1000,
        high=1.0900,  # high < low — violation
        low=1.1100,
        close=1.1050,
        volume=1000.0,
        spread_avg=0.00015,
        verified=True,
        source="synthetic",
    )
    result = verify_candles([bad_candle], instrument="EUR_USD", interval="1h")
    integrity_issues = [i for i in result.issues if i.issue_type == "ohlc_integrity"]
    assert len(integrity_issues) > 0, "Should detect OHLC integrity violation"
    assert len(result.suspect) == 1, "Bad candle should be in suspect list"
    return f"Detected {len(integrity_issues)} OHLC integrity issue(s), {len(result.suspect)} suspect candle(s)"


def test_dp_03() -> str:
    """Verifier deduplicates overlapping timestamps."""
    from datetime import UTC, datetime

    from src.data.fetcher_base import CandleRecord
    from src.data.verifier import verify_candles

    t = datetime(2025, 1, 1, tzinfo=UTC)
    candle = CandleRecord(
        time=t,
        instrument="EUR_USD",
        interval="1h",
        open=1.1,
        high=1.11,
        low=1.09,
        close=1.105,
        volume=1000.0,
        spread_avg=0.00015,
        verified=True,
        source="synthetic",
    )
    result = verify_candles([candle, candle], instrument="EUR_USD", interval="1h")
    assert len(result.deduplicated) == 1, f"Expected 1 after dedup, got {len(result.deduplicated)}"
    dup_issues = [i for i in result.issues if i.issue_type == "duplicate_candles"]
    assert len(dup_issues) == 1, "Should report duplicate candle issue"
    return f"Input: 2 candles, deduplicated: {len(result.deduplicated)}"


def test_dp_04() -> str:
    """Indicator computation (RSI, MACD, BB) on synthetic OHLCV."""
    from src.data.indicators import TechnicalIndicatorProvider

    candles = make_candles(100, instrument="EUR_USD")
    provider = TechnicalIndicatorProvider()
    features = provider.get_features(
        instrument="EUR_USD",
        interval="1h",
        candles=candles,
        lookback=100,
    )
    assert len(features) > 0, "Should produce features for some timestamps"
    # Check a later timestamp (early ones lack enough history for RSI/MACD)
    sample = list(features.values())[-1]
    feature_keys = set(sample.keys())
    has_rsi = any("rsi" in k.lower() for k in feature_keys)
    assert has_rsi, f"Should have RSI indicator, got keys: {feature_keys}"
    return f"Computed features for {len(features)} timestamps with {len(feature_keys)} indicators"


TESTS = [
    UATTest(id="DP-01", name="Candle normalization produces valid CandleRecord fields",
            suite=SUITE_ID, fn=test_dp_01),
    UATTest(id="DP-02", name="Verifier detects OHLC integrity violations",
            suite=SUITE_ID, fn=test_dp_02),
    UATTest(id="DP-03", name="Verifier deduplicates overlapping timestamps",
            suite=SUITE_ID, fn=test_dp_03),
    UATTest(id="DP-04", name="Indicator computation on synthetic OHLCV",
            suite=SUITE_ID, fn=test_dp_04),
]
