# Newton User Acceptance Tests

This file tracks user acceptance tests cumulatively across all stages. Tests are added as tasks are completed and reviewed at each stage gate.

**Instructions for testers:**
- Work through each test in order
- Check the box when the test passes
- Add notes for any issues, unexpected behavior, or observations
- If a test fails, describe the actual behavior in the Notes column
- Tests from previous stages should be re-verified to catch regressions

---

<!--
Stage sections are added as stages are completed.
Each section contains tests derived from the stage's task acceptance criteria.
Format: checkbox | test description | notes
-->

## Stage 1: Remediation & Hardening

| Pass | Test | Notes |
|------|------|-------|
| [ ] | Run `pytest -q` — coverage report appears automatically showing per-module coverage and >=80% global | |
| [ ] | Run `pytest --cov=src --cov-report=term-missing -q` — same result as bare `pytest -q` (addopts wired) | |
| [ ] | `GET /api/v1/signals/EUR_USD` response includes `"scaffold": true` at top level | |
| [ ] | `GET /api/v1/signals/EUR_USD` response includes `"warning"` string mentioning scaffold | |
| [ ] | `GET /api/v1/signals/generators` response includes `"scaffold": true` at top level | |
| [ ] | `client/src/main.js` does not exist (stale entry point removed) | |
| [ ] | `client/src/main.tsx` still exists (scaffold entry point retained) | |
| [ ] | `DECISIONS.md` contains DEC-012 deferring Dockerfile to Stage 7 | |
| [ ] | `Dockerfile` still contains stub placeholder (unchanged) | |
| [ ] | Oanda fetcher URL validation accepts configured `base_url` (e.g., live `api-fxtrade.oanda.com`) without ValueError | |
| [ ] | Binance fetcher URL validation accepts configured `base_url` (e.g., testnet `testnet.binance.vision`) without ValueError | |
| [ ] | Health check database failures are logged (not silently swallowed) — check logs when DB is unavailable | |

## Stage 2: Event Detection & Tokenization

| Pass | Test | Notes |
|------|------|-------|
| [ ] | `from src.analysis.events import label_events, EventLabel` imports without error | |
| [ ] | `label_events()` with synthetic candles returns `EventLabel` objects with `event_type`, `time`, `label` fields | |
| [ ] | `from src.analysis.tokenizer import tokenize, load_classifications, TokenSet` imports without error | |
| [ ] | `load_classifications("config/classifications/EUR_USD_classifications.json")` returns 22 rules | |
| [ ] | `load_classifications("config/classifications/BTC_USD_classifications.json")` returns 22 rules | |
| [ ] | `tokenize()` returns `TokenSet` with `frozenset` of active tokens matching classification rules | |
| [ ] | `from src.analysis.token_selection import select_tokens, compute_mutual_information` imports without error | |
| [ ] | `compute_mutual_information()` returns `TokenScore` list sorted descending by MI score | |
| [ ] | `select_tokens()` returns `SelectedTokenSet` with tokens ranked by MI and redundant tokens dropped | |
| [ ] | `select_tokens()` with `top_n=100` caps at 50 tokens (SPEC §5.4 max) | |
| [ ] | `select_tokens()` logs selected token set info at INFO level | |
| [ ] | `from src.analysis.bayesian import train, predict, BayesianModel` imports without error | |
| [ ] | `train()` with synthetic token sets and event labels returns `BayesianModel` with `prior`, `likelihoods`, `calibration_x`, `calibration_y` fields | |
| [ ] | `BayesianModel.likelihoods` contains `TokenLikelihood` entries with Laplace-smoothed `p_given_event` and `p_given_no_event` | |
| [ ] | `predict()` with no active tokens returns posterior approximately equal to prior | |
| [ ] | `predict()` with informative token returns posterior higher than prior (for event-correlated token) | |
| [ ] | `predict()` result never exceeds `posterior_cap` (default 0.90) even with very strong evidence | |
| [ ] | `train()` with `laplace_alpha=5` produces likelihoods closer to 0.5 than `laplace_alpha=1` | |
| [ ] | `compute_phi_coefficient()` returns 1.0 for identical token activation patterns | |
| [ ] | `check_correlations()` logs WARNING when `|phi| > 0.7` between any token pair | |
| [ ] | `check_correlations()` logs ALERT recommending token set reduction when >3 pairs exceed threshold | |
| [ ] | `BayesianV1Generator` with model and rules in config uses tokenize → predict path (not scaffold fallback) | |
| [ ] | `BayesianV1Generator` without model in config falls back to `features.values["score"]` scaffold behavior | |
| [ ] | `BayesianV1Generator.generate()` with informative tokens returns posterior > prior | |
| [ ] | `BayesianV1Generator.generate()` metadata contains `"source": "bayesian_engine"` when model is provided | |
| [ ] | `BayesianV1Generator.generate_batch()` returns signals for all snapshots with correct timestamps | |
| [ ] | End-to-end: train model → tokenize features → predict → Signal produces valid probabilities | |
| [ ] | `config/feature_providers.json` class path is `src.data.indicators.TechnicalIndicatorProvider` (not `newton.`) | |
| [ ] | `DECISIONS.md` contains DEC-013 documenting FeatureProvider sync batch signature | |
| [ ] | `verify_candles([])` returns clean result with zero counts and no issues | |
| [ ] | `verify_candles()` with zero-volume candles passes OHLC integrity (volume is not an OHLC field) | |
| [ ] | Indicator provider handles zero-volume candles without error (OBV stays at 0) | |
| [ ] | Indicator provider handles zero-range candles (open==high==low==close) without error (ATR=0) | |
| [ ] | `BayesianV1Generator.generate()` raises `RecoverableSignalError` when `_close` is missing from features and model+rules are present | |
| [ ] | `BayesianV1Generator.generate()` without model/rules (scaffold path) does not require `_close` in features | |
| [ ] | `SignalRouter.route_signal()` with `generator_override` uses instrument-specific thresholds (not defaults) | |
| [ ] | `generate_batch()` with thresholds in `config.parameters` uses those thresholds for action computation | |
| [ ] | `generate_batch()` without thresholds in `config.parameters` uses default thresholds (backward compatible) | |
| [ ] | `DECISIONS.md` contains DEC-014 documenting event labeling high-watermark approach | |

## Stage 3: ML Pipeline

### T-301: Feature Engineering Pipeline

| Status | Test | Notes |
|--------|------|-------|
| [ ] | `build_feature_matrix()` produces a matrix with OHLCV return columns (`ohlcv:*:lag=N`), indicator columns (`ind:*:lag=N`), and token flag columns (`tok:*`) | |
| [ ] | OHLCV returns use period-over-period returns (not raw prices) — verified against hand-calculated values | |
| [ ] | Lookback window is configurable and defaults to 24 (from strategy `ml_model.lookback_periods`) | |
| [ ] | Token presence flags are binary (0.0 or 1.0) and reflect current-period token activation | |
| [ ] | `build_feature_vector()` for a given timestamp produces the same values as the corresponding row in `build_feature_matrix()` | |
| [ ] | Insufficient history for lookback window produces empty matrix (training) or raises ValueError (inference) | |
| [ ] | Zero-volume candles handled safely (no division-by-zero errors) | |

### T-302: Model Artifact Storage and Versioning

| Status | Test | Notes |
|--------|------|-------|
| [ ] | `save_model()` writes model file and `.meta.json` sidecar to `{base_dir}/{instrument}/{model_type}/v{N}.model` | |
| [ ] | `save_model()` computes SHA-256 hash of model bytes and stores it in metadata | |
| [ ] | `load_model()` round-trips: saved bytes and metadata match loaded bytes and metadata | |
| [ ] | `load_model()` with corrupted model file raises `ModelIntegrityError` (hash mismatch) | |
| [ ] | `load_model()` with `version=None` loads the latest version | |
| [ ] | `load_model()` for missing model file raises `FileNotFoundError` | |
| [ ] | `get_latest_version()` returns 0 when no versions exist | |
| [ ] | `get_latest_version()` returns highest version number after multiple saves | |
| [ ] | `list_versions()` returns all version metadata sorted ascending by version | |
| [ ] | `ModelArtifact` is frozen (attribute assignment raises `AttributeError`) | |

### T-303: Walk-Forward Training Framework

| Status | Test | Notes |
|--------|------|-------|
| [ ] | `generate_folds()` produces at least `min_folds` folds with correct train/test boundaries | |
| [ ] | Embargo gap between train_end and test_start equals `embargo_periods` for every fold | |
| [ ] | Each fold's train_start advances by `step_periods` (rolling window) | |
| [ ] | Consecutive test sets are non-overlapping | |
| [ ] | All fold indices are within `[0, n_samples)` bounds | |
| [ ] | `generate_folds()` with insufficient data raises `ValueError` | |
| [ ] | `validate_no_lookahead()` passes for well-formed folds and raises `ValueError` for violations | |
| [ ] | `collect_results()` concatenates OOF predictions, labels, and timestamps from all folds | |
| [ ] | `collect_results()` computes mean AUC-ROC as average of per-fold AUC-ROC values | |
| [ ] | All dataclasses (`WalkForwardConfig`, `WalkForwardFold`, `FoldResult`, `WalkForwardResult`) are frozen | |
