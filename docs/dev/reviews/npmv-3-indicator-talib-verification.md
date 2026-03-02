# N-PMV-3 Indicator TA-Lib Verification (Stage 1)

Date (UTC): 2026-02-18 10:22
Branch: `stage/2-event-detection`
Task: `N-PMV-3`

## Scope
- Verify Stage 1 indicator outputs against TA-Lib reference implementation.
- Indicators: RSI, MACD (line/signal/histogram), Bollinger Bands (upper/middle/lower), OBV, ATR.
- Instruments: `EUR_USD`, `BTC_USD`.
- Interval: `1h`.
- Acceptance threshold: **max deviation < 0.01%**.

## Stage 1 Indicator Computation Paths
- Source file: `src/data/indicators.py`
- Provider: `TechnicalIndicatorProvider` (`technical_indicator_provider_v1`)
- Feature keys:
  - `rsi:period=14`
  - `macd:fast=12,slow=26,signal=9:line|signal|histogram`
  - `bb:period=20,std=2.0:upper|middle|lower`
  - `obv:`
  - `atr:period=14`

## Methodology
1. Load verified OHLCV candles from `ohlcv` where `verified = TRUE` for each instrument.
2. Build Newton outputs via `TechnicalIndicatorProvider.get_features(...)` with full lookback.
3. Build TA-Lib references using:
   - `talib.RSI(period=14)`
   - `talib.MACD(fast=12, slow=26, signal=9)`
   - `talib.BBANDS(period=20, nbdevup=2, nbdevdn=2, matype=SMA)`
   - `talib.OBV`
   - `talib.ATR(period=14)`
4. Randomly sample 100 timestamps per instrument (seed=20260218) from eligible candles after warmup.
   - Warmup index floor: `40` (covers slowest indicator history requirements).
5. Compute percentage deviation per field:

```text
pct_deviation = abs(newton - talib) / max(abs(talib), 1e-12) * 100
```

6. Aggregate per field: max and mean deviation across 200 points total (100 x 2 instruments).

## Sample Strategy
- Dataset: verified DB candles (`ohlcv`) for `1h` interval.
- Instruments sampled independently, each with 100 unique random indices.
- Random seed fixed for reproducibility: `20260218`.

## Deviation Results

| Indicator field | Samples | Max deviation (%) | Mean deviation (%) |
|---|---:|---:|---:|
| RSI | 200 | 0.000000000000 | 0.000000000000 |
| MACD Line | 200 | 0.000000000000 | 0.000000000000 |
| MACD Signal | 200 | 0.000000000000 | 0.000000000000 |
| MACD Histogram | 200 | 0.000000000000 | 0.000000000000 |
| Bollinger Upper | 200 | 0.000000000000 | 0.000000000000 |
| Bollinger Middle | 200 | 0.000000000000 | 0.000000000000 |
| Bollinger Lower | 200 | 0.000000000000 | 0.000000000000 |
| OBV | 200 | 0.000000000000 | 0.000000000000 |
| ATR | 200 | 0.000000000000 | 0.000000000000 |

## Verdict
**PASS** — threshold is max deviation < `0.01%` for every indicator field.

## Sampled Timestamp Coverage (first 5 shown)
- `EUR_USD`: 100 samples (first 5: 2023-02-07T20:00:00Z, 2023-02-17T13:00:00Z, 2023-03-16T15:00:00Z, 2023-04-07T12:00:00Z, 2023-04-10T18:00:00Z)
- `BTC_USD`: 100 samples (first 5: 2023-01-05T16:00:00Z, 2023-01-17T17:00:00Z, 2023-02-22T15:00:00Z, 2023-03-01T14:00:00Z, 2023-03-05T11:00:00Z)

## N-PMV-3B Regression Gate
- Added CI-facing parity regression test focused on TA-Lib equivalence for MACD + OBV:
  - `tests/unit/test_indicators_provider.py::test_technical_indicator_macd_obv_parity_regression_gate`
- Gate rule: max percent deviation must remain `< 0.01%` across 100 deterministic random samples (post-warmup) for MACD line/signal/histogram and OBV.
