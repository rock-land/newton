# Newton Development Tasks

**Current Version:** `0.6.0` (Stage 6 start)
**Latest Release:** `0.5.12` (Stage 5 complete)

Status: Active
**Source of truth:** `SPEC.md`

## Version Reference

| Version | Stage | Milestone |
|---------|-------|-----------|
| 0.1.0 | 1 | Stage 1 start |
| 0.1.5 | 1 | Stage 1 complete |
| 0.2.0 | 2 | Stage 2 start |
| 0.2.8 | 2 | Stage 2 complete |
| 0.3.0 | 3 | Stage 3 start |
| 0.3.10 | 3 | Stage 3 complete |
| 0.4.0 | 4 | Stage 4 start |
| 0.4.8 | 4 | Stage 4 complete |
| 0.5.0 | 5 | Stage 5 start |
| 0.5.12 | 5 | Stage 5 complete |
| 0.6.0 | 6 | Stage 6 start |

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
| T-2G | Stage gate: lint/type/test/coverage pass | fullstack | `ruff check .` PASS; `mypy src` PASS; `pytest --cov=src -q` PASS with ≥80% coverage; all T-2xx tasks DONE | DONE |

---

## Stage 3: ML Pipeline

**Branch:** `stage/3-ml-pipeline`

| ID | Task | Scope | Acceptance | Status |
|---|---|---|---|---|
| T-301 | Feature engineering pipeline for ML training and inference | server | `src/analysis/feature_engineering.py` implemented; builds feature vectors from OHLCV returns (not raw prices), indicator features from feature store, and token presence flags; rolling window of N periods (configurable, default 24 per strategy `ml_model.lookback_periods`); feature matrix output for XGBoost training; single-row feature vector for inference from FeatureSnapshot; tests with synthetic data verify feature construction, window handling, and return calculation | DONE |
| T-302 | Model artifact storage and versioning | server | `src/analysis/model_store.py` implemented; save/load model artifacts to disk with SHA-256 hash verification; `ModelArtifact` frozen dataclass with type, instrument, training date, hyperparameters, performance metrics, data hash; version tracking per instrument (monotonically incrementing); integrity verification on load (hash mismatch raises error); storage directory configurable (default `models/`); tests for save/load/verify cycle, corruption detection, version incrementing | DONE |
| T-303 | Walk-forward training framework | server | `src/analysis/walk_forward.py` implemented; walk-forward cross-validation with configurable train/test window sizes; default 2-year train, 6-month test, 6-month step per SPEC §9.1; 48-hour embargo between train and test sets; minimum 4 folds; per-fold metric collection (AUC-ROC); out-of-fold prediction collection for meta-learner training; no look-ahead guarantee; tests with synthetic data verify fold boundaries, embargo enforcement, and no look-ahead | DONE |
| T-304 | XGBoost model training and MLV1Generator | server | XGBoost training using walk-forward framework (T-303); Optuna hyperparameter search within training windows only; early stopping on validation loss; `MLV1Generator` in `src/trading/signal.py` rewritten from scaffold to real inference (load model → FeatureSnapshot → feature vector → predict → Signal); walk-forward AUC-ROC > 0.55 per instrument (if below, log warning and set `metadata.below_auc_threshold`); CNN-LSTM deferred unless XGBoost fails threshold; tests for model train/predict cycle, generator protocol compliance, AUC evaluation | DONE |
| T-305 | Regime detection subsystem | server | `src/regime/detector.py` rewritten from scaffold; `vol_30d` annualized realized volatility (√252 forex, √365 crypto); `ADX_14` 14-day ADX; `vol_median` 2-year rolling window recalculated monthly; 4 regime labels per SPEC §5.8.2; deterministic confidence formula `sqrt(clamp(d_vol) × clamp(d_adx))`; confidence bands HIGH (≥0.5) / MEDIUM (0.2–0.5) / LOW (<0.2); `RegimeState` frozen dataclass; tests for regime classification, confidence calculation, vol_median update | DONE |
| T-306 | Meta-learner and EnsembleV1Generator rewrite | server | `src/analysis/meta_learner.py` rewritten from scaffold to logistic regression stacking; inputs: Bayesian posterior, ML probability, regime confidence; trained on out-of-fold walk-forward predictions; calibration < 5pp per decile; `EnsembleV1Generator` in `src/trading/signal.py` rewritten to use meta-learner (fallback to weighted blend when untrained); signal interpretation per strategy thresholds; tests for meta-learner training, calibration, ensemble with and without meta-learner | DONE |
| T-306-FIX1 | Guard non-positive prices in regime detection and use NaN for missing indicator values | server | `compute_vol_30d()` raises `ValueError` when any close price ≤ 0; `_extract_row()` in feature_engineering.py uses `float('nan')` instead of `0.0` for missing indicator/return values (XGBoost handles NaN natively); tests added for zero/negative price guard and NaN propagation; quality gate passes | DONE |
| T-306-FIX2 | Enforce AUC threshold, implement validate_config, and evaluate calibration on held-out data | server | `train_xgboost()` returns `None` for `production_model_bytes` when AUC below threshold (SPEC §5.6 compliance); `MLV1Generator.validate_config()` and `EnsembleV1Generator.validate_config()` check required parameter keys; `train_meta_learner()` evaluates calibration on held-out split (not training data); tests added for AUC enforcement, config validation, and held-out calibration; quality gate passes | DONE |
| T-306-FIX3 | Cache XGBoost deserialization and add path sanitization to model store | server | `predict_xgboost()` accepts pre-deserialized booster or caches deserialized model to avoid redundant per-call deserialization; `model_store.py` validates `instrument` and `model_type` against `^[A-Za-z0-9_-]+$` regex, raises `ValueError` on path traversal attempts; tests added for caching behavior and path sanitization; quality gate passes | DONE |
| T-3G | Stage gate: lint/type/test/coverage pass | fullstack | `ruff check .` PASS; `mypy src` PASS; `pytest --cov=src -q` PASS with ≥80% coverage; all T-3xx tasks DONE | DONE |

---

## Stage 4: UAT & Admin UI

**Branch:** `stage/4-uat-admin`

| ID | Task | Scope | Acceptance | Status |
|---|---|---|---|---|
| T-401 | React + Vite + Tailwind + shadcn/ui foundation | client | React 18 + TypeScript + Vite configured in `client/`; Tailwind CSS v4 with dark mode; shadcn/ui initialized with base components (Button, Card, Table, Badge, Tabs, Sidebar); React Router with sidebar nav (Health, UAT Runner, Admin); API client layer with fetch wrapper; Vite dev server proxies `/api` to `localhost:8000`; existing health panel rebuilt as React component; `npm run dev` and `npm run build` work; DEC-015 recorded | DONE |
| T-402 | UAT test API endpoints | server | `GET /api/v1/uat/suites` lists test suites with test counts; `POST /api/v1/uat/run` executes suite or individual test by ID; ~25-30 behavioral tests across 7 suites (Data Pipeline, Event Detection, Bayesian, ML Training, Regime, Ensemble, End-to-End); each result: `{id, name, suite, status, duration_ms, details, error?}`; tests use synthetic data (no DB required for most); registered in API router; server-side tests pass | DONE |
| T-403 | UAT Runner UI | client | React page: suite cards with test counts, "Run All" / "Run Suite" buttons; results table with pass/fail badges, duration, expandable detail rows; summary bar (X/Y passed, total duration); re-run individual tests; loading states during execution; accessible from sidebar nav | DONE |
| T-404 | Interactive admin panels | fullstack | 4 panels accessible from sidebar: (1) Feature Explorer — browse features per instrument/interval, table with indicator values; (2) Signal Inspector — trigger signal generation per instrument, show probability/action/component scores/metadata; (3) Regime Monitor — regime state per instrument with vol_30d/ADX/classification/confidence band; (4) Model Dashboard — list model artifacts, version history, AUC metrics, training metadata; all panels use dark mode; API endpoints added as needed | DONE |
| T-405 | Refresh UAT.md with practical test plan | docs | Rewrite UAT.md with human-verifiable items; each item maps to automated test (suite:test_id) or interactive panel (page + what to look for); remove pure unit-test items covered by pytest; add verification instructions for each panel | DONE |
| T-405-FIX1 | Sanitize API error responses and add input validation | server | All `HTTPException(500)` in `data.py` use generic messages (no `{exc}` interpolation); `models.py` validates `model_type` against `_MODEL_TYPES` with 400 on invalid; `data.py` validates `instrument` on `get_ohlcv`, `get_features`, `compute_features`; `compute_features` has a row limit (≤50,000); `regime.py` wraps computation in try/except with `_unknown_regime` fallback; quality gate passes | DONE |
| T-405-FIX2 | Fix client API contract and app version | fullstack | `api.ts` `ohlcv()` requires `interval` and `start` params matching server; `app.py` reads version from `VERSION` file; `regime.py` step size corrected or comment fixed; React Fragment key added in ModelDashboard; `class="dark"` added to `index.html`; quality gate passes | DONE |
| T-4G | Stage gate: lint/type/test/build pass | fullstack | `ruff check .` PASS; `mypy src` PASS; `pytest --cov=src -q` PASS with ≥80% coverage; `cd client && npm run build` PASS; all T-4xx tasks DONE | DONE |

---

## Stage 5: Trading Engine

**Branch:** `stage/5-trading-engine`

| ID | Task | Scope | Acceptance | Status |
|---|---|---|---|---|
| T-501 | Implement `BrokerAdapter` protocol and domain models in `broker_base.py` | server | `BrokerAdapter` protocol per SPEC §3.3 with all 7 methods; frozen dataclasses for `AccountInfo`, `Position`, `OrderResult`, `OrderStatus`; `client_order_id` format `NEWTON-{instrument}-{timestamp_ms}` per §5.9; tests verify protocol compliance and dataclass immutability | DONE |
| T-502 | Implement `OandaAdapter` in `broker_oanda.py` | server | Oanda v20 REST API adapter implementing `BrokerAdapter`; `place_market_order` with `stopLossOnFill` per §5.9; retry 3× with exponential backoff (2s, 4s, 8s) per §3.5; validates against configured `base_url`; all methods tested with fake HTTP client | DONE |
| T-503 | Implement `BinanceSpotAdapter` in `broker_binance.py` | server | Binance REST API adapter implementing `BrokerAdapter`; HMAC-SHA256 signed requests; market order + immediate OCO stop-loss per §5.9; if OCO fails, close position and alert; minimum notional and lot size validation; commission accounted in position sizing; retry 3× with backoff; all methods tested with fake HTTP client | DONE |
| T-504 | Risk management engine in `risk.py` | server | Risk config loading with 3-tier precedence (instrument > strategy > global per §6.1); validation bounds enforced per §6.1; pre-trade checks per §6.3 (position limit, portfolio exposure, Kelly sizing, circuit breaker, data freshness, model freshness, regime confidence); Kelly criterion formula; in-trade controls (hard stop, trailing stop, time stop, volatility check) per §6.4; 100% branch coverage; tests cover all pre-trade check outcomes and sizing calculations | DONE |
| T-505 | Circuit breaker system in `circuit_breaker.py` | server | 5 circuit breakers per §6.5: daily loss, max drawdown, consecutive losses, model degradation, kill switch; per-instrument + portfolio scope; automatic reset (daily loss at 00:00 UTC, consecutive after timeout) and manual reset (max drawdown, kill switch); kill switch closes all positions on all brokers; state persisted and queryable; 100% branch coverage; tests cover trigger, reset, and edge cases for each breaker | DONE |
| T-506 | Order execution orchestrator in `executor.py` | server | End-to-end trade execution: signal → pre-trade checks → position sizing → order submission → stop-loss placement → trade record; `client_order_id` idempotency per §5.11; retry 3× on 5xx/timeout, no retry on 4xx; trade lifecycle (PENDING → OPEN → CLOSED); stop-loss updates per §6.4; writes to `trades` table; 100% branch coverage; tests cover full lifecycle with fake broker adapter | DONE |
| T-507 | Position reconciliation loop in `reconciler.py` | server | Reconciliation per §5.12: fetch broker positions, compare with internal `trades` (status=OPEN); classify MATCH/SYSTEM_EXTRA/BROKER_EXTRA; SYSTEM_EXTRA → mark CLOSED + CRITICAL alert; BROKER_EXTRA → halt entries + require manual review; log to `reconciliation_log` table; designed for 60s frequency; 100% branch coverage; tests cover all three classification states | DONE |
| T-508 | Trading API endpoints and kill switch | server | `GET /api/v1/trades` with filters; `POST /api/v1/kill` activate kill switch; `DELETE /api/v1/kill` deactivate with confirmation; `GET /api/v1/config/risk` current config; `PUT /api/v1/config/risk` update with validation + audit logging to `config_changes`; API tests for all endpoints | DONE |
| T-508-FIX1 | Binance adapter critical fixes: candle retrieval, get_positions, OCO stop-loss, dynamic quantity, direction-aware stop modification | server | `_fetch()` accepts JSON arrays; `get_candles()` parses raw klines array correctly; `get_positions()` returns actual positions from `/api/v3/account`; `place_market_order` places stop-loss order after fill (or closes + alerts on failure); `modify_stop_loss`/`close_position` use actual position quantity; `modify_stop_loss` derives side from direction; candle test uses real API response format; all tests pass with 100% coverage on changed code | DONE |
| T-508-FIX2 | Position sizing units conversion: dollar risk to instrument units | server | Kelly sizing output converted from dollar risk to instrument units using price/stop-distance; Oanda adapter sends correct lot size; Binance adapter sends correct BTC quantity; tests verify conversion math for both instruments; existing risk tests updated | DONE |
| T-508-FIX3 | Risk engine and circuit breaker spec compliance fixes | server | Trailing stop logic direction-aware for SELL trades; daily loss breaker latches once tripped (reset only at 00:00 UTC); non-kill-switch breakers trigger position closure callback; idempotency check uses narrow exception type (`KeyError`/`LookupError`); tests cover SELL trailing stops, daily loss latch behavior, breaker position closure, and narrow exception handling | DONE |
| T-5G | Stage gate: lint/type/test/coverage pass | fullstack | `ruff check .` PASS; `mypy src` PASS; `pytest --cov=src -q` PASS ≥80% global; 100% branch on `risk.py`, `executor.py`, `reconciler.py`, `circuit_breaker.py`; all T-5xx tasks DONE | DONE |

---

## Stage 6: Backtesting

**Branch:** `stage/6-backtesting`

| ID | Task | Scope | Acceptance | Status |
|---|---|---|---|---|
| T-601 | Implement trade simulation engine in `simulator.py` | server | Per-instrument fill model per SPEC §9.2: EUR/USD fill at `open[T+1] ± (1.0 pip slippage + 0.75 pip half-spread)`, BTC/USD fill at `open[T+1] ± (0.02% slippage + 0.025% half-spread)` + 0.10% taker commission; pessimistic mode with 2× slippage/spread multiplier; no partial fills or rejects; frozen `SimulatedFill` dataclass; tests verify fill price math for both instruments in normal and pessimistic modes | DONE |
| T-602 | Implement backtest engine in `engine.py` | server | End-to-end backtest orchestration: loads OHLCV data → computes features → generates signals via `SignalGenerator` → applies pre-trade risk checks → simulates fills → tracks positions with stop-loss management (hard/trailing/time stops) → records trade lifecycle; per-instrument execution with configurable date range; uses `SimulatedFill` from T-601; frozen `BacktestResult` with equity curve, trade list, and raw metrics; tests with synthetic data verify full lifecycle | DONE |
| T-603 | Implement performance metrics in `metrics.py` | server | All §9.5 metrics: Sharpe ratio (√252 forex, √365 crypto), profit factor, max drawdown, win rate, Calmar ratio, expectancy, calibration error (per decile); hard gate evaluation (Sharpe >0.8, PF >1.3, DD <15%, expectancy >0, trade count >30/fold, cal error <5pp); portfolio-level metrics (portfolio Sharpe, max portfolio DD <20%, instrument return correlation); frozen `PerformanceMetrics` and `MetricGateResult` dataclasses; tests verify each formula against hand-calculated values | DONE |
| T-604 | Implement purged K-fold cross-validation | server | K=5 purged K-fold per SPEC §9.2: 48-hour purge zones between train/test; per-instrument execution; per-fold metric collection; complements walk-forward (T-303) as robustness check; frozen `KFoldResult` dataclass; tests verify fold boundaries, purge zone enforcement, and no data leakage | DONE |
| T-605 | Implement regime-aware reporting in `report.py` | server | Per-regime performance breakdown per §9.4: Sharpe, PF, win rate per regime per instrument; regime transition timeline; regime-adjusted metrics weighted by time-in-regime; low-sample flagging (<20 trades in any fold); bias controls checklist per §9.3 (look-ahead, overfitting, survivorship, selection, data snooping); frozen `BacktestReport` dataclass; JSON-serializable output; tests verify regime breakdown, low-sample flagging, and bias control metadata | DONE |
| T-606 | Backtest API endpoints | server | `POST /api/v1/backtest` — run backtest (instrument, strategy, date range, pessimistic mode flag); `GET /api/v1/backtest/{id}` — retrieve results; results include equity curve, trade list, metrics, gate results, regime breakdown, bias controls; async execution with status polling or sync for small date ranges; API tests for both endpoints | DONE |
| T-607 | Backtest Runner UI | client | React page accessible from sidebar: instrument selector, date range picker, pessimistic mode toggle, "Run Backtest" button; progress/status display during execution; results view with equity curve chart (Recharts), metrics summary cards (Sharpe, PF, DD, win rate, expectancy), gate pass/fail badges; trade list table with entry/exit/PnL/duration; dark mode | DONE |
| T-608 | Backtest results viewer and comparison UI | client | Regime overlay on equity curve chart; calibration plot (predicted vs observed by decile); per-regime metrics breakdown table with low-sample flags; backtest comparison: side-by-side two runs with diff highlighting on metrics; trade overlay on candlestick chart (entry/exit markers, stop levels, regime shading); backtest history list with run metadata | DONE |
| T-608-FIX1 | Backtest API fixes: interval mismatch, thread safety, bounded storage, error sanitization, input validation | server | RC-1 `"H1"`→`"1h"` fixed; RC-4 `_RunState` guarded by `threading.Lock`; RH-2 max 100 runs with LRU eviction; RH-4 generic error messages (internal details logged only); RH-5 `initial_equity` upper bound + date range max 5yr; tests for all fixes | DONE |
| T-608-FIX2 | Financial formula corrections: Sharpe risk-free rate, CAGR, calibration error, portfolio Sharpe | server | RC-2 Sharpe subtracts daily risk-free rate from returns; RH-1 compound CAGR formula replaces linear; RM-4 `ValueError` raised on length mismatch; RM-5 consistent annualization convention for portfolio metrics; existing metric tests updated with corrected expected values | DONE |
| T-608-FIX3 | Engine simulation accuracy: exit costs, feature snapshot, regime integration, cash guard, dead code | server | RC-3 exit fills simulated with slippage/spread/commission; SR-H3 `_build_features` computes indicator features via `FeatureProvider`; SR-M1 regime detector integrated for per-trade labels; RM-2 `cash >= cost` guard before entry; RM-3 dead branch removed; tests cover exit cost PnL reduction, negative cash skip, and regime label assignment | DONE |
| T-6G | Stage gate: lint/type/test/build pass | fullstack | `ruff check .` PASS; `mypy src` PASS; `pytest --cov=src -q` PASS ≥80% global; `cd client && npm run build` PASS; all T-6xx tasks DONE | TODO |

---

## Backlog

<!--
Backlog lists planned stages at a high level. Detailed tasks are generated
during /stage-init, NOT in advance. Keep entries lightweight.
-->

| Stage | Name | Summary |
|-------|------|---------|
| ~~5~~ | ~~Trading Engine~~ | ~~Active — see Stage 5 above~~ |
| ~~6~~ | ~~Backtesting~~ | ~~Active — see Stage 6 above~~ |
| 7 | Client Web UI | Signal display, data viewer with charting, trade monitoring — React foundation from Stage 4 (SPEC §8) |
| 8 | Paper Trading | Oanda practice account + Binance testnet integration, live data pipeline (SPEC §11) |
| 9 | Live Trading | Production deployment, monitoring, kill switches, operational runbooks (SPEC §11) |

---

## Notes

- Keep task IDs stable for commit references.
- Update status values only: TODO / IN_PROGRESS / BLOCKED / DONE.
- Tasks within a stage are populated by `/stage-init`.
- Fix tasks are appended at the end of the relevant stage with `-FIXn` suffix.
