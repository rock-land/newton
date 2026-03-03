# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows the stage-based format: `0.{STAGE}.{TASK}`.

This changelog is updated at each stage completion (when the stage gate is shipped).

<!--
Entries are added by /ship when shipping a stage gate task.
Each stage gets a version entry summarizing all work completed in that stage.
Categories: Added, Changed, Deprecated, Removed, Fixed, Security
-->

## [0.2.8] - 2026-03-04

### Added
- Event detection and labeling system (`src/analysis/events.py`) — binary event labeling from OHLCV candles with configurable thresholds and horizons per instrument (T-202)
- Tokenizer and classification vocabulary (`src/analysis/tokenizer.py`) — indicator-to-token mapping with per-instrument classification rules for RSI, MACD, BB, OBV, ATR (T-203)
- Token classification configs (`config/classifications/EUR_USD_classifications.json`, `BTC_USD_classifications.json`) — 22 rules each (T-203)
- Token selection via mutual information (`src/analysis/token_selection.py`) — MI scoring, Jaccard similarity dedup, top-N selection with configurable max of 50 (T-204)
- Bayesian inference engine (`src/analysis/bayesian.py`) — Naive Bayes with Laplace smoothing, log-odds prediction, isotonic calibration, posterior capping, phi correlation checks (T-205)
- BayesianV1Generator integration — full inference path: FeatureSnapshot → tokenize → predict → Signal (T-206)
- Data-layer edge case tests for empty candle lists, zero-volume candles, zero-range candles (T-206)
- DEC-013 decision record for FeatureProvider sync batch signature (T-206)
- DEC-014 decision record for event labeling high-watermark approach (T-206-FIX1)
- 170 new tests (55 → 225), coverage 85% → 89%

### Changed
- `BayesianV1Generator` rewritten from scaffold to full Bayesian inference with scaffold fallback when no model/rules configured (T-206)
- `_action_from_probability` uses strict `>` comparison per SPEC §5.7 (T-201)
- `MLV1Generator` refactored to independent class (no inheritance from BayesianV1) (T-201)
- Ensemble weight validation enforces sum to 1.0 (±0.01) (T-201)
- `_build_signal` clamps probability before computing action (T-201)
- `config/feature_providers.json` class path corrected to `src.data.indicators.TechnicalIndicatorProvider` (T-206)
- Generator override in `route_signal` preserves instrument-specific thresholds (T-206-FIX1)
- `generate_batch()` uses instrument-appropriate thresholds from config parameters (T-206-FIX1)

### Fixed
- `BayesianV1Generator.generate()` raises `RecoverableSignalError` when `_close` missing from features with model+rules present (T-206-FIX1)
- Default close fallback silently using 0.0 instead of failing explicitly (T-206-FIX1)
- Generator override discarding instrument-specific thresholds and using defaults (T-206-FIX1)
- Batch signal generation ignoring config-level threshold overrides (T-206-FIX1)

## [0.1.5] - 2026-03-03

### Added
- pytest-cov wired into test suite with `addopts = --cov=src --cov-report=term-missing` — baseline coverage 85% (T-101)
- Scaffold markers on signal endpoints — `"scaffold": true` field and warning in response metadata (T-102)
- DEC-012 decision record deferring Dockerfile implementation to Stage 7 (T-103)
- Exception logging in health check `except` blocks via `logger.exception()` (T-103-FIX1)
- 11 new tests (44 → 55) covering scaffold markers, URL validation, and health check logging

### Changed
- Oanda fetcher URL validation now validates against configured `base_url` netloc instead of hardcoded practice domain (T-103-FIX1)
- Binance fetcher URL validation applies same dynamic netloc validation for testnet compatibility (T-103-FIX1)

### Removed
- Stale `client/src/main.js` vanilla JS entry point (287 lines) — `client/src/main.tsx` scaffold retained (T-103)
- Built artifact `client/public/dist/main.js` (T-103)

### Fixed
- Hardcoded Oanda URL validation that would reject live trading API URLs (T-103-FIX1)
- Hardcoded Binance URL validation that would reject testnet URLs (T-103-FIX1)
- Silent exception swallowing in health check database and candle age queries (T-103-FIX1)
