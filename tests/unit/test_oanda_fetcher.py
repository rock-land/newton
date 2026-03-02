from __future__ import annotations

from datetime import UTC, datetime

from src.data.fetcher_oanda import (
    OandaCandle,
    OandaEURUSDFetcher,
    OandaHTTPClient,
    store_verified_candles,
)


class FakeHTTPClient(OandaHTTPClient):
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.last_path = ""
        self.last_params: dict[str, str] = {}

    def get_json(self, path: str, params: dict[str, str]) -> dict:
        self.last_path = path
        self.last_params = params
        return self.payload


class FakeCursor:
    def __init__(self) -> None:
        self.executed: list[tuple[str, list[tuple[object, ...]]]] = []

    def executemany(self, sql: str, rows: list[tuple[object, ...]]) -> None:
        self.executed.append((sql, rows))


class FakeConnection:
    def __init__(self) -> None:
        self.cursor_obj = FakeCursor()
        self.committed = False

    def cursor(self) -> FakeCursor:
        return self.cursor_obj

    def commit(self) -> None:
        self.committed = True


def test_fetch_recent_normalizes_only_complete_candles() -> None:
    client = FakeHTTPClient(
        {
            "candles": [
                {
                    "time": "2026-02-17T07:00:00.000000000Z",
                    "complete": True,
                    "volume": 123,
                    "mid": {"o": "1.08000", "h": "1.08100", "l": "1.07900", "c": "1.08050"},
                },
                {
                    "time": "2026-02-17T07:01:00.000000000Z",
                    "complete": False,
                    "volume": 10,
                    "mid": {"o": "1.08050", "h": "1.08070", "l": "1.08010", "c": "1.08030"},
                },
            ]
        }
    )
    fetcher = OandaEURUSDFetcher(account_id="acct", api_key="key", http_client=client)

    candles = fetcher.fetch_recent(interval="1m", count=2)

    assert len(candles) == 1
    candle = candles[0]
    assert candle.instrument == "EUR_USD"
    assert candle.interval == "1m"
    assert candle.source == "oanda"
    assert candle.verified is True
    assert candle.time == datetime(2026, 2, 17, 7, 0, tzinfo=UTC)
    assert client.last_path == "/v3/instruments/EUR_USD/candles"
    assert client.last_params["count"] == "2"


def test_store_verified_candles_upserts_ohlcv_rows() -> None:
    conn = FakeConnection()
    candles = [
        OandaCandle(
            time=datetime(2026, 2, 17, 7, 0, tzinfo=UTC),
            instrument="EUR_USD",
            interval="1m",
            open=1.08,
            high=1.081,
            low=1.079,
            close=1.0805,
            volume=123.0,
            spread_avg=None,
            verified=True,
            source="oanda",
        )
    ]

    inserted = store_verified_candles(conn, candles)

    assert inserted == 1
    assert conn.committed is True
    sql, rows = conn.cursor_obj.executed[0]
    assert "INSERT INTO ohlcv" in sql
    assert "ON CONFLICT (time, instrument, interval) DO UPDATE" in sql
    assert rows[0][-2] is True
    assert rows[0][-1] == "oanda"


def test_fetch_historical_uses_oanda_time_range_params() -> None:
    client = FakeHTTPClient({"candles": []})
    fetcher = OandaEURUSDFetcher(account_id="acct", api_key="key", http_client=client)

    fetcher.fetch_historical(
        interval="1h",
        start=datetime(2026, 2, 1, 0, 0, tzinfo=UTC),
        end=datetime(2026, 2, 2, 0, 0, tzinfo=UTC),
    )

    assert client.last_params["from"] == "2026-02-01T00:00:00Z"
    assert client.last_params["to"] == "2026-02-02T00:00:00Z"
    assert client.last_params["granularity"] == "H1"
