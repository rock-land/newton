# Newton Development Tasks

**Current Version:** `0.1.0` (Stage 1, Task 0)
**Latest Release:** —

Status: Active
**Source of truth:** `SPEC.md`

## Version Reference

| Version | Stage | Milestone |
|---------|-------|-----------|
| 0.1.0 | 1 | Stage 1 start |

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
| T-103 | Remove stale client entry point and record Dockerfile deferral | fullstack | `client/src/main.js` deleted; DEC-012 recorded in DECISIONS.md deferring Dockerfile implementation to Stage 7; Dockerfile unchanged (stub retained) | TODO |
| T-1G | Stage gate: lint/type/test/coverage pass | fullstack | `ruff check .` PASS; `mypy src` PASS; `pytest --cov=src -q` PASS with >=80% coverage; all T-1xx tasks DONE | TODO |

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
