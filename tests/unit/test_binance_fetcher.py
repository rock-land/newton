from __future__ import annotations

from datetime import UTC, datetime

from src.data.fetcher_binance import (
    BinanceBTCUSDTFetcher,
    BinanceCandle,
    BinanceHTTPClient,
    store_verified_candles,
)


class FakeHTTPClient(BinanceHTTPClient):
    def __init__(self, payload: list[list[object]]) -> None:
        self.payload = payload
        self.last_path = ""
        self.last_params: dict[str, str] = {}

    def get_json(self, path: str, params: dict[str, str]) -> list[list[object]]:
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


def test_fetch_recent_normalizes_only_closed_candles_and_uses_quote_volume() -> None:
    # [openTime, open, high, low, close, baseVol, closeTime, quoteVol, ...]
    client = FakeHTTPClient(
        [
            [
                1708153200000,
                "52000.00",
                "52100.00",
                "51950.00",
                "52050.00",
                "1.2",
                1708153259999,
                "62460.00",
                100,
                "0.6",
                "31230.00",
                "0",
            ],
            [
                1708153260000,
                "52050.00",
                "52120.00",
                "52000.00",
                "52090.00",
                "0.8",
                1708153319999,
                "41672.00",
                80,
                "0.4",
                "20836.00",
                "0",
            ],
        ]
    )
    fetcher = BinanceBTCUSDTFetcher(http_client=client, now_provider=lambda: datetime.fromtimestamp(1708153260, tz=UTC))

    candles = fetcher.fetch_recent(interval="1m", count=2)

    assert len(candles) == 1
    candle = candles[0]
    assert candle.instrument == "BTC_USD"
    assert candle.interval == "1m"
    assert candle.source == "binance"
    assert candle.verified is True
    assert candle.time == datetime.fromtimestamp(1708153200, tz=UTC)
    assert candle.volume == 62460.0
    assert client.last_path == "/api/v3/klines"
    assert client.last_params["symbol"] == "BTCUSDT"
    assert client.last_params["interval"] == "1m"
    assert client.last_params["limit"] == "2"


def test_store_verified_candles_upserts_ohlcv_rows() -> None:
    conn = FakeConnection()
    candles = [
        BinanceCandle(
            time=datetime(2026, 2, 17, 7, 0, tzinfo=UTC),
            instrument="BTC_USD",
            interval="1m",
            open=52000.0,
            high=52100.0,
            low=51900.0,
            close=52050.0,
            volume=62460.0,
            spread_avg=None,
            verified=True,
            source="binance",
        )
    ]

    inserted = store_verified_candles(conn, candles)

    assert inserted == 1
    assert conn.committed is True
    sql, rows = conn.cursor_obj.executed[0]
    assert "INSERT INTO ohlcv" in sql
    assert "ON CONFLICT (time, instrument, interval) DO UPDATE" in sql
    assert rows[0][-2] is True
    assert rows[0][-1] == "binance"


def test_fetch_historical_uses_binance_time_range_params() -> None:
    client = FakeHTTPClient([])
    fetcher = BinanceBTCUSDTFetcher(http_client=client)

    fetcher.fetch_historical(
        interval="1h",
        start=datetime(2026, 2, 1, 0, 0, tzinfo=UTC),
        end=datetime(2026, 2, 2, 0, 0, tzinfo=UTC),
    )

    assert client.last_path == "/api/v3/klines"
    assert client.last_params["symbol"] == "BTCUSDT"
    assert client.last_params["interval"] == "1h"
    assert client.last_params["startTime"] == str(int(datetime(2026, 2, 1, 0, 0, tzinfo=UTC).timestamp() * 1000))
    assert client.last_params["endTime"] == str(int(datetime(2026, 2, 2, 0, 0, tzinfo=UTC).timestamp() * 1000))
