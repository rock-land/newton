# Runbooks

## Data ingestion verification alerts (N-006)

Verification checks run every ingestion cycle (`src/data/pipeline.py`):

- Gap detection (missing candles)
- Duplicate handling (dedupe by timestamp)
- OHLC integrity checks
- Staleness watchdog (no new candle within `2x` expected interval)

### Log events

- `event=ingestion_cycle` (INFO): summary counters + `halt_signals`
- `event=data_verification_alert` (WARNING): one alert-ready payload per issue

### Immediate operator actions

1. **`stale_data` (critical)**
   - Confirm broker/exchange connectivity.
   - Confirm fetcher endpoint health and recent candle availability.
   - Keep signal generation halted for the instrument until fresh candles resume.
2. **`ohlc_integrity` (critical)**
   - Review suspect candle timestamps and source payload.
   - Exclude suspect candles from signal path (already default behavior).
   - Investigate source anomalies or parser regressions.
3. **`gaps` / `duplicate_candles` (warning)**
   - Trigger backfill for missing ranges.
   - Validate dedupe counts against source responses.

### Verification output contract

Alert payload fields:

- `instrument`
- `interval`
- `issue_type`
- `severity`
- `message`
- `details`
