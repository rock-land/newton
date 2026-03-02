from __future__ import annotations

from datetime import UTC, datetime

from src.data.fetcher_base import CandleRecord
from src.data.verifier import interval_to_timedelta, verify_candles


def make_candle(ts: str, *, open_: float, high: float, low: float, close: float) -> CandleRecord:
    return CandleRecord(
        time=datetime.fromisoformat(ts).astimezone(UTC),
        instrument="EUR_USD",
        interval="1m",
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=100.0,
        spread_avg=None,
        verified=True,
        source="oanda",
    )


def test_interval_to_timedelta_supported_values() -> None:
    assert interval_to_timedelta("1m").total_seconds() == 60
    assert interval_to_timedelta("5m").total_seconds() == 300
    assert interval_to_timedelta("1h").total_seconds() == 3600


def test_verifier_detects_duplicates_gaps_ohlc_and_staleness() -> None:
    candles = [
        make_candle("2026-02-17T00:00:00+00:00", open_=1.0, high=1.2, low=0.9, close=1.1),
        # duplicate timestamp, latest should be kept
        make_candle("2026-02-17T00:00:00+00:00", open_=1.0, high=1.21, low=0.9, close=1.11),
        # gap at 00:01 (missing)
        make_candle("2026-02-17T00:02:00+00:00", open_=1.1, high=1.3, low=1.0, close=1.2),
        # invalid OHLC (high below close)
        make_candle("2026-02-17T00:03:00+00:00", open_=1.2, high=1.19, low=1.1, close=1.25),
    ]

    result = verify_candles(
        candles,
        instrument="EUR_USD",
        interval="1m",
        now=datetime(2026, 2, 17, 0, 10, tzinfo=UTC),
    )

    issue_types = {issue.issue_type for issue in result.issues}
    assert issue_types == {"duplicate_candles", "gaps", "ohlc_integrity", "stale_data"}
    assert len(result.deduplicated) == 3
    assert len(result.verified) == 2
    assert len(result.suspect) == 1
    assert result.should_halt_signals is True


def test_verifier_clean_series_no_issues() -> None:
    candles = [
        make_candle("2026-02-17T00:00:00+00:00", open_=1.0, high=1.2, low=0.9, close=1.1),
        make_candle("2026-02-17T00:01:00+00:00", open_=1.1, high=1.3, low=1.0, close=1.2),
        make_candle("2026-02-17T00:02:00+00:00", open_=1.2, high=1.4, low=1.1, close=1.3),
    ]

    result = verify_candles(
        candles,
        instrument="EUR_USD",
        interval="1m",
        now=datetime(2026, 2, 17, 0, 3, tzinfo=UTC),
    )

    assert result.issues == []
    assert result.should_halt_signals is False
    assert len(result.verified) == 3
