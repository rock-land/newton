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

### T-304: XGBoost Model Training and MLV1Generator

| Status | Test | Notes |
|--------|------|-------|
| [ ] | `train_xgboost()` with synthetic feature matrix returns `TrainingResult` with populated `production_model_bytes` and `production_hyperparameters` | |
| [ ] | Walk-forward folds are populated (≥2 folds, OOF predictions and labels non-empty) | |
| [ ] | `train_xgboost()` with `auc_threshold=0.99` sets `below_auc_threshold=True` | |
| [ ] | `train_xgboost()` with `auc_threshold=0.0` sets `below_auc_threshold=False` | |
| [ ] | Production model from `train_xgboost()` can predict via `predict_xgboost()` — returns probability in [0, 1] | |
| [ ] | All OOF predictions are in [0.0, 1.0] range | |
| [ ] | Optimized hyperparameters are in valid ranges (max_depth 3-10, learning_rate 0.01-0.3, etc.) | |
| [ ] | `predict_xgboost()` round-trip: train model → serialize → predict returns valid probability | |
| [ ] | `predict_xgboost()` with different inputs produces different probabilities | |
| [ ] | `MLV1Generator` with `model_bytes` and `feature_names` in config uses real XGBoost inference (`metadata.source = "xgboost_engine"`) | |
| [ ] | `MLV1Generator` without model in config falls back to scaffold behavior (`metadata.source = "scaffold"`) | |
| [ ] | `MLV1Generator` with model but missing feature in `features.values` raises `RecoverableSignalError` | |
| [ ] | `MLV1Generator.generate_batch()` with model returns signals with `source: "xgboost_engine"` for all snapshots | |
| [ ] | `XGBoostHyperparameters` and `TrainingResult` dataclasses are frozen | |
| [ ] | Training is reproducible with the same `random_seed` | |

### T-305: Regime Detection Subsystem

| Status | Test | Notes |
|--------|------|-------|
| [ ] | `RegimeLabel` enum has exactly 4 values: `LOW_VOL_TRENDING`, `LOW_VOL_RANGING`, `HIGH_VOL_TRENDING`, `HIGH_VOL_RANGING` | |
| [ ] | `ConfidenceBand` enum has exactly 3 values: `HIGH`, `MEDIUM`, `LOW` | |
| [ ] | `RegimeState` is frozen (attribute assignment raises `AttributeError`) | |
| [ ] | `compute_vol_30d()` with constant prices returns 0.0 | |
| [ ] | `compute_vol_30d()` with forex annualization (√252) produces lower vol than crypto (√365) for same returns | |
| [ ] | `compute_vol_30d()` with fewer than 2 closes raises `ValueError` | |
| [ ] | `compute_adx_14()` with strong trending data returns ADX > 25 | |
| [ ] | `compute_adx_14()` with ranging/oscillating data returns ADX < 25 | |
| [ ] | `compute_adx_14()` with fewer than 28 bars raises `ValueError` | |
| [ ] | `compute_adx_14()` returns value in [0, 100] range | |
| [ ] | `compute_vol_median()` returns correct median of input series | |
| [ ] | `compute_vol_median()` with empty list raises `ValueError` | |
| [ ] | `classify_regime()` returns `LOW_VOL_TRENDING` when vol_30d < vol_median AND ADX > 25 | |
| [ ] | `classify_regime()` returns `HIGH_VOL_RANGING` when vol_30d ≥ vol_median AND ADX ≤ 25 | |
| [ ] | `classify_regime()` boundary: vol_30d == vol_median classifies as HIGH_VOL (≥ condition) | |
| [ ] | `classify_regime()` boundary: ADX == 25 classifies as RANGING (≤ condition) | |
| [ ] | `compute_confidence()` matches SPEC §5.8.3 formula: `sqrt(clamp(d_vol) × clamp(d_adx))` | |
| [ ] | `compute_confidence()` with vol_median=0 returns (0.0, LOW) — no division-by-zero crash | |
| [ ] | Confidence ≥ 0.5 → HIGH band; 0.2–0.5 → MEDIUM band; < 0.2 → LOW band | |
| [ ] | `detect_regime()` end-to-end with trending candle data returns `RegimeState` with ADX > 25 | |
| [ ] | `detect_regime()` end-to-end with ranging candle data returns valid `RegimeState` | |
| [ ] | Pure Python ADX fallback produces results in the same ballpark as TA-Lib ADX | |

### T-306: Meta-Learner and EnsembleV1Generator

| Status | Test | Notes |
|--------|------|-------|
| [ ] | `MetaLearnerModel` is frozen (attribute assignment raises `AttributeError`) | |
| [ ] | `MetaLearnerModel` has fields: `coefficients`, `intercept`, `feature_names`, `calibration_errors`, `n_training_samples` | |
| [ ] | `train_meta_learner()` with separable synthetic data returns `MetaLearnerModel` with 3 coefficients | |
| [ ] | `train_meta_learner()` bayesian and ML coefficients are positive (informative inputs) | |
| [ ] | `train_meta_learner()` with fewer than `min_samples` raises `ValueError` | |
| [ ] | `train_meta_learner()` default `min_samples` is 100 — 99 samples raises `ValueError` | |
| [ ] | `train_meta_learner()` with exactly 100 samples succeeds | |
| [ ] | `predict_meta_learner()` returns probability in [0, 1] | |
| [ ] | `predict_meta_learner()` with high bayesian+ml inputs returns higher probability than low inputs | |
| [ ] | `predict_meta_learner()` with different inputs produces different outputs | |
| [ ] | `predict_meta_learner()` with all-zero inputs returns valid probability in [0, 1] | |
| [ ] | `predict_meta_learner()` with all-one inputs returns valid probability in [0, 1] | |
| [ ] | `compute_calibration_error()` returns 10-element tuple (one per decile) | |
| [ ] | `compute_calibration_error()` with well-calibrated data returns errors < 0.10 per decile | |
| [ ] | `compute_calibration_error()` with poorly calibrated data (predict 0.95, observe 50%) returns high error in 0.9-1.0 bin | |
| [ ] | `compute_calibration_error()` empty bins get 0.0 error | |
| [ ] | `check_calibration()` returns True when all decile errors < 5pp | |
| [ ] | `check_calibration()` returns False when any decile error ≥ 5pp | |
| [ ] | `check_calibration()` with error exactly at 5pp (0.05) returns False (strict < threshold) | |
| [ ] | `check_calibration()` with custom `max_error_pp` threshold works correctly | |
| [ ] | `EnsembleV1Generator` with `meta_learner_model` in config uses meta-learner path (`metadata.source = "meta_learner"`) | |
| [ ] | `EnsembleV1Generator` without `meta_learner_model` in config falls back to weighted blend (`metadata.source = "weighted_blend"`) | |
| [ ] | `EnsembleV1Generator` with meta-learner: high bayesian+ml inputs produce higher probability than low inputs | |
| [ ] | `EnsembleV1Generator.generate_batch()` with meta-learner model returns all signals with `source: "meta_learner"` | |
| [ ] | `EnsembleV1Generator` with meta-learner but missing `regime_confidence` feature raises `RecoverableSignalError` | |
| [ ] | End-to-end: train meta-learner → predict → EnsembleV1Generator produces valid signal with calibrated probability | |

### T-306-FIX1/FIX2/FIX3: Remediation Fixes

| Status | Test | Notes |
|--------|------|-------|
| [ ] | `compute_vol_30d()` with zero price in closes raises `ValueError` (non-positive guard) | |
| [ ] | `compute_vol_30d()` with negative price in closes raises `ValueError` | |
| [ ] | Missing indicator values in feature matrix produce `NaN` (not `0.0`) — XGBoost handles natively | |
| [ ] | Missing OHLCV return values in feature vector produce `NaN` (not `0.0`) | |
| [ ] | `train_xgboost()` with `auc_threshold=0.99` returns `production_model_bytes=None` (ML disabled per SPEC §5.6) | |
| [ ] | `train_xgboost()` with `auc_threshold=0.0` returns `production_model_bytes` with data (ML enabled) | |
| [ ] | `MLV1Generator.validate_config()` returns `True` for valid config (both `model_bytes` and `feature_names`) | |
| [ ] | `MLV1Generator.validate_config()` returns `False` for partial config (`model_bytes` without `feature_names`) | |
| [ ] | `EnsembleV1Generator.validate_config()` returns `False` for invalid weights (single-element list) | |
| [ ] | `train_meta_learner()` `n_training_samples` is 80% of input (train/held-out split for calibration) | |
| [ ] | `predict_xgboost()` caches deserialized booster — second call with same bytes reuses object | |
| [ ] | `model_store` rejects path traversal in instrument name (`../etc` raises `ValueError`) | |
| [ ] | `model_store` rejects path traversal in model_type (`../../passwd` raises `ValueError`) | |
| [ ] | `model_store` rejects slash in instrument name (`foo/bar` raises `ValueError`) | |
