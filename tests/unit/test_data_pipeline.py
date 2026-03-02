from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

from src.data.fetcher_base import CandleRecord
from src.data.pipeline import run_ingestion_cycle


class FakeFetcher:
    def __init__(self, candles: list[CandleRecord]) -> None:
        self.candles = candles
        self.last_interval = ""
        self.last_count = 0

    def fetch_recent(self, *, interval: str, count: int = 2) -> list[CandleRecord]:
        self.last_interval = interval
        self.last_count = count
        return self.candles


class FakeStore:
    def __init__(self) -> None:
        self.stored: list[CandleRecord] = []

    def __call__(self, _connection: object, candles: list[CandleRecord]) -> int:
        self.stored = candles
        return len(candles)


def make_candle(ts: str, *, high: float, close: float) -> CandleRecord:
    return CandleRecord(
        time=datetime.fromisoformat(ts).astimezone(UTC),
        instrument="EUR_USD",
        interval="1m",
        open=1.0,
        high=high,
        low=0.9,
        close=close,
        volume=100.0,
        spread_avg=None,
        verified=True,
        source="oanda",
    )


def test_ingestion_cycle_runs_verification_and_emits_logs(caplog) -> None:  # type: ignore[no-untyped-def]
    candles = [
        make_candle("2026-02-17T00:00:00+00:00", high=1.2, close=1.1),
        make_candle("2026-02-17T00:03:00+00:00", high=1.3, close=1.2),
    ]
    fetcher = FakeFetcher(candles)
    store = FakeStore()

    logger = logging.getLogger("test_data_pipeline")
    with caplog.at_level(logging.INFO):
        result = run_ingestion_cycle(
            instrument="EUR_USD",
            interval="1m",
            fetcher=fetcher,
            store_verified_candles=store,
            db_connection=object(),
            logger=logger,
            now=datetime(2026, 2, 17, 0, 3, tzinfo=UTC),
            recent_count=5,
        )

    assert fetcher.last_interval == "1m"
    assert fetcher.last_count == 5
    assert result.fetched_count == 2
    assert result.stored_count == 2

    messages = [record.message for record in caplog.records]
    summary_log = json.loads(messages[0])
    assert summary_log["event"] == "ingestion_cycle"
    assert summary_log["issue_count"] == 1
    assert any(json.loads(message)["event"] == "data_verification_alert" for message in messages[1:])
