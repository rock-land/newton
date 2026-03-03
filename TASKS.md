# Newton Development Tasks

**Current Version:** `0.2.0` (Stage 2, Task 0)
**Latest Release:** `0.1.5` (Stage 1 complete)

Status: Active
**Source of truth:** `SPEC.md`

## Version Reference

| Version | Stage | Milestone |
|---------|-------|-----------|
| 0.1.0 | 1 | Stage 1 start |
| 0.1.5 | 1 | Stage 1 complete |
| 0.2.0 | 2 | Stage 2 start |

## Rules
- Work only from `SPEC.md` unless the lead explicitly approves deviation.
- Use TDD for every implementation task.
- Keep tasks small and testable.

## Task ID Scheme
- Stage N tasks: `T-N01`, `T-N02`, ... `T-Nnn` (e.g., `T-101` for Stage 1 task 1)
- Stage gate: `T-NG` (e.g., `T-1G` for Stage 1 gate)
- Fix tasks: `T-Nnn-FIX1`, `T-Nnn-FIX2` (appended at end of stage)

---

## Summary of Completed Work (Pre-Governance)

The following work was completed before governance was established. This is not a retroactive stage — it documents the existing codebase state.

### Data Pipeline (Complete)
- Oanda EUR/USD fetcher (`src/data/fetcher_oanda.py`) — REST API integration with candle normalization and storage
- Binance BTC/USD fetcher (`src/data/fetcher_binance.py`) — REST API integration with closed-candle filtering and quote volume normalization
- Data verification pipeline (`src/data/verifier.py`) — deduplication, OHLC integrity, gap detection, staleness alerts
- Technical indicators (`src/data/indicators.py`) — RSI(14), MACD(12,26,9), BB(20,2.0), OBV, ATR(14) with TA-Lib + pure Python fallback
- Feature store (`src/data/feature_store.py`) — write, query, metadata registry for computed features
- Feature provider protocol (`src/data/feature_provider.py`) — pluggable feature source interface
- Database bootstrap (`src/data/database.py`) — TimescaleDB migration system (ohlcv, features, feature_metadata tables)
- Data ingestion pipeline (`src/data/pipeline.py`) — orchestration of fetch → verify → store → compute → store cycle
- Configuration validation (`src/data/schema.py`) — Pydantic v2 schemas with cross-field constraints

### Signal Infrastructure (Complete)
- Signal contract (`src/analysis/signal_contract.py`) — Signal, FeatureSnapshot, SignalGenerator protocol
- Signal routing (`src/trading/signal.py`) — GeneratorRegistry, SignalRouter, BayesianV1/MLV1/EnsembleV1 generators
- Per-instrument routing with fallback chains and neutral fail-safe

### API Layer (Partial)
- FastAPI application (`src/app.py`) — versioned API with static client mount
- Health endpoint (`/api/v1/health`) — DB, broker, candle freshness checks with checksums
- Data endpoints (`/api/v1/ohlcv/{instrument}`, `/api/v1/features/*`) — OHLCV and feature queries
- Signal endpoints (`/api/v1/signals/*`) — generator listing and scaffold signal generation

### Test Suite (44 tests, all passing)
- Unit tests for all implemented modules (11 test files)
- Integration tests for config validation and scaffold verification
- Scenario tests for workflow patterns

### Infrastructure
- Docker Compose for TimescaleDB
- Quality gate: ruff (lint), mypy strict (types), pytest (tests)
- All JSON configuration files for instruments, strategies, risk, features

---

## Stage 1: Remediation & Hardening

**Branch:** `stage/1-remediation`

| ID | Task | Scope | Acceptance | Status |
|---|---|---|---|---|
| T-101 | Wire pytest-cov into test suite and establish baseline coverage | server | `pytest --cov=src -q` runs by default; coverage report shows >=80% global; pytest.ini updated with `addopts = --cov=src --cov-report=term-missing`; CLAUDE.md quality gate reflects coverage command | DONE |
| T-102 | Mark signal endpoint as scaffold-only with clear response metadata | server | `GET /api/v1/signals/{instrument}` response includes `"scaffold": true` field and a warning in the response metadata; hardcoded dummy FeatureSnapshot replaced with explicit scaffold marker; tests updated to verify scaffold flag | DONE |
| T-103 | Remove stale client entry point and record Dockerfile deferral | fullstack | `client/src/main.js` deleted; DEC-012 recorded in DECISIONS.md deferring Dockerfile implementation to Stage 7; Dockerfile unchanged (stub retained) | DONE |
| T-103-FIX1 | Fix hardcoded URL validation in fetchers and add exception logging to health checks | server | Oanda fetcher validates against configured `self._base_url` netloc, not hardcoded practice domain; Binance fetcher applies same fix for testnet compatibility; health check `except` blocks log exceptions via `logger.exception()` before returning defaults; existing tests still pass; new tests verify URL validation accepts configured base URLs | DONE |
| T-1G | Stage gate: lint/type/test/coverage pass | fullstack | `ruff check .` PASS; `mypy src` PASS; `pytest --cov=src -q` PASS with >=80% coverage; all T-1xx tasks DONE | DONE |

---

## Stage 2: Event Detection & Tokenization

**Branch:** `stage/2-event-detection`

| ID | Task | Scope | Acceptance | Status |
|---|---|---|---|---|
| T-201 | Resolve deferred Stage 1 signal-layer findings | server | `_action_from_probability` uses strict `>` per SPEC §5.7; `MLV1Generator` is independent class (no inheritance from BayesianV1); ensemble weights validated to sum to 1.0 (±0.01); `_build_signal` clamps probability before computing action; tests cover probability at each threshold boundary; tests cover register-after-freeze, unknown generator_id, invalid instrument 404 on signal endpoint | DONE |
| T-202 | Event detection and labeling system | server | `src/analysis/events.py` implemented; event types loaded from strategy config `events` field; given OHLCV candles, labels each timestamp with binary event occurrence (e.g., "price moved ≥1% in next 24h"); frozen `EventLabel` dataclass; both instruments supported; tests with synthetic candle data | DONE |
| T-203 | Tokenizer and classification vocabulary | server | `src/analysis/tokenizer.py` implemented; classification rules defined for RSI, MACD, BB, OBV, ATR; `config/classifications/EUR_USD_classifications.json` and `BTC_USD_classifications.json` populated with token vocabularies; token format matches SPEC §5.3 (`{INSTRUMENT}_{PREFIX}_{PARAM}_{DATAPOINT}_{TYPE}_{VALUE}`); frozen `TokenSet` dataclass; tests verify token generation for known indicator values | DONE |
| T-204 | Token selection via mutual information | server | `src/analysis/token_selection.py` implemented; computes MI `I(Token; Event)` for all tokens; ranks by MI score; Jaccard similarity dedup (threshold from config, default 0.85); selects top-N tokens (from config, default 20, max 50); returns selected set with scores; tests with synthetic data verify ranking, dedup, and selection | DONE |
| T-205 | Bayesian inference engine | server | `src/analysis/bayesian.py` implemented; training computes prior P(Event) and likelihoods P(Token\|Event) with Laplace smoothing (configurable alpha); prediction uses log-odds form (numerically stable); isotonic calibration on out-of-fold predictions; posterior cap (configurable, default 0.90); phi correlation check with warning if \|phi\| > 0.7; frozen `BayesianModel` dataclass for trained params; tests verify posterior math, calibration, capping, and correlation alerts | DONE |
| T-206 | BayesianV1Generator integration and data-layer fixes | server | `BayesianV1Generator` in `signal.py` rewritten to use Bayesian engine; inference path: FeatureSnapshot → tokenize → predict → Signal; DEC-013 recorded for FeatureProvider sync batch signature decision (SR-H5); `feature_providers.json` class path fixed (SR-H6); data-layer edge case tests added (SR-TG4: empty candle list, zero-volume candles); end-to-end integration test with synthetic data passes | DONE |
| T-206-FIX1 | Fix default close fallback and action threshold inconsistencies in signal generators | server | `BayesianV1Generator.generate()` raises `RecoverableSignalError` when `_close` missing from features (model+rules present); generator override in `route_signal` preserves instrument-specific thresholds; `generate_batch()` signals use instrument-appropriate thresholds; DEC-014 recorded for event labeling high-watermark approach; quality gate passes | DONE |
| T-2G | Stage gate: lint/type/test/coverage pass | fullstack | `ruff check .` PASS; `mypy src` PASS; `pytest --cov=src -q` PASS with ≥80% coverage; all T-2xx tasks DONE | TODO |

---

## Backlog

<!--
Backlog lists planned stages at a high level. Detailed tasks are generated
during /stage-init, NOT in advance. Keep entries lightweight.
-->

| Stage | Name | Summary |
|-------|------|---------|
| 2 | Event Detection & Tokenization | Indicator event detection, token generation, Bayesian scoring (SPEC §5) |
| 3 | ML Pipeline | Feature engineering, XGBoost training, model evaluation, stacking meta-learner (SPEC §5.4-5.5) |
| 4 | Trading Engine | Broker adapters, risk management, order execution, reconciliation, circuit breakers (SPEC §6) |
| 5 | Backtesting | Walk-forward validation, purged K-fold CV, performance metrics, reporting (SPEC §9) |
| 6 | Client Web UI | Health panel, data viewer, signal display, trade monitoring (SPEC §8) |
| 7 | Paper Trading | Oanda practice account + Binance testnet integration, live data pipeline (SPEC §11) |
| 8 | Live Trading | Production deployment, monitoring, kill switches, operational runbooks (SPEC §11) |

---

## Notes

- Keep task IDs stable for commit references.
- Update status values only: TODO / IN_PROGRESS / BLOCKED / DONE.
- Tasks within a stage are populated by `/stage-init`.
- Fix tasks are appended at the end of the relevant stage with `-FIXn` suffix.
