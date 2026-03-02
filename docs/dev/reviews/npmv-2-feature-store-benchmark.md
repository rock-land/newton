# N-PMV-2 Feature Store Benchmark (Stage 1 PMV)

Date: 2026-02-18  
Branch: `stage/2-event-detection`

## Objective
Validate feature store query latency is **<500ms** for a **60-period lookback** across **5 indicators**.

## Stage-1 feature-store read paths identified
1. `src/data/feature_store.py`
   - `query_feature_records(...)` (time-range read path)
   - `query_feature_snapshot(...)` (point-in-time read path)
2. `src/api/v1/data.py`
   - `GET /api/v1/features/{instrument}` executes direct SQL against `features` using instrument/interval/start (+ optional indicator filters), ordered by time/feature key.

The benchmark targets the Stage-1 API-style read pattern over the same `features` table and index.

## Benchmark scenario
- Instruments: `EUR_USD`, `BTC_USD`
- Interval: `1h` (primary signal interval from `config/instruments/*.json`)
- Lookback: 60 periods
- Indicators (5):
  - `rsi:period=14`
  - `macd:fast=12,slow=26,signal=9:line`
  - `bb:period=20,std=2.0:middle`
  - `obv:`
  - `atr:period=14`
- Runs: 50 timed runs/instrument (plus 5 warmup runs)

## Methodology
1. Confirm DB connectivity and schema using existing project env (`.env`) and virtualenv.
2. Ensure feature rows exist for each instrument in `features` (technical namespace). If missing, populate from existing `ohlcv` data using `TechnicalIndicatorProvider` + `store_feature_records`.
3. For each instrument:
   - Find the timestamp corresponding to the latest 60 periods.
   - Execute repeated query:
     - filter by instrument, interval, namespace, and the 5 indicator keys
     - `time >= lookback_start`
     - order by `time, namespace, feature_key`
     - limit to `60 * 5 = 300` rows
4. Measure end-to-end SQL execution + fetch latency per run using `time.perf_counter_ns()`.
5. Compute p50/p95/max in milliseconds.

## Commands used
```bash
cd /home/bj/.openclaw/workspace/projects/newton
source .venv/bin/activate
set -a && source .env && set +a
PYTHONPATH=. python scripts/bench_feature_store.py --interval 1h --lookback 60 --runs 50 --warmup 5
```

## Environment notes
- Runtime: local Debian host
- Python: project `.venv` (3.11)
- DB: PostgreSQL/TimescaleDB via `DATABASE_URL` from local `.env`
- Data basis at run time:
  - `ohlcv` had substantial 1h history for both instruments
  - `features` technical rows were present (no additional upserts required in final benchmark run)

## Results

| Instrument | Runs | Rows/run | p50 (ms) | p95 (ms) | max (ms) | Threshold (<500ms) |
|---|---:|---:|---:|---:|---:|---|
| EUR_USD | 50 | 300 | 1.162 | 3.716 | 23.563 | PASS |
| BTC_USD | 50 | 300 | 0.966 | 1.417 | 1.576 | PASS |

## Verdict
**PASS** — Feature store query latency is well below the 500ms acceptance threshold for both `EUR_USD` and `BTC_USD` under a 60-period / 5-indicator scenario.
