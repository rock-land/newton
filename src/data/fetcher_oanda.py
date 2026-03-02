"""Oanda EUR/USD candle fetcher with normalize + verified-storage path."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from src.data.fetcher_base import CandleRecord, INTERVAL_TO_OANDA_GRANULARITY, format_utc_z


OANDA_BASE_URL = "https://api-fxpractice.oanda.com"


class OandaHTTPClient(Protocol):
    def get_json(self, path: str, params: dict[str, str]) -> dict[str, Any]: ...


class UrllibOandaHTTPClient:
    def __init__(self, api_key: str, *, base_url: str = OANDA_BASE_URL) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")

    def get_json(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        query = urlencode(params)
        url = f"{self._base_url}{path}?{query}"
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.netloc != "api-fxpractice.oanda.com":
            msg = f"unexpected oanda URL: {url}"
            raise ValueError(msg)
        req = Request(
            url,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Accept-Datetime-Format": "RFC3339",
            },
        )
        with urlopen(req, timeout=30) as response:  # nosec B310
            payload = response.read().decode("utf-8")
        data = json.loads(payload)
        if not isinstance(data, dict):
            msg = "oanda response must be a JSON object"
            raise ValueError(msg)
        return data


@dataclass(frozen=True)
class OandaCandle(CandleRecord):
    pass


class CursorLike(Protocol):
    def executemany(self, sql: str, rows: list[tuple[Any, ...]]) -> None: ...


class ConnectionLike(Protocol):
    def cursor(self) -> CursorLike: ...

    def commit(self) -> None: ...


class OandaEURUSDFetcher:
    def __init__(
        self,
        account_id: str,
        api_key: str,
        *,
        http_client: OandaHTTPClient | None = None,
    ) -> None:
        self.account_id = account_id
        self.api_key = api_key
        self.http_client = http_client or UrllibOandaHTTPClient(api_key)

    def fetch_historical(self, *, interval: str, start: datetime, end: datetime) -> list[OandaCandle]:
        params = {
            "price": "M",
            "granularity": _to_granularity(interval),
            "from": format_utc_z(start),
            "to": format_utc_z(end),
        }
        data = self.http_client.get_json("/v3/instruments/EUR_USD/candles", params)
        return normalize_oanda_candles(data.get("candles", []), interval=interval)

    def fetch_recent(self, *, interval: str, count: int = 2) -> list[OandaCandle]:
        params = {
            "price": "M",
            "granularity": _to_granularity(interval),
            "count": str(count),
        }
        data = self.http_client.get_json("/v3/instruments/EUR_USD/candles", params)
        return normalize_oanda_candles(data.get("candles", []), interval=interval)


def normalize_oanda_candles(raw_candles: list[dict[str, Any]], *, interval: str) -> list[OandaCandle]:
    normalized: list[OandaCandle] = []
    for raw in raw_candles:
        if raw.get("complete") is not True:
            continue

        mid = raw.get("mid")
        if not isinstance(mid, dict):
            continue

        raw_time = raw.get("time")
        if not isinstance(raw_time, str):
            continue
        time = _parse_oanda_time(raw_time)

        normalized.append(
            OandaCandle(
                time=time,
                instrument="EUR_USD",
                interval=interval,
                open=float(mid["o"]),
                high=float(mid["h"]),
                low=float(mid["l"]),
                close=float(mid["c"]),
                volume=float(raw.get("volume", 0.0)),
                spread_avg=None,
                verified=True,
                source="oanda",
            )
        )
    return normalized


def store_verified_candles(connection: ConnectionLike, candles: list[OandaCandle]) -> int:
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


def _to_granularity(interval: str) -> str:
    try:
        return INTERVAL_TO_OANDA_GRANULARITY[interval]
    except KeyError as exc:
        msg = f"unsupported interval for oanda: {interval}"
        raise ValueError(msg) from exc


def _parse_oanda_time(value: str) -> datetime:
    trimmed = value
    if value.endswith("Z"):
        trimmed = value[:-1] + "+00:00"
    dt = datetime.fromisoformat(trimmed)
    return dt.astimezone(UTC)
