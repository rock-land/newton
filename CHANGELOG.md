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
