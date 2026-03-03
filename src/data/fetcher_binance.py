"""Binance BTC/USDT spot candle fetcher with normalize + verified-storage path."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Callable, Protocol
from urllib.parse import urlencode, urlparse
from urllib.request import urlopen

from src.data.fetcher_base import CandleRecord, require_utc


BINANCE_BASE_URL = "https://api.binance.com"
INTERVAL_TO_BINANCE_INTERVAL: dict[str, str] = {
    "1m": "1m",
    "5m": "5m",
    "1h": "1h",
    "4h": "4h",
    "1d": "1d",
}


class BinanceHTTPClient(Protocol):
    def get_json(self, path: str, params: dict[str, str]) -> list[list[Any]]: ...


class UrllibBinanceHTTPClient:
    def __init__(self, *, base_url: str = BINANCE_BASE_URL) -> None:
        self._base_url = base_url.rstrip("/")

    def get_json(self, path: str, params: dict[str, str]) -> list[list[Any]]:
        query = urlencode(params)
        url = f"{self._base_url}{path}?{query}"
        parsed = urlparse(url)
        expected_netloc = urlparse(self._base_url).netloc
        if parsed.scheme != "https" or parsed.netloc != expected_netloc:
            msg = f"unexpected binance URL: {url}"
            raise ValueError(msg)
        with urlopen(url, timeout=30) as response:  # nosec B310
            payload = response.read().decode("utf-8")
        data = json.loads(payload)
        if not isinstance(data, list):
            msg = "binance response must be a JSON array"
            raise ValueError(msg)
        return data


@dataclass(frozen=True)
class BinanceCandle(CandleRecord):
    pass


class CursorLike(Protocol):
    def executemany(self, sql: str, rows: list[tuple[Any, ...]]) -> None: ...


class ConnectionLike(Protocol):
    def cursor(self) -> CursorLike: ...

    def commit(self) -> None: ...


class BinanceBTCUSDTFetcher:
    def __init__(
        self,
        *,
        http_client: BinanceHTTPClient | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self.http_client = http_client or UrllibBinanceHTTPClient()
        self.now_provider = now_provider or (lambda: datetime.now(tz=UTC))

    def fetch_historical(self, *, interval: str, start: datetime, end: datetime) -> list[BinanceCandle]:
        params = {
            "symbol": "BTCUSDT",
            "interval": _to_binance_interval(interval),
            "startTime": str(_to_epoch_ms(start)),
            "endTime": str(_to_epoch_ms(end)),
            "limit": "1000",
        }
        data = self.http_client.get_json("/api/v3/klines", params)
        return normalize_binance_candles(data, interval=interval, now=self.now_provider())

    def fetch_recent(self, *, interval: str, count: int = 2) -> list[BinanceCandle]:
        params = {
            "symbol": "BTCUSDT",
            "interval": _to_binance_interval(interval),
            "limit": str(count),
        }
        data = self.http_client.get_json("/api/v3/klines", params)
        return normalize_binance_candles(data, interval=interval, now=self.now_provider())


def normalize_binance_candles(
    raw_candles: list[list[Any]], *, interval: str, now: datetime | None = None
) -> list[BinanceCandle]:
    current = require_utc(now or datetime.now(tz=UTC))
    now_ms = int(current.timestamp() * 1000)

    normalized: list[BinanceCandle] = []
    for raw in raw_candles:
        if len(raw) < 8:
            continue

        open_time_ms = int(raw[0])
        close_time_ms = int(raw[6])
        if close_time_ms > now_ms:
            continue

        normalized.append(
            BinanceCandle(
                time=datetime.fromtimestamp(open_time_ms / 1000, tz=UTC),
                instrument="BTC_USD",
                interval=interval,
                open=float(raw[1]),
                high=float(raw[2]),
                low=float(raw[3]),
                close=float(raw[4]),
                volume=float(raw[7]),  # quote asset volume (USDT)
                spread_avg=None,
                verified=True,
                source="binance",
            )
        )
    return normalized


def store_verified_candles(connection: ConnectionLike, candles: list[BinanceCandle]) -> int:
    if not candles:
        return 0

    rows = [
        (
            candle.time,
            candle.instrument,
            candle.interval,
            candle.open,
            candle.high,
            candle.low,
            candle.close,
            candle.volume,
            candle.spread_avg,
            candle.verified,
            candle.source,
        )
        for candle in candles
        if candle.verified
    ]
    if not rows:
        return 0

    cursor = connection.cursor()
    cursor.executemany(
        """
        INSERT INTO ohlcv (time, instrument, interval, open, high, low, close, volume, spread_avg, verified, source)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (time, instrument, interval) DO UPDATE
        SET
            open = EXCLUDED.open,
            high = EXCLUDED.high,
            low = EXCLUDED.low,
            close = EXCLUDED.close,
            volume = EXCLUDED.volume,
            spread_avg = EXCLUDED.spread_avg,
            verified = EXCLUDED.verified,
            source = EXCLUDED.source
        """,
        rows,
    )
    connection.commit()
    return len(rows)


def _to_binance_interval(interval: str) -> str:
    try:
        return INTERVAL_TO_BINANCE_INTERVAL[interval]
    except KeyError as exc:
        msg = f"unsupported interval for binance: {interval}"
        raise ValueError(msg) from exc


def _to_epoch_ms(dt: datetime) -> int:
    return int(require_utc(dt).timestamp() * 1000)
