# Stage 2: Event Detection & Tokenization

## Code Review

- **Date:** 2026-03-03
- **Scope:** Full Stage 2 — all 6 implementation tasks (T-201 through T-206) on `stage/2-event-detection`

### Stage 1 Deferred Finding Resolution

All findings deferred from Stage 1 to Stage 2 have been addressed:

| Finding | Resolution | Task |
|---------|-----------|------|
| SR-H1 (strict `>` thresholds) | `_action_from_probability` uses strict `>` comparisons per SPEC §5.7 | T-201 |
| SR-H5 (FeatureProvider signature) | DEC-013 recorded documenting sync batch signature rationale | T-206 |
| SR-H6 (feature_providers.json path) | Class path corrected from `newton.data.indicators` to `src.data.indicators` | T-206 |
| SR-M1 (MLV1 inherits Bayesian) | MLV1Generator is now an independent class (no inheritance) per DEC-005 | T-201 |
| SR-M2 (ensemble weights) | Weights validated to sum to 1.0 (±0.01); `RecoverableSignalError` on violation | T-201 |
| SR-M8 (unclamped action) | `_build_signal` clamps probability before computing action | T-201 |
| SR-TG3 (threshold boundary tests) | `TestActionFromProbabilityBoundaries` — 6 tests covering exact-threshold values | T-201 |
| SR-TG4 (edge cases) | Empty candle list, zero-volume candles, zero-range candles tested | T-206 |
| SR-TG5 (registry/signal edges) | Register-after-freeze, unknown generator_id, invalid instrument 404 tested | T-201 |

### Findings

#### Critical

_None._

#### Warning

- [W-1] **src/trading/signal.py:122-131** — `generate_batch()` calls `generate()` per snapshot without passing `previous_features` to the tokenizer. Crossover, rising, and falling classification rules (10 of 22 tokens per instrument) will never activate in batch mode. This is documented as intentional for Stage 2 (sequential context deferred to orchestration layer), but batch-generated signals will be systematically less informative than single-call signals with history. Recommend adding a comment in `generate_batch` documenting this limitation and its target resolution stage.

- [W-2] **src/analysis/bayesian.py:268-303** — K-fold cross-validation in `_out_of_fold_predictions` splits data by index position, not by time. If token sets are not chronologically ordered, fold boundaries may leak future data into training folds. In practice, `_align_data` preserves insertion order from `token_sets`, which typically follows candle timestamps. Adding an explicit sort-by-time before splitting would make this guarantee explicit.

- [W-3] **src/trading/signal.py:87-88** — No runtime type validation on `config.parameters["model"]` and `config.parameters["rules"]`. Since `config.parameters` is `dict[str, Any]`, passing incorrect types (e.g., a dict instead of `BayesianModel`) would produce a confusing `AttributeError` deep inside `predict()`. An `isinstance` guard would improve error diagnostics.

#### Note

- [N-1] **src/trading/signal.py:83-120** — `BayesianV1Generator.generate()` does not log which inference path is taken (Bayesian engine vs scaffold fallback). A debug-level log entry would aid production tracing.

- [N-2] **src/analysis/bayesian.py:393** — `return cal_y[-1]` at end of `_apply_calibration` is unreachable when `cal_x[0] < raw < cal_x[-1]` (the for-loop always finds a matching interval). Defensive but dead code. Coverage correctly reports it as uncovered.

- [N-3] **src/analysis/events.py:82-95** — Event labeling checks `future.high` for UP events and `future.low` for DOWN events, which is more sensitive than using `future.close`. This is arguably correct (detects if the level was _reached_ at any point) but differs from some common implementations that use close-to-close returns. The behavior matches the docstring, so this is informational.

- [N-4] **Classification config** — Both `EUR_USD_classifications.json` and `BTC_USD_classifications.json` have identical rule structures (22 tokens each) with only instrument prefix and ATR thresholds differing. If additional instruments are added, this pattern could be template-generated. Low priority for 2 instruments.

### Spec Compliance

| SPEC Section | Requirement | Status | Notes |
|---|---|---|---|
| §5.1 | Per-instrument strategy config with events, tokens, bayesian params | ✅ | Both strategy JSONs match spec schema |
| §5.2 | SignalGenerator protocol, registry, routing, fallback chains | ✅ | All generators satisfy protocol; MLV1 independent; ensemble validates weights |
| §5.2.4 | `generate_batch()` deterministic, no look-ahead, timestamped | ✅ | Tested in `TestBayesianV1GeneratorBatch` |
| §5.3 | Token format `{INSTRUMENT}_{PREFIX}_{PARAM}_{DATAPOINT}_{TYPE}_{VALUE}` | ✅ | Classification JSONs follow format |
| §5.4 | MI scoring, Jaccard dedup, top-N (max 50), logging | ✅ | `select_tokens()` with all steps; INFO-level logging |
| §5.5 | Naïve Bayes, Laplace smoothing, log-odds, isotonic calibration, posterior cap | ✅ | Full implementation with PAVA isotonic regression |
| §5.5 | Phi correlation check, warning at |phi|>0.7, alert at >3 pairs | ✅ | `check_correlations()` with logging |
| §5.7 | Action thresholds use strict `>` | ✅ | Fixed in T-201, boundary tests confirm |

### Task Acceptance Verification

| Task | Criteria Met | Notes |
|------|-------------|-------|
| T-201 | ✅ All met | 6 deferred findings resolved; threshold boundary tests; registry edge cases; ensemble weight validation |
| T-202 | ✅ All met | Event labeling with forward-looking windows; both instruments; frozen `EventLabel`; 17 tests |
| T-203 | ✅ All met | 10 condition types; 22 rules per instrument; frozen `TokenSet`; 41 tests; real config integration |
| T-204 | ✅ All met | MI scoring, Jaccard dedup, top-N capped at 50; INFO logging; 23 tests |
| T-205 | ✅ All met | Laplace smoothing, log-odds, isotonic calibration, posterior cap, phi correlation; 37 tests |
| T-206 | ✅ All met | BayesianV1Generator rewritten with tokenize→predict path; scaffold fallback retained; DEC-013; feature_providers.json fixed; data-layer edge cases; 16 tests |

### Quality Gate

- lint: **PASS** — `ruff check .` all checks passed
- types: **PASS** — `mypy src` no issues in 47 source files (strict mode)
- tests: **PASS** — 218 passed in 0.71s — coverage 89% global (≥80% target met)

### Coverage by Stage 2 Module

| Module | Stmts | Miss | Cover |
|--------|-------|------|-------|
| `src/analysis/events.py` | 50 | 0 | 100% |
| `src/analysis/tokenizer.py` | 76 | 0 | 100% |
| `src/analysis/token_selection.py` | 104 | 0 | 100% |
| `src/analysis/bayesian.py` | 169 | 4 | 98% |
| `src/trading/signal.py` | 140 | 8 | 94% |
| `src/analysis/signal_contract.py` | 32 | 0 | 100% |

Stage 2 modules average **98.5% coverage**. Uncovered lines are defensive fallbacks (bayesian.py:235,293,379,393) and scaffold generators (signal.py:65,141,159,170,175,196,257,274 — MLV1/Ensemble/Router paths deferred to Stage 3).

### Positive Observations

1. **Excellent test depth:** 168 new tests added across Stage 2 (50 → 218). All Stage 2 core modules at 94–100% coverage.
2. **Frozen dataclasses throughout:** `EventDefinition`, `EventLabel`, `ClassificationRule`, `TokenSet`, `TokenScore`, `SelectedTokenSet`, `TokenLikelihood`, `BayesianModel`, `CorrelationWarning` — all immutable per DEC-010.
3. **Numerically stable Bayesian engine:** Log-odds form prevents underflow; sigmoid handles extreme values; Laplace smoothing prevents log(0); posterior cap prevents overconfidence.
4. **Clean PAVA implementation:** Isotonic calibration via pool-adjacent-violators is a solid, well-understood algorithm. No external dependency needed.
5. **Config-driven token vocabulary:** Classification rules externalized to JSON, loaded at runtime. Adding new indicator tokens requires only config changes.
6. **Dual-path generator design:** BayesianV1Generator cleanly supports both real inference (model+rules) and scaffold fallback, with metadata indicating which path was used (`"source": "bayesian_engine"` vs `"source": "threshold"`).
7. **All Stage 1 deferred findings resolved:** 9 findings targeted at Stage 2 — all addressed with tests confirming the fixes.
8. **Decision log maintained:** DEC-013 properly documents the FeatureProvider sync batch signature deviation from SPEC §3.6 with clear rationale.

### Verdict

**Ready for merge.** No critical or blocking issues. Three warnings are documented design decisions (batch crossover limitation, fold ordering, type validation) — none are regressions. All 6 task acceptance criteria fully met. SPEC §5.1–5.5 compliance verified. Quality gate passes with 218 tests at 89% coverage. Stage 2 modules average 98.5% coverage.

## Red Team Review

- **Date:** 2026-03-03
- **Reviewer:** Adversarial Subagent (fresh context)
- **Scope:** Stage 2: Event Detection & Tokenization — full codebase on `stage/2-event-detection`

### Quality Gate

- lint: **PASS** — `ruff check .` all checks passed
- types: **PASS** — `mypy src` no issues in 47 source files (strict mode)
- tests: **PASS** — 218 passed, coverage 89%

### Critical

- [RC-1] **src/analysis/events.py:88-95** — Event labeling uses high/low watermark scanning instead of close-to-close forward return. Subagent claims SPEC §4.6 requires `(close[T+N] - close[T]) / close[T] >= X/100` (close-to-close measurement, NOT high-watermark). Implementation checks `future.high >= ref_close * (1 + threshold)` for UP events and `future.low <= ref_close * (1 - threshold)` for DOWN events, scanning any candle within the horizon. Subagent claims this systematically produces more optimistic labels, corrupting all downstream training. **Note:** Requires verification against actual SPEC §4.6 text — subagent may be referencing a section that specifies different semantics than what was implemented per task acceptance.

- [RC-2] **src/trading/signal.py:92-98** — `BayesianV1Generator.generate()` never passes `previous_features` to `tokenize()`, silently disabling 8 of 22 classification rules per instrument (36%): 4 `cross_above_val`/`cross_below_val`, 2 `cross_above`/`cross_below`, 2 `rising`/`falling`. Creates train/serve skew if training data had previous features available. Impact: severely limited token vocabulary in production inference path.

### High

- [RH-1] **src/trading/signal.py:97** — `close=features.values.get("_close", 0.0)` defaults to 0.0 when `_close` is missing from features. This causes BB band tokens (`BB2020_CL_BLW_LWR`) to always fire and (`BB2020_CL_ABV_UPR`) to never fire. Two of 22 tokens per instrument produce incorrect results.

- [RH-2] **src/trading/signal.py:223-227** — Generator override in `route_signal` creates a new `InstrumentRouting` with default thresholds (0.65/0.55/0.40) instead of preserving instrument-specific thresholds. BTC_USD (0.60/0.50/0.45) produces wrong action labels when override is used.

- [RH-3] **src/trading/signal.py:320-321** — `_build_signal` calls `_action_from_probability` with hardcoded default thresholds. When `generate_batch()` is used directly (backtesting path per SPEC §5.2.4), signals use default thresholds regardless of instrument. Creates backtest-to-live action divergence for BTC_USD.

- [RH-4] **src/analysis/events.py:31-38** — `EventLabel` dataclass only has `event_type`, `time`, `label`. Subagent claims SPEC §4.2 events table requires additional fields: `lookforward_periods`, `price_at_signal`, `price_at_resolution`. These fields are not captured, making database persistence impossible without data model changes.

- [RH-5] **src/analysis/events.py** — SPEC §4.6 specifies `min_occurrences` validation (default 100) with alert logging. Not implemented — system proceeds without warning on rare events with insufficient training data.

### Medium

- [RM-1] **src/analysis/bayesian.py:268-303** — K-fold CV for calibration splits by index position, not time. Could introduce look-ahead bias into calibration function. SPEC says "out-of-fold predictions" without specifying time ordering. Recommend time-ordered folds.

- [RM-2] **src/trading/signal.py:28-52** — `GeneratorRegistry._frozen` flag and `_generators` dict have no locking. Race between `register()` and `freeze()` theoretically possible under concurrent access. In practice unlikely since boot precedes ASGI server. Recommend `MappingProxyType` after freeze.

- [RM-3] **src/api/v1/signals.py:14** — `SignalRouter` uses `@dataclass` (not frozen), is module-level mutable global state shared across API requests. Inconsistent with DEC-010. No current mutation, but not defensively immutable.

- [RM-4] **src/analysis/bayesian.py:367** — Isotonic calibration uses block midpoints instead of boundary values. Reduces calibration resolution for wide PAVA blocks.

- [RM-5] **src/analysis/events.py:17** — Event regex `\d+` only matches integer thresholds. Events like `1.5PCT` would fail to parse. Current events are integer-only (1, 3), but limits extensibility.

### Low

- [RL-1] **src/trading/signal.py** — Duplicate action computation: `_build_signal` computes action with defaults, then `route_signal` overwrites with instrument thresholds via `replace()`.

- [RL-2] **src/analysis/token_selection.py:76-84** — MI inner loop iterates all vocab per token set: O(|token_sets| * |vocab|). Acceptable at current scale (~572k iterations) but scales poorly.

- [RL-3] **src/analysis/token_selection.py:173** — SPEC §5.4 step 5 requires logging correlation matrix during token selection. Implementation only logs token list and MI scores; phi correlation check is in bayesian.py at training time.

- [RL-4] **src/analysis/events.py:76-103** — `label_events` is O(n * h) where h is horizon in periods. Acceptable but should document complexity.

### Test Gaps

- [TG-1] **events.py** — No test verifying close-to-close vs high-watermark labeling behavior. Tests validate current (watermark) behavior.
- [TG-2] **signal.py:BayesianV1Generator** — No test for `previous_features` in inference path. Tests only use `below`/`above` conditions.
- [TG-3] **signal.py:BayesianV1Generator** — No test for `_close=0.0` fallback corrupting BB tokens.
- [TG-4] **signal.py:generate_batch** — No test for previous_features propagation between snapshots.
- [TG-5] **signal.py:route_signal** — No test for generator override threshold regression.
- [TG-6] **tokenizer.py:load_classifications** — No test for malformed classification JSON.
- [TG-7] **events.py:label_events** — No test for unsorted candle input.

### Positive Observations

1. Frozen dataclasses consistently used — all domain models per DEC-010.
2. Numerically stable sigmoid with dual-branch approach; prior clamped to [1e-10, 1-1e-10].
3. Laplace smoothing correctly implemented with `(count + alpha) / (total + 2*alpha)`.
4. Comprehensive threshold boundary tests with strict `>` comparisons per SPEC §5.7.
5. Jaccard dedup greedy and correct — MI-ranked order, checks against already-selected.
6. Phi correlation check with graduated warnings matching SPEC §5.5.
7. No security issues found — parameterized queries, no subprocess calls, no bare excepts.
8. 89% code coverage exceeds 80% target.

### Verdict

**FAIL** — Two critical findings (RC-1: event labeling semantics, RC-2: missing previous_features) must be addressed. RC-1 may corrupt all downstream training data. RC-2 silently disables 36% of the token vocabulary. High findings RH-1 through RH-5 should also be addressed.

## Stage Report

- **Date:** 2026-03-04
- **Status:** APPROVED
- **Sign-off:** 2026-03-04

### Quality Gate Summary

- lint: **PASS** — `ruff check .` clean
- types: **PASS** — `mypy src` clean (47 source files, strict mode)
- tests: **PASS** — 218 passed, coverage 89% (≥80% target met)

### Unified Findings

#### Critical (must fix)

_None._ Both red team critical findings were reclassified per user interview (see User Interview Notes).

#### High (must fix — FIX task)

- [SR-H1] **src/trading/signal.py:97** — Default `close=0.0` when `_close` missing from features silently corrupts Bollinger Band token evaluations. `BB2020_CL_BLW_LWR` always fires, `BB2020_CL_ABV_UPR` never fires. — source: Red Team RH-1
  - **Impact:** 2 of 22 tokens per instrument produce incorrect results when `_close` is absent from FeatureSnapshot.
  - **Remediation:** Require `_close` in features or raise a clear error. Add test for missing `_close`.

- [SR-H2] **src/trading/signal.py:223-227** — Generator override in `route_signal` creates `InstrumentRouting` with default thresholds (0.65/0.55/0.40) instead of preserving instrument-specific thresholds. — source: Red Team RH-2
  - **Impact:** BTC_USD (thresholds 0.60/0.50/0.45) produces wrong action labels when generator override is used.
  - **Remediation:** Copy thresholds from `self.routing[instrument]` when creating override routing.

- [SR-H3] **src/trading/signal.py:320-321** — `_build_signal` calls `_action_from_probability` with hardcoded default thresholds. `generate_batch()` signals use EUR_USD defaults regardless of instrument. — source: Red Team RH-3
  - **Impact:** Backtest-to-live action divergence for BTC_USD when using batch-generated signals.
  - **Remediation:** Pass instrument-specific thresholds through the generation path or accept thresholds as parameter in `_build_signal`.

#### High (deferred to target stages)

- [SR-H4] **src/trading/signal.py:92-98** — `BayesianV1Generator.generate()` never passes `previous_features` to `tokenize()`, disabling 8 of 22 classification rules (crossover, rising, falling). Training also lacks previous_features, so no train/serve skew exists. Symmetrical limitation. — source: Red Team RC-2, Code Review W-1. **Target: Stage 3/5** (orchestration pipeline).

- [SR-H5] **src/analysis/events.py:31-38** — `EventLabel` dataclass missing `lookforward_periods`, `price_at_signal`, `price_at_resolution` fields required by SPEC §4.2 events table schema. Not needed for in-memory training pipeline. — source: Red Team RH-4. **Target: Stage 5** (backtesting with DB persistence).

- [SR-H6] **src/analysis/events.py** — SPEC §4.6 `min_occurrences` validation (default 100) with alert logging not implemented. Not needed for in-memory training; becomes relevant when training on real historical data. — source: Red Team RH-5. **Target: Stage 5** (backtesting).

#### Medium (noted, no action required)

- [SR-M1] **src/analysis/events.py:88-95** — Event labeling uses high-watermark scanning instead of SPEC §4.6 close-to-close return. User decision: keep current approach, make configurable in future strategy config. To be recorded as DEC-014. — source: Red Team RC-1, Code Review N-3
- [SR-M2] **src/analysis/bayesian.py:268-303** — K-fold CV splits by index, not time. Could introduce look-ahead bias into calibration. SPEC says "out-of-fold" without requiring time ordering. — source: Red Team RM-1, Code Review W-2
- [SR-M3] **src/trading/signal.py:28-52** — GeneratorRegistry freeze mechanism not thread-safe. Boot precedes ASGI server in practice. — source: Red Team RM-2
- [SR-M4] **src/api/v1/signals.py:14** — SignalRouter is mutable `@dataclass`, module-level global. Inconsistent with DEC-010. — source: Red Team RM-3, Stage 1 RM-4
- [SR-M5] **src/analysis/bayesian.py:367** — Isotonic calibration uses block midpoints instead of boundary values. — source: Red Team RM-4
- [SR-M6] **src/analysis/events.py:17** — Event regex integer-only (`\d+`). Limits extensibility for decimal thresholds. — source: Red Team RM-5
- [SR-M7] **src/trading/signal.py:87-88** — No runtime type validation on `config.parameters["model"]` and `config.parameters["rules"]`. — source: Code Review W-3

#### Low (noted)

- [SR-L1] **src/trading/signal.py** — Duplicate action computation in `_build_signal` then `route_signal`. — source: Red Team RL-1
- [SR-L2] **src/analysis/token_selection.py:76-84** — MI inner loop O(|token_sets| × |vocab|). Acceptable at current scale. — source: Red Team RL-2
- [SR-L3] **src/analysis/token_selection.py:173** — SPEC §5.4 step 5 correlation matrix logging in token_selection; phi check in bayesian.py instead. — source: Red Team RL-3
- [SR-L4] **src/analysis/events.py:76-103** — `label_events` O(n × h). Acceptable. — source: Red Team RL-4

### Test Gap Summary

- [SR-TG1] **signal.py:BayesianV1Generator** — No test for `previous_features` in inference path. Deferred with SR-H4. — source: Red Team TG-2, TG-4
- [SR-TG2] **tokenizer.py:load_classifications** — No test for malformed classification JSON. Minor robustness gap. — source: Red Team TG-6
- [SR-TG3] **events.py:label_events** — No test for unsorted candle input. — source: Red Team TG-7

Note: TG-3 (_close=0.0 fallback) and TG-5 (override thresholds) will be covered by the FIX task tests.

### Contradictions Between Reviews

One contradiction identified and resolved:

- **Event labeling (RC-1):** Code review noted high/low watermark as N-3 (informational, "behavior matches the docstring"). Red team flagged as RC-1 (critical spec violation). Resolution: The SPEC §4.6 text is unambiguous ("NOT a high-watermark measurement"), but the user considers the labeling method a strategy-dependent design choice. Reclassified as Medium with DEC-014 recording the deviation. Future: make configurable per strategy.

All other findings are consistent between reviews. Both reviews agree on quality gate results and positive observations.

### User Interview Notes

- **RC-1 (event labeling):** User considers the labeling method (close-to-close vs high-watermark) a strategy-dependent design decision, not a fixed spec requirement. High-watermark approach should be retained for now. Will be made configurable per strategy in a future stage. Record as DEC-014.
- **RC-2 (previous_features):** User confirmed no train/serve skew exists since both training and inference lack previous_features. Downgraded to High, deferred to Stage 3/5 when orchestration pipeline provides sequential context.
- **RH-1 (close=0.0):** Bundle into FIX task — require `_close` or raise error.
- **RH-2/RH-3 (thresholds):** Fix now — bundle into FIX task. Important for backtest accuracy.
- **RH-4/RH-5 (EventLabel fields, min_occurrences):** Defer both to Stage 5 (backtesting). Not needed for in-memory training pipeline.
- **No additional issues** reported from manual testing. User is confident in Stage 2 code.

### Positive Observations

Consolidated from both reviews:
1. **Excellent test depth:** 168 new tests (50 → 218). Stage 2 core modules at 94–100% coverage.
2. **Frozen dataclasses throughout:** All 9 new Stage 2 domain types are `@dataclass(frozen=True)` per DEC-010.
3. **Numerically stable Bayesian engine:** Log-odds form, dual-branch sigmoid, Laplace smoothing, posterior cap — all correctly implemented.
4. **No security issues:** Parameterized queries, no subprocess calls, no bare excepts, no credential leaks.
5. **All Stage 1 deferred findings resolved:** 9 findings targeted at Stage 2 — all addressed with tests.
6. **Clean PAVA isotonic calibration:** No external dependency, well-tested.
7. **Config-driven token vocabulary:** 22 rules per instrument, externalized to JSON.
8. **Dual-path generator:** Bayesian engine path with scaffold fallback, metadata indicates source.
9. **Decision log maintained:** DEC-013 properly documents FeatureProvider sync batch signature.

### Remediation Tasks

| ID | Task | Scope | Acceptance | Status |
|---|---|---|---|---|
| T-206-FIX1 | Fix default close fallback and action threshold inconsistencies in signal generators | server | (1) `BayesianV1Generator.generate()` raises `RecoverableSignalError` when `_close` is missing from `features.values` and model+rules are present; test confirms BB tokens are not silently corrupted. (2) Generator override in `route_signal` preserves instrument-specific thresholds from `self.routing[instrument]`; test confirms BTC_USD override uses 0.60/0.50/0.45. (3) `generate_batch()` signals use instrument-appropriate thresholds (or thresholds are passed through config); test confirms BTC_USD batch signals differ from EUR_USD defaults. (4) DEC-014 recorded for event labeling high-watermark approach. (5) Quality gate passes. | TODO |

### Verdict

**NOT READY** — Three High findings (SR-H1, SR-H2, SR-H3) require remediation before the stage gate. One FIX task (T-206-FIX1) bundles all three fixes plus DEC-014. Three additional High findings (SR-H4, SR-H5, SR-H6) are deferred to their target stages with documented traceability. After the fix is shipped and verified, the stage gate can proceed.

## Fix Verification

- **Date:** 2026-03-04
- **Status:** PASS

### Verified Fixes

| Fix Task | Original Finding | Status | Notes |
|---|---|---|---|
| T-206-FIX1 (SR-H1) | `close=0.0` default corrupts BB tokens | PASS | `BayesianV1Generator.generate()` now raises `RecoverableSignalError("_close required in features for Bayesian inference")` when `_close` is missing and model+rules are present (line 94-97). Scaffold fallback path unchanged — does not require `_close`. Verified by 3 tests in `TestCloseRequiredForInference`. |
| T-206-FIX1 (SR-H2) | Generator override uses default thresholds | PASS | `route_signal` override path now copies `strong_buy_threshold`, `buy_threshold`, `sell_threshold` from `self.routing[instrument]` (line 233-244). BTC_USD with prob 0.53 correctly returns BUY (>0.50) instead of NEUTRAL. Verified by `test_generator_override_preserves_btc_thresholds` and `test_generator_override_does_not_use_default_thresholds`. |
| T-206-FIX1 (SR-H3) | `generate_batch` uses hardcoded thresholds | PASS | New `_extract_thresholds()` helper (line 362-367) extracts thresholds from `config.parameters["thresholds"]`. `_build_signal()` accepts optional `thresholds` kwarg (line 335). All three generators (BayesianV1, MLV1, EnsembleV1) pass thresholds through. Verified by `test_batch_signal_uses_config_thresholds` and `test_batch_signal_without_thresholds_uses_defaults`. |
| T-206-FIX1 (DEC-014) | Event labeling spec deviation | PASS | DEC-014 recorded in DECISIONS.md documenting high-watermark approach and future configurability plan. |

### Quality Gate
- lint: PASS — `ruff check .` clean
- types: PASS — `mypy src` clean (47 source files)
- tests: PASS — 225 passed, coverage 89%

### Regression Check
- All 225 tests pass (218 pre-existing + 7 new)
- No new linting or type errors introduced
- `signal.py` coverage increased from 94% to 95%
- No regressions in signal routing, Bayesian inference, or ensemble generation paths

### New Issues Found
None — fixes are clean.

### Verdict
**PASS**

All three High findings (SR-H1, SR-H2, SR-H3) are resolved with targeted fixes and comprehensive test coverage. DEC-014 is properly recorded. No regressions detected. The stage can proceed to approval and the stage gate.
