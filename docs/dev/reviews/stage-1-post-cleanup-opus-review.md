# Pre-Merge Review: stage/1-post-cleanup → main

**Reviewer:** Opus (automated)
**Date:** 2026-02-18
**Branch:** `stage/1-post-cleanup` (5339b74)
**Base:** `main`
**Diff scope:** 52 files changed, +2995 / −276

---

## Executive Verdict: **CONDITIONAL PASS**

The branch is merge-ready with **one conditional fix** (Major #1 below). The remaining findings are minor and can ship as-is with follow-up tickets. All 42 tests pass. No regressions to existing Stage 1 functionality were found. The new signal architecture aligns with SPEC.v4 and respects the FINAL_SPEC §8 ownership boundary.

---

## Critical Findings (must fix before merge)

**None.**

---

## Major Findings (should fix)

### M-1: Ensemble confidence formula is semantically inverted

**File:** `src/trading/signal.py` line 113
**Issue:** `EnsembleV1Generator` computes `confidence = _clamp(abs(bayesian_score - ml_score))`. This means *high disagreement* between component signals produces *high confidence*, which is semantically backwards. When bayesian and ML disagree strongly, the ensemble should have *lower* confidence in its blended output.

**Spec reference:** SPEC.v4 §1.2 requires `confidence: float # confidence [0.0, 1.0]`. FINAL_SPEC §5.6 uses confidence as an input to the meta-learner and regime-aware position sizing — semantically inverted confidence would propagate incorrect risk sizing in downstream stages.

**Risk:** Low in Stage 1 (scaffold values only), but **will cause incorrect risk sizing in Stage 2+** if not addressed.

**Fix:**
```python
# Replace:
confidence = _clamp(abs(bayesian_score - ml_score))
# With:
confidence = _clamp(1.0 - abs(bayesian_score - ml_score))
```

**Recommendation:** Fix before merge or create a tracked ticket for Stage 2 entry. If deferred, add a `# TODO(Stage-2): invert confidence` comment to prevent silent propagation.

### M-2: Signal action thresholds are hardcoded, not per-instrument

**File:** `src/trading/signal.py` lines 210–216
**Issue:** `_action_from_probability()` uses hardcoded thresholds (0.65/0.55/0.40) matching EUR_USD defaults from FINAL_SPEC §5.1. BTC_USD specifies different thresholds (0.60/0.50/0.45). Currently all instruments share EUR_USD thresholds.

**Spec reference:** FINAL_SPEC §5.1 explicitly defines per-instrument `thresholds` in strategy config.

**Risk:** Low in Stage 1 (scaffold mode), but becomes a correctness issue when BTC_USD signal generation is live.

**Fix:** Accept thresholds as parameters (from `GeneratorConfig.parameters` or a new `ThresholdConfig`), or defer with a tracked ticket and clear TODO comment.

**Recommendation:** Acceptable to merge as-is since this is a Stage 2+ concern. Add `# TODO(Stage-2): per-instrument thresholds from strategy config` comment.

---

## Minor Findings (nice-to-have)

### m-1: Module-level `_signal_router` instantiation in signals API

**File:** `src/api/v1/signals.py` line 13
**Issue:** `_signal_router: SignalRouter = build_default_router()` is instantiated at import time. This is fine for the current scaffold but prevents runtime configuration updates and makes testing harder (requires monkeypatching the module-level variable).

**Recommendation:** Defer to Stage 2 when signal config governance (SPEC.v4 §1.5.1) is implemented. No action needed now.

### m-2: `MLV1Generator` is a zero-value subclass

**File:** `src/trading/signal.py` line 96
**Issue:** `class MLV1Generator(BayesianV1Generator)` — `ml_v1` is just an alias for bayesian with a different `generator_id`. This is intentionally scaffolded (generator disabled by default) but could confuse future developers.

**Recommendation:** Add a brief docstring: `"""Scaffold: will diverge in Stage 3 when XGBoost integration lands."""`

### m-3: Missing `STRONG_SELL` action in vocabulary

**File:** `src/analysis/signal_contract.py` line 9
**Issue:** `SignalAction = Literal["STRONG_BUY", "BUY", "SELL", "NEUTRAL"]` — matches FINAL_SPEC §5.6 which only defines these four actions (v1 is long-only; SELL closes positions). This is *correct* for v1. No fix needed.

**Observation only** — document that `STRONG_SELL` is explicitly deferred per FINAL_SPEC §2.2.

### m-4: `VERSION` file missing trailing newline

**File:** `VERSION`
**Issue:** `0.2.1` without trailing newline. Most POSIX tooling expects a final newline.

**Fix:** `echo "0.2.1" > VERSION`

### m-5: Test `test_signals_api.py` imports `app` but doesn't use it directly

**File:** `tests/unit/test_signals_api.py` line 4
**Issue:** `from src.app import app` is imported to trigger router registration side-effects. This is a valid pattern for FastAPI testing but the import should have a comment explaining the intent.

**Fix:** Add `# noqa: F401 — import triggers router mount` comment.

### m-6: `talib` import exposed as module-level mutable binding

**File:** `src/data/indicators.py` line 16
**Issue:** `talib: Any | None = _talib` creates a module-level mutable binding that could be reassigned accidentally. The internal `_talib` sentinel is correct; the public `talib` alias is only used for `is not None` checks.

**Risk:** Negligible. Pattern is common in optional-dependency handling.

---

## File-by-File Actionable Recommendations

### Core Logic (changed/new)

| File | Verdict | Notes |
|------|---------|-------|
| `src/analysis/signal_contract.py` | ✅ Clean | Protocol + dataclasses match SPEC.v4 §1.2 exactly. `is_valid_action()` guard is useful. |
| `src/trading/signal.py` | ⚠️ M-1, M-2 | Generator registry freeze semantics correct. Routing/fallback logic matches SPEC.v4 §1.4.1. Failsafe signal matches spec. Confidence formula (M-1) and hardcoded thresholds (M-2) need attention. |
| `src/api/v1/signals.py` | ✅ Clean | Additive endpoints, correct 404 handling, scaffold feature values appropriate for Stage 1. |
| `src/app.py` | ✅ Clean | Router mounting is additive-only. No existing endpoints disturbed. |
| `src/data/indicators.py` | ✅ Clean | TA-Lib integration with manual fallback is well-structured. Original functions renamed to `_manual_*` and wrapped with TA-Lib dispatch. All tests confirm parity. |

### Tests (new)

| File | Verdict | Notes |
|------|---------|-------|
| `tests/unit/test_signal_contract_and_routing.py` | ✅ Good | Covers contract vocab, batch determinism, fallback + logging, registry contents. |
| `tests/unit/test_signals_api.py` | ✅ Good | Validates endpoint additivity and checks existing Stage 1 routes are preserved (regression guard). |
| `tests/unit/test_indicators_provider.py` (changes) | ✅ Good | TA-Lib parity tests with 512-candle random walk and <0.01% deviation gate. Updated golden values match TA-Lib reference. |

### Client (changed)

| File | Verdict | Notes |
|------|---------|-------|
| `client/src/main.js` | ✅ Clean | `BTC_USDT` → `BTC_USD` naming fix aligns with FINAL_SPEC §1.3 `instrument_id`. API path fixes (`/api/v1/ohlcv/{instrument}`) match implemented routes. Data source banner and empty-payload handling are good defensive changes. `apiUrl()` helper for dev proxy is correct. |
| `client/public/index.html` | ✅ Clean | Adds `data-source-overall` element referenced by JS. |
| `client/public/dist/main.js` | ✅ Clean | Mirror of `src/main.js` (build artifact). |
| `client/package.json` | ✅ Clean | Adds `build` script. |

### Scripts & Config

| File | Verdict | Notes |
|------|---------|-------|
| `scripts/run_api.sh` | ✅ Clean | `.env` loading is correct (`set -a / set +a` pattern). |
| `requirements.txt` | ✅ Clean | `ta-lib` addition matches the new indicator integration. |
| `VERSION` | ⚠️ m-4 | Missing trailing newline. |

### Documentation (new/changed)

| File | Verdict | Notes |
|------|---------|-------|
| `CHANGELOG.md` | ✅ Clean | Well-structured history. Post-merge verification checklist is useful. |
| `README.md` | ✅ Clean | Substantial improvement from scaffold README. Architecture diagram matches implementation. |
| `TASKS.md` | ✅ Clean | Task tracking updated. |
| `DECISIONS.md` | ✅ Clean | Decision records maintained. |
| `spec/SPEC.v4.md` | ✅ Clean | Additive spec that correctly extends FINAL_SPEC. |
| `docs/dev/*` | ✅ Clean | All new review/verification docs are additive. |

### Scaffold Docstring Updates (20 files)

All scaffold files (`src/analysis/bayesian.py`, `src/analysis/events.py`, `src/backtest/engine.py`, etc.) received identical docstring changes:
```python
-"""Scaffold module per FINAL_SPEC Appendix D."""
+"""TODO(N-201+): module scaffold retained intentionally for staged implementation.
+Aligned during N-221 compatibility pass to avoid naming drift against FINAL_SPEC/SPEC.v4."""
```

**Verdict:** ✅ Harmless. Better than the original scaffold strings as they signal intentional retention and link to task IDs.

---

## Spec Cross-Reference Summary

| Spec Requirement | Status | Notes |
|-----------------|--------|-------|
| SPEC.v4 §1.2 Signal dataclass fields | ✅ Match | All 8 fields present in `Signal` dataclass |
| SPEC.v4 §1.2 `SignalGenerator` Protocol | ✅ Match | `generate()`, `generate_batch()`, `validate_config()`, `id`, `version` |
| SPEC.v4 §1.3 Registry boot-time write / runtime read-only | ✅ Match | `_frozen` flag enforced |
| SPEC.v4 §1.4.1 Routing + fallback semantics | ✅ Match | Primary → fallback → neutral failsafe chain implemented |
| SPEC.v4 §1.4.1 Fallback logging | ✅ Match | `signal_generator_fallback` log message with required fields |
| SPEC.v4 §1.5 API endpoints | ✅ Match | `/signals/generators` and `/signals/{instrument}` implemented. `/signals/config` POST deferred (appropriate for Stage 1). |
| SPEC.v4 §2 `generate_batch()` determinism | ✅ Match | Tested in `test_generate_batch_is_deterministic` |
| SPEC.v4 §2 Backtest ownership boundary | ✅ Match | Comment in signal_contract.py: "PnL simulation remains owned by the backtest module per FINAL_SPEC §8" |
| FINAL_SPEC §5.6 Signal action vocabulary | ✅ Match | `STRONG_BUY`, `BUY`, `SELL`, `NEUTRAL` |
| FINAL_SPEC §5.1 Per-instrument thresholds | ⚠️ M-2 | Hardcoded to EUR_USD values; BTC_USD thresholds not parameterized |
| FINAL_SPEC §3.2 Additive API versioning | ✅ Match | New endpoints under `/api/v1/`, no existing routes changed |
| FINAL_SPEC §4.3 Feature key format | ✅ Match | Indicator keys unchanged, TA-Lib dispatch is internal |

---

## Merge Readiness Decision

**CONDITIONAL PASS** — Safe to merge if:

1. **M-1** (ensemble confidence inversion) is either fixed or tracked with a `# TODO` comment and corresponding ticket. Since Stage 1 uses scaffold values only and `ml_v1` is disabled, the inverted confidence doesn't affect runtime behavior yet, but it **must** be resolved before Stage 2 signal routing goes live.

2. **M-2** (hardcoded thresholds) is either parameterized or documented with a `# TODO` comment for Stage 2.

All other findings are minor and non-blocking. The branch introduces no regressions, all tests pass (42/42), and the implementation faithfully follows the SPEC.v4 signal architecture while maintaining backward compatibility with existing Stage 1 surfaces.

---

*Review conducted against full diff (52 files, +2995/−276), FINAL_SPEC.md, and spec/SPEC.v4.md.*

## Fixes Applied

- Ensemble confidence calculation updated in `src/trading/signal.py` to decrease with disagreement:
  `confidence = clamp(1.0 - abs(bayesian_score - ml_score))`.
- Signal action thresholds are now parameterized per instrument via `InstrumentRouting`
  (EUR_USD: 0.65/0.55/0.40, BTC_USD: 0.60/0.50/0.45 for strong_buy/buy/sell).
- Added tests in `tests/unit/test_signal_contract_and_routing.py` for:
  - confidence decreasing as model disagreement increases;
  - instrument-specific threshold behavior for EUR_USD vs BTC_USD.
- Commit reference: `fix: address Opus major findings for confidence and threshold parameterization` (this commit).
