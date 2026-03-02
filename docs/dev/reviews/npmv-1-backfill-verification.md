# N-PMV-1 Backfill Verification (Stage 1)

Date (UTC): 2026-02-18 09:10
Branch: `stage/2-event-detection`
Task: `N-PMV-1`

## Scope
- Run 3-year backfill verification for:
  - `EUR_USD` (Oanda)
  - `BTC_USD` (Binance BTCUSDT)
- Validate row counts in `ohlcv` (verified rows) against expected counts with ±1% tolerance.
- Primary verification interval used for Stage 1 acceptance: `1h` (`signal_interval` from config).

## Commands Run

### 1) DB reachability
```bash
docker ps -a --filter name=newton-timescaledb --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
source .venv/bin/activate && python scripts/db_status.py
```

### 2) Trigger backfill path (existing pipeline tooling)
Used existing fetcher + verifier + verified-store path from:
- `src/data/fetcher_oanda.py`
- `src/data/fetcher_binance.py`
- `src/data/verifier.py`

Executed with environment credentials loaded from `.env` and chunked historical fetches:
- `EUR_USD` in 60-day chunks (`fetch_historical`)
- `BTC_USD` in 30-day chunks (`fetch_historical`, Binance `limit=1000`)

Observed totals during run:
- `EUR_USD`: fetched/stored `19472`
- `BTC_USD`: fetched/stored `27502`

### 3) Query verified counts in DB (3-year window)
Window used for deterministic hourly expectation:
- `start = 2023-01-01T00:00:00Z`
- `end = floor_to_hour(now_utc)` => `2026-02-18T09:00:00Z`

SQL (per instrument):
```sql
SELECT count(*), min(time), max(time)
FROM ohlcv
WHERE instrument = $1
  AND interval = '1h'
  AND verified = TRUE
  AND time >= '2023-01-01T00:00:00Z'
  AND time <  '2026-02-18T09:00:00Z';
```

## Results

### Actual verified row counts (`ohlcv`, interval=`1h`)
- `EUR_USD`: `19472` rows
  - min: `2023-01-01T23:00:00Z`
  - max: `2026-02-18T08:00:00Z`
- `BTC_USD`: `27464` rows
  - min: `2023-01-01T00:00:00Z`
  - max: `2026-02-18T08:00:00Z`

### Expected row counts
- `BTC_USD` (24/7):
  - Expected = total hourly buckets in window
  - `expected_btc = (end - start) / 1h = 27465`

- `EUR_USD` (24/5):
  - Expected = hourly buckets where candle open is Monday-Friday (UTC)
  - `expected_eur = 19617`

## Tolerance Math (±1%)

### EUR_USD
- Expected: `19617`
- Actual: `19472`
- Delta: `-145`
- Percent error: `145 / 19617 = 0.739%`
- Allowed band: `[19420.83, 19813.17]`
- Verdict: **PASS**

### BTC_USD
- Expected: `27465`
- Actual: `27464`
- Delta: `-1`
- Percent error: `1 / 27465 = 0.0036%`
- Allowed band: `[27190.35, 27739.65]`
- Verdict: **PASS**

## Overall Verdict
**PASS** — both instruments are within ±1% row-count tolerance for the 3-year `1h` verification window.
