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

## [0.6.12] - 2026-03-06

### Added
- Trade simulation engine (`src/backtest/simulator.py`) — per-instrument fill models for EUR/USD (pip-based slippage/spread) and BTC/USD (%-based + 0.10% taker commission) with pessimistic mode 2× multiplier (T-601)
- Backtest engine (`src/backtest/engine.py`) — end-to-end simulation: OHLCV → pre-computed features → signal generation → risk checks → fill simulation → position management (hard/trailing/time stops) → equity curve + trade list (T-602)
- Performance metrics (`src/backtest/metrics.py`) — all SPEC §9.5 metrics: Sharpe ratio (with risk-free rate), profit factor, max drawdown, win rate, Calmar ratio, expectancy, calibration error per decile; hard/informational gate evaluation; portfolio-level metrics (portfolio Sharpe, max portfolio DD, instrument return correlation) (T-603)
- Purged K-fold cross-validation (`src/backtest/kfold.py`) — K=5 with 48-hour purge zones, per-instrument execution, per-fold metric collection (T-604)
- Regime-aware reporting (`src/backtest/report.py`) — per-regime performance breakdown (Sharpe, PF, win rate), regime transition timeline, regime-adjusted metrics, low-sample flagging (<20 trades), bias controls checklist per §9.3 (T-605)
- Backtest API endpoints (`src/api/v1/backtest.py`) — `POST /api/v1/backtest` (run), `GET /api/v1/backtest/{id}` (retrieve), `GET /api/v1/backtest` (list); thread-safe async execution with ThreadPoolExecutor; bounded storage (max 100 runs, LRU eviction) (T-606)
- Backtest Runner UI (`client/src/pages/BacktestPage.tsx`) — instrument selector, date range picker, pessimistic toggle, equity curve chart (Recharts), metrics summary cards, gate pass/fail badges, trade list table (T-607)
- Backtest results viewer and comparison UI — regime overlay on equity curve, calibration plot, per-regime breakdown table, candlestick chart with trade markers, backtest history list, side-by-side run comparison with diff highlighting (T-608)
- 11 Pydantic response schemas for backtest API in `src/api/schemas.py` (T-606)
- 176 new tests (679 → 855), coverage 92% global

### Changed
- Sharpe ratio formula includes configurable `risk_free_rate` parameter per SPEC §9.5 (T-608-FIX2)
- Annualized return uses compound CAGR formula `(1 + total_return)^(periods_per_year / n_periods) - 1` instead of linear scaling (T-608-FIX2)
- Portfolio Sharpe uses consistent `√365` (calendar days) convention instead of averaging instrument-specific factors (T-608-FIX2)
- Backtest engine pre-computes features via `TechnicalIndicatorProvider` for realistic signal generation (T-608-FIX3)
- Backtest engine integrates regime detection via `classify_regime()` for per-trade regime labels (T-608-FIX3)

### Fixed
- Backtest API interval mismatch `"H1"` → `"1h"` — was producing empty results with real candle data (T-608-FIX1)
- Thread-unsafe `_RunState` mutation — all state access now guarded by `threading.Lock` (T-608-FIX1)
- Unbounded in-memory run storage — capped at 100 runs with LRU eviction of oldest completed (T-608-FIX1)
- API error message leaking internal exception details — now uses generic message with server-side logging (T-608-FIX1)
- Missing input validation — `initial_equity` upper bound (10M), date range max 5 years (T-608-FIX1)
- Exit-side transaction costs never applied — `simulate_fill()` now called on exits with reversed direction for slippage, spread, and commission (T-608-FIX3)
- Cash balance could go negative (implicit leverage) — added `cash >= cost_of_entry` guard before trade entry (T-608-FIX3)
- Calibration error silently returning 0.0 on length mismatch — now raises `ValueError` (T-608-FIX2)
- Dead code branch in `_trade_stats()` removed (T-608-FIX3)

### Security
- Backtest API error responses sanitized — no internal exception details exposed to clients (T-608-FIX1)
- Input validation at API boundary for initial equity and date range (T-608-FIX1)

## [0.5.12] - 2026-03-06

### Added
- BrokerAdapter protocol (`src/trading/broker_base.py`) — unified order/position interface for multi-broker trading with `OrderNotFoundError` idempotent cancel support (T-501)
- Immutable trading domain models — `Order`, `Position`, `TradeRecord`, `Fill`, `AccountSummary`, `PositionDelta` frozen dataclasses (T-501)
- OandaAdapter (`src/trading/broker_oanda.py`) — Oanda REST v20 broker adapter: market/limit orders, OCO stop-loss, position queries, account summary (T-502)
- BinanceSpotAdapter (`src/trading/broker_binance.py`) — Binance spot adapter: market/limit orders, STOP_LOSS_LIMIT stops, `get_json_list` for multi-format responses, position tracking (T-503)
- Risk management engine (`src/trading/risk.py`) — pre-trade checks (drawdown, correlation, exposure, staleness, regime), Kelly criterion sizing, direction-aware trailing stops for BUY/SELL, in-trade controls (T-504)
- Circuit breaker system (`src/trading/circuit_breaker.py`) — daily loss limit with latch, max open positions, rapid-fire trade guard, `BreakerTrip` returns with action field, system-wide kill switch (T-505)
- Order execution orchestrator (`src/trading/executor.py`) — signal→pre-trade→sizing→order→stop-loss→trade-record pipeline, dollar→units conversion, `OrderNotFoundError` idempotent handling (T-506)
- Position reconciliation loop (`src/trading/reconciler.py`) — broker vs internal position comparison, MATCH/SYSTEM_EXTRA/BROKER_EXTRA classification, configurable reconcile interval (T-507)
- Trading API endpoints (`src/api/v1/trading.py`) — `GET /trades`, `POST /kill`, `DELETE /kill` with safety confirm, `GET/PUT /config/risk` with Pydantic validation and audit logging (T-508)
- 238 new tests (441 → 679), coverage 93% → 92% (new modules fully covered, denominator increased)

### Changed
- Risk pre-trade checks return structured `PreTradeResult` with rejection reasons instead of bare bool (T-504)
- Circuit breaker `check()` returns `BreakerTrip` dataclass with `action` field instead of raising exceptions (T-505)
- Trailing stop calculation is direction-aware: BUY positions trail upward, SELL positions trail downward (T-508-FIX1)

### Fixed
- Binance adapter `get_json_list()` handles both `list` and `dict` API responses without crashing (T-508-FIX1)
- Dollar→units position sizing correctly converts notional amounts using current price (T-508-FIX2)
- Risk `evaluate_in_trade_controls()` handles zero entry price without division-by-zero (T-508-FIX1)
- Circuit breaker daily loss check uses absolute value for threshold comparison (T-508-FIX3)
- `OrderNotFoundError` during cancel treated as success (idempotent) instead of raising (T-508-FIX3)

### Security
- Kill switch requires `confirm=true` query parameter for deactivation — prevents accidental disabling (T-508)
- Risk config PUT endpoint validates all parameters against Pydantic bounds before applying (T-508)
- API error responses do not leak internal details for trading endpoints (T-508-FIX1)

## [0.4.8] - 2026-03-05

### Added
- React + Vite + Tailwind + shadcn/ui client foundation (`client/`) — sidebar nav, API layer, health dashboard with auto-refresh, error boundary (T-401)
- UAT test API endpoints (`src/uat/`) — 28 behavioral tests across 7 suites (Data Pipeline, Event Detection, Bayesian, ML Training, Regime, Ensemble, End-to-End) with synthetic data (T-402)
- UAT Runner UI (`client/src/pages/UATPage.tsx`) — suite cards, Run All/Run Suite, results table with expandable details, re-run individual tests, loading states (T-403)
- Interactive admin panels (`client/src/pages/AdminPage.tsx`) — Feature Explorer (compute + load + pivoted table), Signal Inspector (generator selection + signal card + component scores + metadata), Regime Monitor (auto-load both instruments), Model Dashboard (version history + expandable details) (T-404)
- Practical UAT.md test plan — human-verifiable items mapped to automated tests and interactive panels across 7 sections (T-405)
- DEC-015 decision record for client UI stack (React 18 + TypeScript + Vite + Tailwind + shadcn/ui) (T-401)
- API endpoints for regime detection (`/api/v1/regime/{instrument}`), model listing (`/api/v1/models/{instrument}`), and feature computation (`POST /api/v1/features/compute`) (T-404)
- Instrument validation on all data endpoints (`get_ohlcv`, `get_features`, `compute_features`) with 400 on unsupported instruments (T-405-FIX1)
- `model_type` query parameter validation against allowed list with 400 on invalid (T-405-FIX1)
- Row limit (50,000) on `compute_features` OHLCV query to prevent memory exhaustion (T-405-FIX1)
- Regime computation try/except with `_unknown_regime` fallback on ValueError/ZeroDivisionError (T-405-FIX1)
- 12 new tests for API validation and error handling paths (T-405-FIX1, T-405-FIX2)
- 216 new tests (225 → 441), coverage 89% → 93%

### Changed
- `app.py` reads version dynamically from `VERSION` file instead of hardcoded `"0.1.0"` (T-405-FIX2)
- Client `ohlcv()` function now requires `interval` and `start` params matching server contract (T-405-FIX2)
- Regime rolling vol step comment corrected from "20 trading days" to "~20 bars" (T-405-FIX2)
- `dark` class added to `<html>` element for shadcn/ui dark mode variant activation (T-405-FIX2)
- React Fragment with key replaces bare `<>` in ModelDashboard list rendering (T-405-FIX2)

### Fixed
- HTTP 500 error messages no longer leak exception details (connection strings, SQL fragments) — all 4 data.py endpoints use generic messages with server-side logging (T-405-FIX1)

### Security
- API error response sanitization — database exceptions no longer exposed to clients per SPEC §7.3 and §10.1 (T-405-FIX1)
- Defense-in-depth input validation at API boundary for `model_type` and `instrument` parameters (T-405-FIX1)

## [0.3.10] - 2026-03-04

### Added
- Feature engineering pipeline (`src/analysis/feature_engineering.py`) — OHLCV return features, indicator lag features, token presence flags with configurable lookback window (T-301)
- Model artifact storage and versioning (`src/analysis/model_store.py`) — save/load with SHA-256 integrity verification, version tracking per instrument/model_type (T-302)
- Walk-forward training framework (`src/analysis/walk_forward.py`) — rolling window cross-validation with configurable train/test/step sizes, 48-hour embargo, minimum 4 folds, OOF prediction collection (T-303)
- XGBoost model training (`src/analysis/xgboost_trainer.py`) — walk-forward training with Optuna hyperparameter optimization, early stopping, AUC-ROC evaluation (T-304)
- Regime detection subsystem (`src/regime/detector.py`) — `vol_30d` annualized realized volatility, `ADX_14`, 4-regime classification, deterministic confidence formula with HIGH/MEDIUM/LOW bands (T-305)
- Meta-learner (`src/analysis/meta_learner.py`) — logistic regression stacking of Bayesian posterior, ML probability, and regime confidence with decile calibration evaluation (T-306)
- Path sanitization in model store — regex validation `^[A-Za-z0-9_-]+$` for instrument and model_type to prevent directory traversal (T-306-FIX3)
- XGBoost booster deserialization cache via `functools.lru_cache` to avoid redundant per-call deserialization (T-306-FIX3)
- 172 new tests (225 → 397), coverage 89% → 92%

### Changed
- `MLV1Generator` rewritten from scaffold to real XGBoost inference: load model → feature vector → predict → Signal (T-304)
- `EnsembleV1Generator` rewritten to use meta-learner stacking with fallback to weighted blend when untrained (T-306)
- Feature engineering uses `NaN` for missing indicator/return values instead of `0.0` — XGBoost handles NaN natively (T-306-FIX1)
- `train_meta_learner()` evaluates calibration on held-out 20% split instead of training data (T-306-FIX2)
- `MLV1Generator.validate_config()` and `EnsembleV1Generator.validate_config()` now check required parameter keys (T-306-FIX2)

### Fixed
- `compute_vol_30d()` now raises `ValueError` for non-positive prices (log undefined) (T-306-FIX1)
- `train_xgboost()` returns `None` for `production_model_bytes` when AUC below threshold per SPEC §5.6 (T-306-FIX2)
- Calibration metric was evaluated on training data instead of held-out split (T-306-FIX2)
- `validate_config()` base implementations always returned `True` without checking required keys (T-306-FIX2)

### Security
- Model store path traversal prevention — rejects `../`, slashes, and special characters in instrument/model_type names (T-306-FIX3)

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
