#!/usr/bin/env python3
"""Benchmark Stage-1 feature store query latency for N-PMV-2."""

from __future__ import annotations

import argparse
import json
import os
import statistics
import time
from dataclasses import asdict, dataclass

import psycopg

from src.data.feature_store import build_feature_records, store_feature_records
from src.data.fetcher_base import CandleRecord
from src.data.indicators import TechnicalIndicatorProvider


@dataclass
class InstrumentMetrics:
    instrument: str
    interval: str
    runs: int
    rows_min: int
    rows_max: int
    p50_ms: float
    p95_ms: float
    max_ms: float
    lookback_start: str


def ensure_features(conn: psycopg.Connection, instrument: str, interval: str, namespace: str) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM features WHERE instrument=%s AND interval=%s AND namespace=%s",
            (instrument, interval, namespace),
        )
        existing = int(cur.fetchone()[0])
        if existing >= 300:
            return 0

        cur.execute(
            """
            SELECT time, instrument, interval, open, high, low, close, volume, spread_avg, verified, source
            FROM ohlcv
            WHERE instrument=%s AND interval=%s
            ORDER BY time ASC
            """,
            (instrument, interval),
        )
        rows = cur.fetchall()

    provider = TechnicalIndicatorProvider()
    candles = [CandleRecord(*row) for row in rows]
    by_time = provider.get_features(
        instrument=instrument,
        interval=interval,
        candles=candles,
        lookback=len(candles),
    )
    feature_rows = build_feature_records(
        instrument=instrument,
        interval=interval,
        namespace=namespace,
        values_by_time=by_time,
    )
    return store_feature_records(conn, feature_rows)


def benchmark_instrument(
    conn: psycopg.Connection,
    *,
    instrument: str,
    interval: str,
    namespace: str,
    lookback: int,
    indicators: list[str],
    runs: int,
    warmup: int,
) -> InstrumentMetrics:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT time
            FROM features
            WHERE instrument=%s AND interval=%s AND namespace=%s AND feature_key = ANY(%s)
            GROUP BY time
            ORDER BY time DESC
            OFFSET %s LIMIT 1
            """,
            (instrument, interval, namespace, indicators, lookback - 1),
        )
        row = cur.fetchone()
        if row is None:
            raise RuntimeError(f"insufficient feature rows for {instrument} ({interval})")
        lookback_start = row[0]

        sql = """
            SELECT time, instrument, interval, namespace, feature_key, value
            FROM features
            WHERE instrument = %s
              AND interval = %s
              AND namespace = %s
              AND time >= %s
              AND feature_key = ANY(%s)
            ORDER BY time ASC, namespace ASC, feature_key ASC
            LIMIT %s
        """
        params = (
            instrument,
            interval,
            namespace,
            lookback_start,
            indicators,
            lookback * len(indicators),
        )

        for _ in range(warmup):
            cur.execute(sql, params)
            cur.fetchall()

        latencies_ms: list[float] = []
        row_counts: list[int] = []
        for _ in range(runs):
            start = time.perf_counter_ns()
            cur.execute(sql, params)
            rows = cur.fetchall()
            end = time.perf_counter_ns()
            latencies_ms.append((end - start) / 1_000_000)
            row_counts.append(len(rows))

    sorted_lat = sorted(latencies_ms)
    p95_idx = max(0, int(0.95 * len(sorted_lat)) - 1)
    return InstrumentMetrics(
        instrument=instrument,
        interval=interval,
        runs=runs,
        rows_min=min(row_counts),
        rows_max=max(row_counts),
        p50_ms=round(statistics.median(latencies_ms), 3),
        p95_ms=round(sorted_lat[p95_idx], 3),
        max_ms=round(max(latencies_ms), 3),
        lookback_start=lookback_start.isoformat(),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--interval", default="1h")
    parser.add_argument("--lookback", type=int, default=60)
    parser.add_argument("--runs", type=int, default=50)
    parser.add_argument("--warmup", type=int, default=5)
    args = parser.parse_args()

    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL is not configured")

    namespace = "technical"
    instruments = ["EUR_USD", "BTC_USD"]
    indicators = [
        "rsi:period=14",
        "macd:fast=12,slow=26,signal=9:line",
        "bb:period=20,std=2.0:middle",
        "obv:",
        "atr:period=14",
    ]

    populated: dict[str, int] = {}
    with psycopg.connect(db_url) as conn:
        for instrument in instruments:
            populated[instrument] = ensure_features(conn, instrument, args.interval, namespace)

    metrics: list[InstrumentMetrics] = []
    with psycopg.connect(db_url, autocommit=True) as conn:
        for instrument in instruments:
            metrics.append(
                benchmark_instrument(
                    conn,
                    instrument=instrument,
                    interval=args.interval,
                    namespace=namespace,
                    lookback=args.lookback,
                    indicators=indicators,
                    runs=args.runs,
                    warmup=args.warmup,
                )
            )

    payload = {
        "interval": args.interval,
        "lookback": args.lookback,
        "indicators": indicators,
        "runs_per_instrument": args.runs,
        "warmup_runs": args.warmup,
        "populated_features_upserted": populated,
        "results": [asdict(item) for item in metrics],
    }
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
