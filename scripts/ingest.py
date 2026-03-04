#!/usr/bin/env python3
"""Fetch recent candles from Oanda and Binance and store in TimescaleDB.

Usage:
    python scripts/ingest.py              # Fetch 100 recent 1h candles per instrument
    python scripts/ingest.py --count 500  # Fetch 500 candles
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def read_env(key: str) -> str:
    """Read from .env file or environment."""
    env_path = ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith(f"{key}="):
                return line.split("=", 1)[1].strip()
    value = os.getenv(key, "")
    if not value:
        raise RuntimeError(f"{key} not set in .env or environment")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest candle data into Newton DB")
    parser.add_argument("--count", type=int, default=100, help="Number of candles to fetch (default: 100)")
    parser.add_argument("--interval", default="1h", help="Candle interval (default: 1h)")
    args = parser.parse_args()

    import psycopg

    db_url = read_env("DATABASE_URL")

    # --- Binance (no API key needed for public klines) ---
    print(f"Fetching {args.count} BTC_USD {args.interval} candles from Binance...")
    from src.data.fetcher_binance import BinanceBTCUSDTFetcher, store_verified_candles as store_binance
    binance_fetcher = BinanceBTCUSDTFetcher()
    btc_candles = binance_fetcher.fetch_recent(interval=args.interval, count=args.count)
    print(f"  Fetched {len(btc_candles)} candles")

    with psycopg.connect(db_url, autocommit=False) as conn:
        stored = store_binance(conn, btc_candles)
        print(f"  Stored {stored} BTC_USD candles")

    # --- Oanda (requires API key + account ID) ---
    oanda_key = os.getenv("OANDA_API_KEY", "")
    oanda_account = os.getenv("OANDA_ACCOUNT_ID", "")
    if not oanda_key or not oanda_account:
        # Try .env
        env_path = ROOT / ".env"
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("OANDA_API_KEY="):
                    oanda_key = line.split("=", 1)[1].strip()
                elif line.startswith("OANDA_ACCOUNT_ID="):
                    oanda_account = line.split("=", 1)[1].strip()

    if oanda_key and oanda_account:
        print(f"Fetching {args.count} EUR_USD {args.interval} candles from Oanda...")
        from src.data.fetcher_oanda import OandaEURUSDFetcher, store_verified_candles as store_oanda
        oanda_fetcher = OandaEURUSDFetcher(account_id=oanda_account, api_key=oanda_key)
        eur_candles = oanda_fetcher.fetch_recent(interval=args.interval, count=args.count)
        print(f"  Fetched {len(eur_candles)} candles")

        with psycopg.connect(db_url, autocommit=False) as conn:
            stored = store_oanda(conn, eur_candles)
            print(f"  Stored {stored} EUR_USD candles")
    else:
        print("Skipping Oanda — OANDA_API_KEY or OANDA_ACCOUNT_ID not set")

    # --- Summary ---
    with psycopg.connect(db_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT instrument, count(*) FROM ohlcv GROUP BY instrument ORDER BY instrument")
            rows = cur.fetchall()
            print("\nOHLCV row counts:")
            for instrument, count in rows:
                print(f"  {instrument}: {count}")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
