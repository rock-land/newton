#!/usr/bin/env python3
"""N-PMV-3: Verify Newton indicator outputs vs TA-Lib reference."""

from __future__ import annotations

import os
import random
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import psycopg
import talib

from src.data.fetcher_base import CandleRecord
from src.data.indicators import TechnicalIndicatorConfig, TechnicalIndicatorProvider

ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / "docs/dev/reviews/npmv-3-indicator-talib-verification.md"
TASKS_PATH = ROOT / "TASKS.md"


@dataclass
class MetricStats:
    name: str
    count: int
    max_pct_dev: float
    mean_pct_dev: float


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def _pct_dev(newton: float, ref: float) -> float:
    denom = max(abs(ref), 1e-12)
    return abs(newton - ref) / denom * 100.0


def _fetch_verified_candles(conn: psycopg.Connection, instrument: str, interval: str) -> list[CandleRecord]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT time, instrument, interval, open, high, low, close, volume, spread_avg, verified, source
            FROM ohlcv
            WHERE instrument = %s
              AND interval = %s
              AND verified = TRUE
            ORDER BY time ASC
            """,
            (instrument, interval),
        )
        rows = cur.fetchall()
    return [CandleRecord(*row) for row in rows]


def _compute_talib(candles: list[CandleRecord], cfg: TechnicalIndicatorConfig) -> dict[str, np.ndarray]:
    closes = np.array([c.close for c in candles], dtype=float)
    highs = np.array([c.high for c in candles], dtype=float)
    lows = np.array([c.low for c in candles], dtype=float)
    volumes = np.array([c.volume for c in candles], dtype=float)

    rsi = talib.RSI(closes, timeperiod=cfg.rsi_period)
    macd, macd_signal, macd_hist = talib.MACD(
        closes,
        fastperiod=cfg.macd_fast,
        slowperiod=cfg.macd_slow,
        signalperiod=cfg.macd_signal,
    )
    bb_upper, bb_middle, bb_lower = talib.BBANDS(
        closes,
        timeperiod=cfg.bb_period,
        nbdevup=cfg.bb_std,
        nbdevdn=cfg.bb_std,
        matype=0,
    )
    obv = talib.OBV(closes, volumes)
    atr = talib.ATR(highs, lows, closes, timeperiod=cfg.atr_period)

    return {
        "rsi": rsi,
        "macd_line": macd,
        "macd_signal": macd_signal,
        "macd_hist": macd_hist,
        "bb_upper": bb_upper,
        "bb_middle": bb_middle,
        "bb_lower": bb_lower,
        "obv": obv,
        "atr": atr,
    }


def _sample_indices(n: int, *, sample_size: int, warmup: int, rng: random.Random) -> list[int]:
    eligible = list(range(warmup, n))
    if len(eligible) < sample_size:
        msg = f"not enough eligible candles ({len(eligible)}) for sample size {sample_size}"
        raise RuntimeError(msg)
    return sorted(rng.sample(eligible, sample_size))


def _safe_float(value: float | None) -> float:
    if value is None:
        raise ValueError("unexpected None value")
    return float(value)


def run() -> tuple[str, list[MetricStats], dict[str, list[str]]]:
    _load_env_file(ROOT / ".env")
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL missing")

    cfg = TechnicalIndicatorConfig()
    provider = TechnicalIndicatorProvider(cfg)

    instruments = ["EUR_USD", "BTC_USD"]
    interval = "1h"
    sample_size = 100
    warmup = max(cfg.rsi_period + 1, cfg.macd_slow + cfg.macd_signal + 5, cfg.bb_period + 1, cfg.atr_period + 1)
    rng = random.Random(20260218)

    metric_values: dict[str, list[float]] = {
        "RSI": [],
        "MACD Line": [],
        "MACD Signal": [],
        "MACD Histogram": [],
        "Bollinger Upper": [],
        "Bollinger Middle": [],
        "Bollinger Lower": [],
        "OBV": [],
        "ATR": [],
    }

    sample_times: dict[str, list[str]] = {}

    with psycopg.connect(db_url) as conn:
        for instrument in instruments:
            candles = _fetch_verified_candles(conn, instrument, interval)
            if len(candles) < warmup + sample_size:
                raise RuntimeError(
                    f"insufficient candles for {instrument} ({len(candles)}); need >= {warmup + sample_size}"
                )

            features = provider.get_features(
                instrument=instrument,
                interval=interval,
                candles=candles,
                lookback=len(candles),
            )
            talib_ref = _compute_talib(candles, cfg)

            indices = _sample_indices(len(candles), sample_size=sample_size, warmup=warmup, rng=rng)
            sample_times[instrument] = [candles[i].time.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ") for i in indices]

            for idx in indices:
                ts = candles[idx].time
                f = features.get(ts)
                if f is None:
                    raise RuntimeError(f"missing Newton feature row at {instrument} {ts.isoformat()}")

                rsi_key = f"rsi:period={cfg.rsi_period}"
                macd_prefix = f"macd:fast={cfg.macd_fast},slow={cfg.macd_slow},signal={cfg.macd_signal}"
                bb_prefix = f"bb:period={cfg.bb_period},std={cfg.bb_std}"
                atr_key = f"atr:period={cfg.atr_period}"

                pairs = [
                    ("RSI", _safe_float(f.get(rsi_key)), float(talib_ref["rsi"][idx])),
                    ("MACD Line", _safe_float(f.get(f"{macd_prefix}:line")), float(talib_ref["macd_line"][idx])),
                    ("MACD Signal", _safe_float(f.get(f"{macd_prefix}:signal")), float(talib_ref["macd_signal"][idx])),
                    ("MACD Histogram", _safe_float(f.get(f"{macd_prefix}:histogram")), float(talib_ref["macd_hist"][idx])),
                    ("Bollinger Upper", _safe_float(f.get(f"{bb_prefix}:upper")), float(talib_ref["bb_upper"][idx])),
                    ("Bollinger Middle", _safe_float(f.get(f"{bb_prefix}:middle")), float(talib_ref["bb_middle"][idx])),
                    ("Bollinger Lower", _safe_float(f.get(f"{bb_prefix}:lower")), float(talib_ref["bb_lower"][idx])),
                    ("OBV", _safe_float(f.get("obv:")), float(talib_ref["obv"][idx])),
                    ("ATR", _safe_float(f.get(atr_key)), float(talib_ref["atr"][idx])),
                ]

                for name, newton_value, ref_value in pairs:
                    if np.isnan(ref_value):
                        raise RuntimeError(f"TA-Lib reference is NaN for {name} at {instrument} index={idx}")
                    metric_values[name].append(_pct_dev(newton_value, ref_value))

    stats: list[MetricStats] = []
    for name, values in metric_values.items():
        arr = np.array(values, dtype=float)
        stats.append(
            MetricStats(
                name=name,
                count=int(arr.size),
                max_pct_dev=float(arr.max(initial=0.0)),
                mean_pct_dev=float(arr.mean() if arr.size else 0.0),
            )
        )

    threshold = 0.01
    verdict = "PASS" if all(s.max_pct_dev < threshold for s in stats) else "FAIL"

    lines: list[str] = []
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M")
    lines.extend(
        [
            "# N-PMV-3 Indicator TA-Lib Verification (Stage 1)",
            "",
            f"Date (UTC): {now}",
            "Branch: `stage/2-event-detection`",
            "Task: `N-PMV-3`",
            "",
            "## Scope",
            "- Verify Stage 1 indicator outputs against TA-Lib reference implementation.",
            "- Indicators: RSI, MACD (line/signal/histogram), Bollinger Bands (upper/middle/lower), OBV, ATR.",
            "- Instruments: `EUR_USD`, `BTC_USD`.",
            "- Interval: `1h`.",
            "- Acceptance threshold: **max deviation < 0.01%**.",
            "",
            "## Stage 1 Indicator Computation Paths",
            "- Source file: `src/data/indicators.py`",
            "- Provider: `TechnicalIndicatorProvider` (`technical_indicator_provider_v1`)",
            "- Feature keys:",
            f"  - `rsi:period={cfg.rsi_period}`",
            f"  - `macd:fast={cfg.macd_fast},slow={cfg.macd_slow},signal={cfg.macd_signal}:line|signal|histogram`",
            f"  - `bb:period={cfg.bb_period},std={cfg.bb_std}:upper|middle|lower`",
            "  - `obv:`",
            f"  - `atr:period={cfg.atr_period}`",
            "",
            "## Methodology",
            "1. Load verified OHLCV candles from `ohlcv` where `verified = TRUE` for each instrument.",
            "2. Build Newton outputs via `TechnicalIndicatorProvider.get_features(...)` with full lookback.",
            "3. Build TA-Lib references using:",
            "   - `talib.RSI(period=14)`",
            "   - `talib.MACD(fast=12, slow=26, signal=9)`",
            "   - `talib.BBANDS(period=20, nbdevup=2, nbdevdn=2, matype=SMA)`",
            "   - `talib.OBV`",
            "   - `talib.ATR(period=14)`",
            "4. Randomly sample 100 timestamps per instrument (seed=20260218) from eligible candles after warmup.",
            f"   - Warmup index floor: `{warmup}` (covers slowest indicator history requirements).",
            "5. Compute percentage deviation per field:",
            "",
            "```text",
            "pct_deviation = abs(newton - talib) / max(abs(talib), 1e-12) * 100",
            "```",
            "",
            "6. Aggregate per field: max and mean deviation across 200 points total (100 x 2 instruments).",
            "",
            "## Sample Strategy",
            "- Dataset: verified DB candles (`ohlcv`) for `1h` interval.",
            "- Instruments sampled independently, each with 100 unique random indices.",
            "- Random seed fixed for reproducibility: `20260218`.",
            "",
            "## Deviation Results",
            "",
            "| Indicator field | Samples | Max deviation (%) | Mean deviation (%) |",
            "|---|---:|---:|---:|",
        ]
    )

    for s in stats:
        lines.append(f"| {s.name} | {s.count} | {s.max_pct_dev:.12f} | {s.mean_pct_dev:.12f} |")

    lines.extend(
        [
            "",
            "## Verdict",
            f"**{verdict}** — threshold is max deviation < `0.01%` for every indicator field.",
            "",
            "## Sampled Timestamp Coverage (first 5 shown)",
        ]
    )

    for instrument, ts_list in sample_times.items():
        preview = ", ".join(ts_list[:5])
        lines.append(f"- `{instrument}`: {len(ts_list)} samples (first 5: {preview})")

    REPORT_PATH.write_text("\n".join(lines) + "\n")
    return verdict, stats, sample_times


if __name__ == "__main__":
    verdict, stats, _ = run()
    print(f"VERDICT={verdict}")
    for s in stats:
        print(f"{s.name}\tmax={s.max_pct_dev:.12f}\tmean={s.mean_pct_dev:.12f}\tn={s.count}")
