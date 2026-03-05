# Stage 3: ML Pipeline

## Code Review

- **Date:** 2026-03-04
- **Scope:** Full Stage 3 — T-301 through T-306 (feature engineering, model store, walk-forward, XGBoost, regime detection, meta-learner, EnsembleV1Generator rewrite)

### Findings

#### Critical
_None._

#### Warning
_None._

#### Note
- [N-1] **src/analysis/meta_learner.py:80** Calibration error is computed on the same OOF data used to train the logistic regression. With only 4 parameters (3 coefficients + 1 intercept), overfitting risk is minimal, but a held-out evaluation split would be more rigorous. Acceptable for v1 given the low-parameter model.
- [N-2] **src/analysis/meta_learner.py:64** `train_meta_learner()` does not validate that all input tuples (`bayesian_posteriors`, `ml_probabilities`, `regime_confidences`, `labels`) have equal length. Length mismatch would cause a numpy error at `column_stack`, but an early explicit check would give a clearer error message.
- [N-3] **src/regime/detector.py:271-344** Pure Python ADX fallback parity test allows 30-point tolerance (`abs(talib_adx - python_adx) < 30`). This is generous — ADX ranges 0–100, so a 30-point difference could cross the 25 threshold. The test does verify both agree on trending vs ranging direction for synthetic data, which mitigates practical impact. Per DEC-006, parity tests are required; the tolerance is documented.
- [N-4] **src/analysis/model_store.py:67** `_deserialize_artifact()` uses `.replace(tzinfo=UTC)` which silently overrides any existing timezone info rather than converting. Since all timestamps are serialized from UTC, this round-trips correctly. Would be slightly more robust as `datetime.fromisoformat(...).astimezone(UTC)` but no practical impact.

### Spec Compliance Assessment

| Module | SPEC Section | Status | Notes |
|--------|-------------|--------|-------|
| feature_engineering.py | §5.6 | PASS | OHLCV returns (not raw prices), configurable lookback, token flags |
| model_store.py | — | PASS | SHA-256 integrity, versioning, frozen dataclass |
| walk_forward.py | §5.6, §9.1 | PASS | Rolling window, embargo, min folds, OOF collection |
| xgboost_trainer.py | §5.6 | PASS | Optuna HPO, early stopping, AUC threshold, production model |
| detector.py | §5.8 | PASS | vol_30d, ADX_14, 4 labels, confidence formula, bands |
| meta_learner.py | §5.7, §9.5 | PASS | Logistic regression stacking, 3 inputs, 5pp calibration |
| signal.py (Ensemble) | §5.7 | PASS | Meta-learner path + weighted blend fallback |

### Pattern Compliance

- All domain models frozen (DEC-010): `FeatureMatrix`, `FeatureVector`, `ModelArtifact`, `WalkForwardConfig`, `WalkForwardFold`, `FoldResult`, `WalkForwardResult`, `XGBoostHyperparameters`, `TrainingResult`, `RegimeState`, `MetaLearnerModel` ✓
- TA-Lib with pure Python fallback (DEC-006): ADX computation ✓
- Protocol abstractions (DEC-005): Generators satisfy `SignalGenerator` protocol ✓
- Registry + fallback chains (DEC-011): EnsembleV1Generator registered, supports fallback ✓
- Config-driven design: lookback periods, thresholds, min_samples all configurable ✓

### Security
- No SQL queries in Stage 3 modules (pure computation) ✓
- No subprocess calls ✓
- No hardcoded secrets ✓
- sklearn/XGBoost/Optuna used as established libraries ✓

### Test Coverage
- 377 tests, 91% global coverage
- Stage 3 module coverage: feature_engineering 100%, model_store 100%, walk_forward 99%, xgboost_trainer 96%, detector 96%, meta_learner 100%, signal.py 97%
- Edge cases covered: empty data, zero volume, insufficient history, missing features, threshold boundaries, frozen dataclass mutation
- Tests use specific assertions (not just `is not None`)
- XGBoost tests verify train→serialize→predict round-trip
- Meta-learner tests verify coefficient signs, boundary conditions, calibration logic

### Quality Gate
- lint: PASS
- types: PASS
- tests: PASS — 377 passed, coverage 91%

### Verdict
Ready for merge. No critical or warning findings. All SPEC acceptance criteria are met. The four notes are informational improvements that don't block the stage gate.

## Red Team Review

- **Date:** 2026-03-04
- **Reviewer:** Adversarial Subagent (fresh context)
- **Scope:** Stage 3 — ML Pipeline (T-301 through T-306)

### Quality Gate
- lint: PASS
- types: PASS
- tests: PASS — 377 passed, coverage 91%

### Critical
- [RC-1] **src/regime/detector.py:116** `np.log()` on close prices with no guard against zero or negative values — silent NaN propagation through vol_30d → regime classification → position sizing
- [RC-2] **src/analysis/feature_engineering.py:132,139** Missing indicator values silently default to 0.0 instead of NaN — XGBoost treats NaN as missing (correct), but 0.0 creates spurious correlations in training data

### High
- [RH-1] **src/analysis/xgboost_trainer.py:137-145** AUC below threshold only logs warning; SPEC §5.6 requires disabling ML component and falling back to Bayesian-only — task acceptance criteria weaker than spec
- [RH-2] **src/analysis/xgboost_trainer.py:179** XGBoost model deserialized on every `predict_xgboost()` call — ~3.5x overhead in batch/backtest scenarios (26,000 deserializations per backtest)
- [RH-3] **src/analysis/model_store.py:46** No path sanitization on `instrument`/`model_type` parameters — latent path traversal if exposed to user input in future stages
- [RH-4] **src/analysis/meta_learner.py:79-83** Calibration evaluated on training data, not held-out data — SPEC §1.5/§9.5 requires "predicted vs. observed ±5pp per decile" which implies out-of-sample evaluation
- [RH-5] **src/trading/signal.py:71-72** `validate_config` always returns True (isinstance check on dict) — misconfigured generators silently fall to scaffold path

### Medium
- [RM-1] **src/trading/signal.py:32-56** GeneratorRegistry uses instance methods; SPEC §5.2.2 specifies `@classmethod`
- [RM-2] **src/analysis/feature_engineering.py:61** `_safe_ret` function redefined inside loop body on every iteration — unnecessary overhead for large datasets
- [RM-3] **src/regime/detector.py:308-313** Wilder's smoothing docstring says "SMA" but computes a sum — misleading documentation (code is correct)
- [RM-4] **src/analysis/walk_forward.py** No validation that `step_periods` avoids test window overlap — OOF predictions could duplicate timestamps
- [RM-5] **src/analysis/xgboost_trainer.py:246** `n_estimators` hardcoded to 300 in HPO output — misleading when inspected (production model uses median best_iteration)
- [RM-6] **src/trading/signal.py:59-61** `_BaseGenerator` inheritance pattern diverges from DEC-005 (Protocol over inheritance)

### Low
- [RL-1] **tests/unit/test_regime_detector.py:381** ADX parity test tolerance of 30 is overly generous (should be ~0.01)
- [RL-2] **src/analysis/model_store.py:67** `.replace(tzinfo=UTC)` may silently override non-UTC timezone
- [RL-3] **src/analysis/meta_learner.py:73** LogisticRegression regularization (C=1.0) is implicit, not documented
- [RL-4] **src/analysis/xgboost_trainer.py:62-71** `train_xgboost` has many parameters; consider grouping into config dataclass
- [RL-5] **src/analysis/walk_forward.py:19** Missing blank line between import block and logger assignment

### Test Gaps
- [TG-1] **detector.py:compute_vol_30d** No test for zero or negative close prices
- [TG-2] **feature_engineering.py** No test for missing indicator keys at specific timestamps
- [TG-3] **xgboost_trainer.py** No test for constant labels (all 0 or all 1)
- [TG-4] **model_store.py** No test for concurrent save/load operations
- [TG-5] **meta_learner.py** No test for out-of-sample calibration
- [TG-6] **signal.py:EnsembleV1Generator** No test for meta-learner with extreme input values (0.0, 1.0)
- [TG-7] **xgboost_trainer.py** No test for NaN/Inf in feature matrix
- [TG-8] **detector.py:detect_regime** No test for vol_median very close to zero (but not exactly zero)

### Positive Observations
- All 11 domain models use `@dataclass(frozen=True)` — thoroughly tested
- No bare `except:` or silenced exceptions anywhere in Stage 3
- No security anti-patterns (eval, exec, os.system, SQL interpolation)
- Walk-forward framework is well-designed with clean separation of concerns
- Pure Python ADX fallback has near-perfect parity with TA-Lib
- Excellent test coverage (91% global, 96-100% on Stage 3 modules)
- SHA-256 integrity verification on model load
- Numerically stable sigmoid in meta-learner
- Configuration matches SPEC §5.1 exactly
- Deterministic regime confidence formula matches SPEC §5.8.3

### Verdict
CONDITIONAL PASS — Two critical findings (RC-1, RC-2) should be addressed. Five high findings should be addressed or deferred with decision records. Overall architecture is solid, test coverage is strong, and core ML pipeline design is sound.

## Stage Report

- **Date:** 2026-03-04
- **Status:** APPROVED
- **Sign-off:** 2026-03-04

### Quality Gate Summary
- lint: PASS
- types: PASS
- tests: PASS — 377 passed, coverage 91%

### Unified Findings

#### Critical (must fix)

- [SR-C1] **src/regime/detector.py:116** `np.log()` on close prices without guard against zero or negative values — source: Red Team RC-1
  - **Impact:** Silent NaN propagation through vol_30d → regime classification → confidence bands → position sizing. A single zero price from data corruption or edge case produces NaN that flows undetected through the entire regime subsystem.
  - **Remediation:** Add `if np.any(window <= 0): raise ValueError(...)` before `np.log(window)`. Add test for zero/negative close prices.

- [SR-C2] **src/analysis/feature_engineering.py:132,139** Missing indicator values silently default to 0.0 instead of NaN — source: Red Team RC-2
  - **Impact:** XGBoost treats NaN as "missing" (correct behavior with native handling) but treats 0.0 as a real value. Substituting 0.0 for missing indicators (RSI ~50, OBV ~10000+) creates a spurious correlation that the model learns from, degrading out-of-sample performance with potentially incorrect trading signals.
  - **Remediation:** Use `float('nan')` as default for missing indicator and return values. Add test for missing indicator keys at specific timestamps.

#### High (should fix)

- [SR-H1] **src/analysis/xgboost_trainer.py:137-145** AUC below threshold only logs warning; SPEC §5.6 requires disabling ML component — source: Red Team RH-1
  - **Impact:** A below-threshold model (AUC < 0.55, worse than random) could be deployed if the caller doesn't check `below_auc_threshold`. SPEC mandates falling back to Bayesian-only mode.
  - **Remediation:** Set `production_model_bytes` to `None` when below threshold, or add explicit guard in MLV1Generator to refuse models flagged as below-threshold.

- [SR-H2] **src/analysis/xgboost_trainer.py:179** XGBoost model deserialized on every `predict_xgboost()` call — source: Red Team RH-2
  - **Impact:** ~3.5x overhead in batch/backtest scenarios. For 3 years of hourly data (~26,000 candles), wastes ~14 seconds on redundant deserialization per backtest run.
  - **Remediation:** Cache deserialized Booster (e.g., accept pre-deserialized model, or use `functools.lru_cache` keyed on model bytes identity).

- [SR-H3] **src/analysis/model_store.py:46** No path sanitization on `instrument`/`model_type` parameters — source: Red Team RH-3
  - **Impact:** Latent path traversal vulnerability. Not exploitable today but becomes a risk if model management API endpoints are added in Stage 4+.
  - **Remediation:** Validate parameters against regex `^[A-Za-z0-9_]+$` and raise ValueError on invalid input.

- [SR-H4] **src/analysis/meta_learner.py:79-83** Calibration evaluated on training data, not held-out data — source: Red Team RH-4, Code Review N-1
  - **Impact:** In-sample calibration may underestimate true error. SPEC §1.5/§9.5 requires "predicted vs. observed ±5pp per decile" which implies out-of-sample evaluation.
  - **Remediation:** Use cross-validation within `train_meta_learner()` or hold out a portion of data for calibration evaluation.

- [SR-H5] **src/trading/signal.py:71-72** `validate_config` always returns True — source: Red Team RH-5
  - **Impact:** Misconfigured generators (e.g., missing model_bytes) silently fall to scaffold behavior, producing incorrect signals without warning.
  - **Remediation:** Each generator's `validate_config` should check for required parameters (e.g., MLV1: model_bytes + feature_names; Ensemble: meta_learner_model or weights).

#### Medium (recommend)

- [SR-M1] **src/trading/signal.py:32-56** GeneratorRegistry uses instance methods; SPEC §5.2.2 specifies `@classmethod` — source: Red Team RM-1
- [SR-M2] **src/analysis/feature_engineering.py:61** `_safe_ret` redefined inside loop body on every iteration — source: Red Team RM-2
- [SR-M3] **src/regime/detector.py:308-313** Wilder's smoothing docstring says "SMA" but computes a sum — source: Red Team RM-3
- [SR-M4] **src/analysis/walk_forward.py** No validation that `step_periods` avoids test window overlap — source: Red Team RM-4
- [SR-M5] **src/analysis/xgboost_trainer.py:246** `n_estimators` hardcoded to 300 in HPO output — source: Red Team RM-5
- [SR-M6] **src/trading/signal.py:59-61** `_BaseGenerator` inheritance diverges from DEC-005 — source: Red Team RM-6

#### Low (noted)

- [SR-L1] **tests/unit/test_regime_detector.py:381** ADX parity test tolerance of 30 is overly generous — source: Red Team RL-1, Code Review N-3
- [SR-L2] **src/analysis/model_store.py:67** `.replace(tzinfo=UTC)` may silently override non-UTC timezone — source: Red Team RL-2, Code Review N-4
- [SR-L3] **src/analysis/meta_learner.py:73** LogisticRegression regularization implicit — source: Red Team RL-3
- [SR-L4] **src/analysis/meta_learner.py:64** Input tuple length not validated — source: Code Review N-2
- [SR-L5] **src/analysis/walk_forward.py:19** Missing blank line between imports and logger — source: Red Team RL-5

### Test Gap Summary

- [SR-TG1] **detector.py:compute_vol_30d** No test for zero or negative close prices — source: Red Team TG-1
- [SR-TG2] **feature_engineering.py** No test for missing indicator keys at specific timestamps — source: Red Team TG-2
- [SR-TG3] **xgboost_trainer.py** No test for constant labels (all 0 or all 1) — source: Red Team TG-3
- [SR-TG4] **model_store.py** No test for concurrent save/load operations — source: Red Team TG-4
- [SR-TG5] **meta_learner.py** No test for out-of-sample calibration — source: Red Team TG-5
- [SR-TG6] **signal.py:EnsembleV1Generator** No test for meta-learner with extreme inputs (0.0, 1.0) — source: Red Team TG-6
- [SR-TG7] **xgboost_trainer.py** No test for NaN/Inf in feature matrix — source: Red Team TG-7
- [SR-TG8] **detector.py:detect_regime** No test for vol_median very close to zero — source: Red Team TG-8

### Contradictions Between Reviews

The code review found no critical or warning findings ("Ready for merge"), while the red team found 2 critical and 5 high findings ("Conditional Pass"). This is expected — the code review focused on spec compliance and pattern consistency (which are strong), while the adversarial review probed edge cases, production resilience, and latent risks that only surface under unusual inputs or future API exposure. The red team's findings are well-substantiated and do not contradict the code review's positive assessments.

### User Interview Notes

- **Criticals confirmed:** User agrees both RC-1 and RC-2 are valid criticals that should be fixed before the stage gate.
- **All highs to be fixed:** User wants all 5 high findings addressed before the gate (no deferrals).
- **No manual testing:** Automated test suite is the only validation so far. Manual testing will be discussed at stage completion.
- **No additional concerns:** No known technical debt or issues beyond the review findings.

### Positive Observations

- All 11 domain models use `@dataclass(frozen=True)` per DEC-010 — thoroughly tested
- No bare `except:` or silenced exceptions anywhere in Stage 3 code
- No security anti-patterns (eval, exec, os.system, SQL interpolation, hardcoded secrets)
- Walk-forward framework is well-designed with clean separation of concerns and correct embargo enforcement
- Excellent test coverage: 91% global, 96–100% on all Stage 3 modules
- SHA-256 integrity verification on model load
- Numerically stable sigmoid in meta-learner
- Configuration matches SPEC §5.1 exactly
- Deterministic regime confidence formula matches SPEC §5.8.3
- Pure Python ADX fallback has near-perfect TA-Lib parity

### Remediation Tasks

| ID | Task | Scope | Acceptance | Status |
|---|---|---|---|---|
| T-306-FIX1 | Guard non-positive prices in regime detection and use NaN for missing indicator values | server | `compute_vol_30d()` raises `ValueError` when close prices contain zero or negative values; `_extract_row()` uses `float('nan')` instead of `0.0` for missing indicator/return values; tests for zero/negative closes and missing indicator keys at specific timestamps; quality gate passes | TODO |
| T-306-FIX2 | Enforce AUC threshold, implement validate_config, and evaluate calibration on held-out data | server | `train_xgboost()` returns `production_model_bytes=None` when `below_auc_threshold=True` (or MLV1Generator refuses below-threshold models); each generator's `validate_config` checks for required parameters and returns False when missing; `train_meta_learner()` evaluates calibration on held-out split (not training data); tests for AUC enforcement, config validation rejection, and held-out calibration; quality gate passes | TODO |
| T-306-FIX3 | Cache XGBoost deserialization and add path sanitization to model store | server | `predict_xgboost()` or `MLV1Generator` avoids redundant deserialization in batch scenarios; `model_store` validates `instrument`/`model_type` against `^[A-Za-z0-9_]+$` and raises ValueError on invalid input; tests for caching behavior and path traversal rejection; quality gate passes | TODO |

### Verdict

**NOT READY**

Two critical findings (SR-C1: NaN propagation in regime detection, SR-C2: misleading ML training data) and five high findings require remediation before the stage gate. Three FIX tasks have been added to TASKS.md. The underlying architecture is solid — 91% test coverage, all domain models frozen, strong spec compliance — but these edge cases and spec gaps must be addressed to ensure production-grade reliability for a trading system.

## Fix Verification

- **Date:** 2026-03-04
- **Status:** PASS

### Verified Fixes

| Fix Task | Original Finding | Status | Notes |
|---|---|---|---|
| T-306-FIX1 (SR-C1) | `np.log()` on close prices without guard against zero/negative | **PASS** | `compute_vol_30d()` at `detector.py:114` now checks `np.any(closes <= 0)` and raises `ValueError("non-positive price detected")` before `np.log(window)`. Tests `test_zero_price_raises` and `test_negative_price_raises` confirm both cases. |
| T-306-FIX1 (SR-C2) | Missing indicator values default to 0.0 instead of NaN | **PASS** | `_extract_row()` at `feature_engineering.py:127` uses `_NAN = float("nan")` as default for both `ret.get(field, _NAN)` (line 134) and `ind.get(key, _NAN)` (line 141). Tests `test_missing_indicator_produces_nan` and `test_missing_ohlcv_return_produces_nan` verify NaN propagation. |
| T-306-FIX2 (SR-H1) | AUC below threshold only logs warning; doesn't disable ML | **PASS** | `train_xgboost()` at `xgboost_trainer.py:149` sets `final_model_bytes = None if below else production_bytes`. `TrainingResult.production_model_bytes` typed as `bytes | None`. Test `test_below_auc_threshold_true_returns_none_model` verifies `result.production_model_bytes is None` when AUC < threshold. |
| T-306-FIX2 (SR-H4) | Calibration evaluated on training data, not held-out | **PASS** | `train_meta_learner()` at `meta_learner.py:73-88` splits data 80/20, trains on 80%, evaluates calibration on held-out 20%. `n_training_samples` reflects the train split count. Tests `test_calibration_evaluated_on_held_out_data` (n=500, expects 400 training samples) and `test_basic_training` (n=100, expects 80) confirm. |
| T-306-FIX2 (SR-H5) | `validate_config` always returns True | **PASS** | `MLV1Generator.validate_config()` at `signal.py:160-168` checks `model_bytes` and `feature_names` must appear together (partial config rejected). `EnsembleV1Generator.validate_config()` at `signal.py:243-250` validates `weights` must be a list of length 2. Seven tests in `TestValidateConfig` cover valid, scaffold, partial, and bad-weights cases for all three generators. |
| T-306-FIX3 (SR-H2) | XGBoost model deserialized on every predict call | **PASS** | `predict_xgboost()` at `xgboost_trainer.py:183-185` converts bytearray to bytes for hashability, then calls `_get_booster()` which is decorated with `@functools.lru_cache(maxsize=8)`. Test `test_cached_deserialization` verifies same object identity on second call and cache hits ≥ 1. |
| T-306-FIX3 (SR-H3) | No path sanitization on instrument/model_type | **PASS** | `model_store.py:40-48` defines `_SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")` and `_validate_path_component()`. Called from `_model_dir()` (line 57-58) for both `instrument` and `model_type`. Six tests verify rejection of `../etc`, `../../passwd`, `foo/bar`, `..`, and path traversal on load. |

### Quality Gate
- lint: **PASS** — `ruff check .` all checks passed
- types: **PASS** — `mypy src` no issues in 51 source files
- tests: **PASS** — 397 passed, coverage 92%

### Regression Check
- All 397 tests pass (377 pre-fix + 20 new)
- Coverage improved from 91% to 92%
- No new linting or type errors introduced
- No regressions in regime detection, feature engineering, XGBoost training, meta-learner, model store, or signal routing

### New Issues Found
None — fixes are clean.

### Verdict
**PASS**

All 7 findings (2 critical, 5 high) are fully resolved across 3 FIX tasks. Each fix has targeted test coverage verifying the specific behavior change. No regressions detected. The Stage Report can now be updated to APPROVED.
