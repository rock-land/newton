"""Shared synthetic data generators for UAT behavioral tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from src.data.fetcher_base import CandleRecord


def make_candles(
    n: int,
    *,
    instrument: str = "EUR_USD",
    base_price: float = 1.1000,
    interval: str = "1h",
    volatility: float = 0.001,
) -> list[CandleRecord]:
    """Create n synthetic candles with deterministic price movements.

    Price pattern cycles: up, down, up-small (period 3).  This produces
    a slight upward drift that's useful for testing trend-based indicators.
    """
    candles: list[CandleRecord] = []
    t = datetime(2025, 1, 1, tzinfo=UTC)
    price = base_price

    for i in range(n):
        change = volatility * (1 if i % 3 == 0 else -1 if i % 3 == 1 else 0.5)
        op = price
        hi = price + abs(change) + volatility * 0.5
        lo = price - abs(change) - volatility * 0.5
        cl = price + change
        price = cl

        candles.append(
            CandleRecord(
                time=t + timedelta(hours=i),
                instrument=instrument,
                interval=interval,
                open=round(op, 6),
                high=round(hi, 6),
                low=round(lo, 6),
                close=round(cl, 6),
                volume=1000.0 + i * 10,
                spread_avg=0.00015 if instrument == "EUR_USD" else None,
                verified=True,
                source="synthetic",
            )
        )
    return candles


def make_trending_candles(
    n: int,
    *,
    instrument: str = "EUR_USD",
    base_price: float = 100.0,
    pct_per_candle: float = 0.005,
    interval: str = "1h",
) -> list[CandleRecord]:
    """Create n candles with a clear upward trend (pct_per_candle per bar)."""
    candles: list[CandleRecord] = []
    t = datetime(2025, 1, 1, tzinfo=UTC)

    for i in range(n):
        price = base_price * (1 + pct_per_candle * i)
        spread = price * 0.002
        candles.append(
            CandleRecord(
                time=t + timedelta(hours=i),
                instrument=instrument,
                interval=interval,
                open=round(price - spread * 0.1, 6),
                high=round(price + spread, 6),
                low=round(price - spread, 6),
                close=round(price, 6),
                volume=1000.0 + i * 10,
                spread_avg=0.00015 if instrument == "EUR_USD" else None,
                verified=True,
                source="synthetic",
            )
        )
    return candles
