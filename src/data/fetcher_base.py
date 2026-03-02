"""Shared candle models and fetcher helpers for Stage 1 data ingestion."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime


INTERVAL_TO_OANDA_GRANULARITY: dict[str, str] = {
    "1m": "M1",
    "5m": "M5",
    "1h": "H1",
    "4h": "H4",
    "1d": "D",
}


@dataclass(frozen=True)
class CandleRecord:
    time: datetime
    instrument: str
    interval: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    spread_avg: float | None
    verified: bool
    source: str


def require_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        msg = "datetime must be timezone-aware (UTC required)"
        raise ValueError(msg)
    return dt.astimezone(UTC)


def format_utc_z(dt: datetime) -> str:
    return require_utc(dt).strftime("%Y-%m-%dT%H:%M:%SZ")
