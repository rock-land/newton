# Newton Code Reviews

Review log for stage-level code audits. Each stage must have an APPROVED review before work begins on the next stage.

**Status values:** `PENDING` → `NEEDS_FIXES` → `APPROVED`
**Sign-off:** Only the project lead can set status to APPROVED.

<!--
This file is populated automatically by the review pipeline:
  1. /review       — writes a Code Review subsection
  2. /red-review   — writes a Red Team Review subsection (via subagent)
  3. /stage-report — writes a Stage Report subsection (unified assessment)
  4. /verify-fixes — writes a Fix Verification subsection

For existing project bootstraps:
  /bootstrap-existing — writes a Baseline Audit section (one-time, pre-governance)
  This audit feeds into /stage-init for Stage 1 task generation.

Do not manually edit review content. Only the lead edits Status and Sign-off fields.
-->

---

## Baseline Audit

- **Date:** 2026-03-02
- **Scope:** Full codebase audit (pre-governance)

### Quality Gate
- lint: PASS — `ruff check .` — all checks passed
- types: PASS — `mypy src` — no issues found in 47 source files
- tests: PASS — `pytest -q` — 44 passed in 0.37s (coverage not yet tracked)

### Critical Findings (must address in Stage 1)

_None identified._ The existing codebase is clean and well-structured.

### High Findings (should address in Stage 1)

- [BA-H1] **VERSION file** VERSION reads `0.2.1` from pre-governance development. Must be reset to `0.1.0` to align with governance versioning scheme. Inconsistency could cause confusion in version-dependent operations (commit messages, changelogs).
- [BA-H2] **Dockerfile** The Dockerfile is a stub (`# Scaffold Dockerfile placeholder`). Not usable for production deployment. Should be implemented or explicitly deferred to Stage 7/8.
- [BA-H3] **src/api/v1/signals.py** Signal endpoint uses hardcoded scaffold data (dummy `FeatureSnapshot` with arbitrary values) instead of querying the feature store. Returns misleading results if called in production context.

### Medium Findings (recommend addressing)

- [BA-M1] **pytest.ini** No coverage tracking configured. `pytest-cov` is in `requirements.txt` but not wired into the default test run. Makes it hard to enforce the >=80% coverage target.
- [BA-M2] **13 scaffold modules** Analysis (events, tokenizer, token_selection, bayesian, ml_model, meta_learner), trading (broker_base, broker_oanda, broker_binance, risk, executor, reconciler, circuit_breaker), backtest (engine, simulator, metrics, report), regime (detector) are empty. This is intentional (DEC-009) but should be acknowledged.
- [BA-M3] **client/src/** Both `main.js` and `main.tsx` exist as entry points. Only `main.tsx` is the intended entry. `main.js` appears to be a leftover.

### Low Findings (informational)

- [BA-L1] **docs/dev/reviews/** Contains 10 pre-governance review/audit files from previous development cycles. These are historical artifacts and do not need modification.
- [BA-L2] **config/classifications/** Classification JSON files exist for both instruments but are not yet consumed by any implemented module (target: Stage 2 Event Detection).

### Positive Observations

- **Excellent type safety:** Comprehensive Python 3.11+ type annotations throughout all implemented modules. mypy strict mode passes cleanly on 47 source files.
- **Protocol-based design:** All major abstractions use runtime-checkable `Protocol` classes (FeatureProvider, SignalGenerator, HTTP clients). Enables clean testing via duck typing.
- **Immutable domain models:** All data transfer objects use `@dataclass(frozen=True)`, preventing accidental mutation.
- **Comprehensive test suite:** 44 tests across unit, integration, and scenario categories, all passing. Tests use well-crafted fakes (FakeCursor, FakeConnection, FakeHTTPClient) rather than fragile mocks.
- **Clean quality gate:** Both ruff and mypy pass with zero issues. No linting suppressions or type ignores needed.
- **Robust data pipeline:** Verification system checks for duplicates, OHLC integrity, gaps, and staleness with structured alert payloads.
- **Dual-mode indicators:** TA-Lib with pure Python fallback ensures portability without sacrificing accuracy.
- **Signal fallback chain:** Primary → fallback → neutral fail-safe pattern ensures the system always produces a signal.
- **Structured logging:** JSON-formatted logs with event types enable machine-parseable monitoring.
- **Config validation:** Pydantic v2 schemas with cross-field validators catch invalid configuration at load time.

### Recommended Stage 1 Focus

Stage 1 should prioritize:
1. **Coverage tracking** — Wire pytest-cov into the default test command and establish baseline coverage metrics (BA-M1)
2. **VERSION reset** — Align VERSION file with governance scheme (BA-H1)
3. **Signal endpoint cleanup** — Either properly wire the signal endpoint to the feature store or clearly mark it as scaffold-only (BA-H3)
4. **Dockerfile** — Decide whether to implement now or explicitly defer (BA-H2)
5. **Client entry point cleanup** — Remove stale `main.js` (BA-M3)
6. Any additional remediation tasks identified during `/stage-init`

---

## Stage 1: Remediation & Hardening

### Code Review

- **Date:** 2026-03-02
- **Scope:** Full Stage 1 — all 3 implementation tasks (T-101, T-102, T-103)

#### Baseline Audit Resolution

All High and targeted Medium findings from the Baseline Audit have been addressed:

| Finding | Resolution | Task |
|---------|-----------|------|
| BA-H1 (VERSION) | Reset to `0.1.0` during bootstrap, now at `0.1.3` | Bootstrap |
| BA-H2 (Dockerfile) | DEC-012 explicitly defers to Stage 7 | T-103 |
| BA-H3 (Signal scaffold) | `"scaffold": true` + warning added to both endpoints | T-102 |
| BA-M1 (pytest-cov) | `addopts = --cov=src --cov-report=term-missing` in pytest.ini | T-101 |
| BA-M3 (client entry) | `client/src/main.js` deleted, `main.tsx` scaffold retained | T-103 |

#### Findings

##### Critical

_None._

##### Warning

- [W-1] **src/app.py:12** — `version="0.1.0"` is hardcoded in the FastAPI constructor. This does not track the `VERSION` file and will drift as versions bump. Consider reading from `VERSION` at startup. Pre-governance code, not a Stage 1 regression — defer to future stage.
- [W-2] **client/public/index.html:80** — `<script type="module" src="dist/main.js"></script>` references a deleted file. Page loads but JS panel is non-functional. Acceptable since client is deferred to Stage 6, but the broken reference will confuse anyone visiting the root URL.

##### Note

- [N-1] **tests/unit/test_indicators_provider.py:281,334** — `monkeypatch` parameter typed as `object` but immediately shadowed by `pytest.MonkeyPatch()`. The parameter is unused. Non-idiomatic but functional. Consider removing the parameter and creating the MonkeyPatch directly.
- [N-2] **src/api/v1/data.py** — Coverage at 38% (lowest module). Data endpoints require DB connection for integration testing. Not a Stage 1 concern but should be addressed when data endpoints are enhanced in future stages.
- [N-3] **src/api/v1/signals.py:14** — `_signal_router` is instantiated at module import time via `build_default_router()`. This means the router config is loaded once and never refreshed. Acceptable for scaffold stage but will need lifecycle management when real signal generation is implemented (Stage 2+).

#### Quality Gate

- lint: **PASS** — `ruff check .` — all checks passed
- types: **PASS** — `mypy src` — no issues found in 47 source files
- tests: **PASS** — 50 passed in 0.42s — coverage 82% global (≥80% target met)

#### Task Acceptance Verification

| Task | Criteria Met | Notes |
|------|-------------|-------|
| T-101 | ✅ All met | pytest.ini addopts wired; coverage ≥80%; report shows per-module coverage |
| T-102 | ✅ All met | Both endpoints include `scaffold: true`; warning present; tests verify all scaffold markers |
| T-103 | ✅ All met | `client/src/main.js` deleted; DEC-012 recorded; Dockerfile unchanged |

#### Verdict

**Ready for merge.** No critical or blocking issues. Two warnings are pre-existing conditions (not Stage 1 regressions) and are appropriately deferred. All 3 Baseline Audit High findings resolved. Quality gate passes cleanly. Test count grew from 44 → 50 with 82% coverage baseline established.

### Red Team Review

- **Date:** 2026-03-02
- **Reviewer:** Adversarial Subagent (fresh context)
- **Scope:** Stage 1: Remediation & Hardening — full codebase on `stage/1-remediation`

#### Quality Gate

- lint: **PASS** — `ruff check .` clean
- types: **PASS** — `mypy src` clean (47 source files, strict mode)
- tests: **PASS** — 50 passed, 0 failed, coverage 82%

#### Critical

- [RC-1] **src/data/fetcher_oanda.py:31** — Hardcoded Oanda URL validation (`api-fxpractice.oanda.com`) blocks live trading. The `base_url` parameter creates false configurability; live URL `api-fxtrade.oanda.com` will be rejected. Fix: validate against configured `self._base_url` netloc.
- [RC-2] **src/api/v1/data.py:48,81** — Silent `except Exception:` blocks swallow ALL errors from database and candle age queries without logging. Database failures, credential errors, and schema corruption are invisible. Fix: log exceptions before returning defaults.

#### High

- [RH-1] **src/trading/signal.py:235-239** — Signal action threshold uses `>=` but SPEC §5.7 says `>`. At boundary values (exactly threshold), code returns wrong action.
- [RH-2] **src/api/v1/data.py:162-220,266-330** — API paths `/api/v1/ohlcv/` and `/api/v1/features/` deviate from SPEC §8.1 which specifies `/api/v1/data/ohlcv/` and `/api/v1/data/features/`.
- [RH-3] **src/api/v1/data.py:105** — Hardcoded instrument list `["EUR_USD", "BTC_USD"]` in HealthService violates config-driven design (DEC-007).
- [RH-4] **src/api/v1/data.py:104** — Health check interval uses undocumented env var `NEWTON_HEALTH_INTERVAL` instead of config schema. Invalid values passed unvalidated to DB query.
- [RH-5] **src/data/feature_provider.py:30-37** — FeatureProvider protocol signature (sync, takes candles, returns dict[datetime, dict]) deviates from SPEC §3.6 (async, takes timestamp, returns dict[str, float]) without a recorded decision.
- [RH-6] **config/feature_providers.json:5** — Provider class path `newton.data.indicators` doesn't match actual import path `src.data.indicators`. Dynamic loading will fail.

#### Medium

- [RM-1] **src/trading/signal.py:98-99** — MLV1Generator inherits from BayesianV1Generator (violates DEC-005 protocol pattern). Produces identical signals labeled as "ML".
- [RM-2] **src/trading/signal.py:110-112** — Ensemble weights not validated to sum to 1.0. Weights of `[1.0, 1.0]` produce probability > 1.0 before silent clamping.
- [RM-3] **src/api/v1/data.py:194** — Raw exception strings leaked in HTTP 500 responses. Could expose DB connection strings, table names, SQL errors.
- [RM-4] **src/api/v1/signals.py:14** — `_signal_router` is module-level mutable state. `SignalRouter` dataclass is NOT frozen — endpoint handlers could mutate routing at runtime.
- [RM-5] **src/data/fetcher_oanda.py:115, fetcher_binance.py:114** — Hardcoded instrument strings in fetcher normalization functions. Cannot reuse fetchers for additional instruments.
- [RM-6] **src/api/v1/data.py:162-168** — No validation of `instrument` path parameter against configured instruments. Invalid instruments silently return empty results.
- [RM-7] **src/api/v1/data.py:162-168** — Missing `end` parameter on OHLCV endpoint for bounded time-range queries.
- [RM-8] **src/trading/signal.py:244-262** — `_build_signal` computes action from unclamped probability, then clamps. Action and probability could be inconsistent.
- [RM-9] **VERSION vs TASKS.md** — VERSION file says `0.1.3` but TASKS.md header says `0.1.0`. Version reference table not updated.

#### Low

- [RL-1] **src/data/fetcher_binance.py:37** — Binance URL validation also hardcoded; will block testnet URLs for paper trading (Stage 7).
- [RL-2] **src/data/fetcher_oanda.py:130-173, fetcher_binance.py:129-172** — Duplicated `store_verified_candles` implementations. Should be shared.
- [RL-3] **src/data/fetcher_oanda.py:54-63, fetcher_binance.py:54-61** — Duplicated `CursorLike`/`ConnectionLike` protocol definitions across modules.
- [RL-4] **client/public/index.html:75** — Client references EMA(20) and SMA(50) indicators that do not exist in the feature store.
- [RL-5] **client/public/index.html:80** — Script tag references `dist/main.js` that is never built. 404 in browser console.
- [RL-6] **docker-compose.yml:1** — Deprecated `version: "3.9"` key produces warning in modern Docker Compose.
- [RL-7] **docker-compose.yml:11** — Default database password in docker-compose fallback. Acceptable for dev, flag before deployment.
- [RL-8] **tests: test_scaffold.py, test_scaffold_integration.py, test_scaffold_scenario.py** — Three tests assert only `True`. Inflate test count without value.
- [RL-9] **tests/unit/test_indicators_provider.py:281-331** — Unusual MonkeyPatch pattern: parameter accepted but shadowed by manually created instance.

#### Test Gaps

- [TG-1] **src/data/fetcher_oanda.py:UrllibOandaHTTPClient** — No tests for real HTTP client (timeouts, SSL, rate limiting).
- [TG-2] **src/data/fetcher_binance.py:UrllibBinanceHTTPClient** — Same as TG-1 for Binance.
- [TG-3] **src/api/v1/data.py:get_ohlcv, get_features** — No unit or integration tests for data endpoints.
- [TG-4] **src/api/v1/data.py** — No error path tests (DB unavailable, malformed params, unsupported instrument).
- [TG-5] **src/trading/signal.py:_action_from_probability** — No boundary condition tests (probability exactly at thresholds).
- [TG-6] **src/data/verifier.py** — No test for empty candle list input.
- [TG-7] **src/data/indicators.py** — No tests for zero-volume candles, zero-range candles, or negative prices.
- [TG-8] **src/trading/signal.py:GeneratorRegistry** — No tests for register-after-freeze or unknown generator_id.
- [TG-9] **src/api/v1/signals.py:get_current_signal** — No test for invalid instrument (404 path at line 39 is uncovered).

#### Positive Observations

1. SQL injection prevention is solid — all queries use parameterized `%s` placeholders.
2. Frozen dataclasses used consistently for all domain models per DEC-010.
3. Timezone discipline excellent — all datetimes use `tz=UTC`, `require_utc()` guards in data paths.
4. Configuration validation thorough — Pydantic schemas with cross-field validators and `extra="forbid"`.
5. Indicator parity testing rigorous — TA-Lib reference comparison within 0.01% over 512 candles.
6. Signal fallback chain correctly tested including neutral fail-safe path.
7. Scaffold pattern clean and consistently documented with DEC-009 references.
8. API checksum mechanism well-implemented (SHA-256 with deterministic JSON serialization).

#### Verdict

**CONDITIONAL PASS** — Two critical findings (RC-1: hardcoded Oanda URL validation, RC-2: silent exception swallowing) should be addressed. High findings represent spec deviations that should be documented in DECISIONS.md if intentional or fixed if not. None are Stage 1 regressions — all are pre-governance code.

### Stage Report

- **Date:** 2026-03-02
- **Status:** APPROVED
- **Sign-off:** 2026-03-03

#### Quality Gate Summary

- lint: **PASS** — `ruff check .` clean
- types: **PASS** — `mypy src` clean (47 source files, strict mode)
- tests: **PASS** — 50 passed, coverage 82% (≥80% target met)

#### Unified Findings

##### Critical (must fix)

- [SR-C1] **src/data/fetcher_oanda.py:31** — Hardcoded Oanda URL validation rejects any netloc other than `api-fxpractice.oanda.com`. The `base_url` constructor parameter creates false configurability. Will block live trading (Stage 8). — source: Red Team RC-1
  - **Impact:** Complete EUR/USD data pipeline failure when switching to live Oanda API.
  - **Remediation:** Validate against `self._base_url` netloc instead of hardcoded practice domain. Apply same fix to Binance (RL-1).

- [SR-C2] **src/api/v1/data.py:48,81** — Silent `except Exception:` blocks swallow ALL errors from database and candle age queries. No logging of exceptions. — source: Red Team RC-2
  - **Impact:** Database failures, credential errors, and schema corruption are invisible in production. Health endpoint reports "healthy: false" without diagnostic information.
  - **Remediation:** Add structured logging (`logger.exception()`) before returning default values.

##### High (deferred to target stages)

All high findings are in pre-governance code and are deferred to the stages where the affected code will be actively developed:

- [SR-H1] **src/trading/signal.py:235-239** — Signal threshold uses `>=` vs spec's `>`. — source: Red Team RH-1. **Target: Stage 2** (signal generators rewritten).
- [SR-H2] **src/api/v1/data.py:162-330** — API paths missing `/data/` prefix vs SPEC §8.1. — source: Red Team RH-2. **Target: Stage 6** (client UI consumes these endpoints).
- [SR-H3] **src/api/v1/data.py:105** — Hardcoded instrument list in HealthService. — source: Red Team RH-3. **Target: Stage 4** (trading engine wires config-driven instruments).
- [SR-H4] **src/api/v1/data.py:104** — Undocumented env var for health interval. — source: Red Team RH-4. **Target: Stage 4** (health endpoint enhanced for production).
- [SR-H5] **src/data/feature_provider.py:30-37** — FeatureProvider signature deviates from SPEC §3.6. — source: Red Team RH-5. **Target: Stage 2** (feature provider actively used).
- [SR-H6] **config/feature_providers.json:5** — Wrong Python module prefix (`newton.` vs `src.`). — source: Red Team RH-6. **Target: Stage 2** (dynamic provider loading implemented).

##### Medium (noted, no action required)

- [SR-M1] **src/trading/signal.py:98-99** — MLV1Generator inherits from BayesianV1 (DEC-005 violation). Scaffold code, rewritten in Stage 2. — source: Red Team RM-1
- [SR-M2] **src/trading/signal.py:110-112** — Ensemble weights not validated to sum to 1.0. — source: Red Team RM-2
- [SR-M3] **src/api/v1/data.py:194** — Raw exception strings in HTTP 500 responses. — source: Red Team RM-3
- [SR-M4] **src/api/v1/signals.py:14** — Module-level mutable state (`SignalRouter` not frozen). — source: Red Team RM-4, Code Review N-3
- [SR-M5] **src/data/fetcher_oanda.py:115, fetcher_binance.py:114** — Hardcoded instrument strings in normalization. — source: Red Team RM-5
- [SR-M6] **src/api/v1/data.py:162-168** — No instrument validation on data endpoints. — source: Red Team RM-6
- [SR-M7] **src/api/v1/data.py** — Missing `end` parameter on OHLCV endpoint. — source: Red Team RM-7
- [SR-M8] **src/trading/signal.py:244-262** — Action computed before probability clamping. — source: Red Team RM-8
- [SR-M9] **TASKS.md header** — Version reference says `0.1.0` but VERSION file is `0.1.3`. — source: Red Team RM-9
- [SR-M10] **src/app.py:12** — Hardcoded FastAPI version string. — source: Code Review W-1
- [SR-M11] **client/public/index.html:80** — Broken script reference to deleted `dist/main.js`. — source: Code Review W-2, Red Team RL-5

##### Low (noted)

- [SR-L1] **src/data/fetcher_binance.py:37** — Hardcoded Binance URL validation. — source: Red Team RL-1 (addressed alongside SR-C1)
- [SR-L2] **Duplicated store/protocol code** across fetcher modules. — source: Red Team RL-2, RL-3
- [SR-L3] **client/public/index.html:75** — Client references non-existent EMA/SMA indicators. — source: Red Team RL-4
- [SR-L4] **docker-compose.yml** — Deprecated `version` key; default dev password. — source: Red Team RL-6, RL-7
- [SR-L5] **Scaffold tests** assert only `True`. — source: Red Team RL-8
- [SR-L6] **MonkeyPatch pattern** in test_indicators_provider.py. — source: Code Review N-1, Red Team RL-9

#### Test Gap Summary

- [SR-TG1] **Fetcher HTTP clients** — No tests for real HTTP interactions (timeouts, SSL, rate limiting). — source: Red Team TG-1, TG-2. Target: Stage 4.
- [SR-TG2] **Data API endpoints** — No unit or integration tests for OHLCV/features endpoints. — source: Red Team TG-3, TG-4. Target: Stage 6.
- [SR-TG3] **Signal threshold boundaries** — No tests for probability exactly at thresholds. — source: Red Team TG-5. Target: Stage 2.
- [SR-TG4] **Edge cases** — Empty candle list, zero-volume candles, negative prices untested. — source: Red Team TG-6, TG-7. Target: Stage 2.
- [SR-TG5] **Registry/signal edge cases** — Register-after-freeze, unknown generator, invalid instrument 404. — source: Red Team TG-8, TG-9. Target: Stage 2.

#### Contradictions Between Reviews

None — reviews are consistent. The code review found no critical issues; the red team found 2 criticals and 6 highs, all in pre-governance code. The reviews agree on quality gate results and positive observations.

#### User Interview Notes

- User confirmed all critical and high findings are in pre-governance code, not Stage 1 regressions.
- Decision: fix the 2 critical findings (SR-C1, SR-C2) as a single bundled FIX task. Defer 6 high findings to their natural target stages.
- High findings assigned specific target stages for traceability (Stage 2: signal/feature, Stage 4: trading engine/health, Stage 6: client API).
- No additional issues from manual testing.

#### Positive Observations

Consolidated from both reviews:
1. **SQL injection prevention** — all queries use parameterized `%s` placeholders. Zero string interpolation in SQL.
2. **Frozen dataclasses** — all domain models consistently use `@dataclass(frozen=True)` per DEC-010.
3. **Timezone discipline** — all datetimes use `tz=UTC` with `require_utc()` guards in data paths.
4. **Configuration validation** — Pydantic v2 schemas with cross-field validators and `extra="forbid"`.
5. **Indicator parity** — TA-Lib reference comparison within 0.01% deviation across 512 candles.
6. **Signal fallback chain** — correctly implemented and tested including neutral fail-safe path.
7. **Clean quality gate** — ruff and mypy pass with zero issues. 50 tests at 82% coverage.
8. **Stage 1 execution** — all 3 baseline audit High findings (BA-H1, BA-H2, BA-H3) resolved. All task acceptance criteria met.

#### Remediation Tasks

| ID | Task | Scope | Acceptance | Status |
|---|---|---|---|---|
| T-103-FIX1 | Fix hardcoded URL validation in fetchers and add exception logging to health checks | server | Oanda fetcher validates against configured `self._base_url` netloc, not hardcoded practice domain; Binance fetcher applies same fix for testnet compatibility; health check `except` blocks log exceptions via `logger.exception()` before returning defaults; existing tests still pass; new tests verify URL validation accepts configured base URLs | TODO |

#### Verdict

**NOT READY** — Two critical findings require remediation before the stage gate. One FIX task (T-103-FIX1) bundles both fixes. After the fix is shipped and verified, the stage gate can proceed. All high findings are deferred to their target stages with documented traceability.

### Fix Verification

- **Date:** 2026-03-03
- **Status:** PASS

#### Verified Fixes

| Fix Task | Original Finding | Status | Notes |
|---|---|---|---|
| T-103-FIX1 (SR-C1) | SR-C1 — Hardcoded Oanda URL validation | **PASS** | `fetcher_oanda.py:31` now validates against `urlparse(self._base_url).netloc` instead of hardcoded `api-fxpractice.oanda.com`. Live URL `api-fxtrade.oanda.com` accepted. Test `test_oanda_url_validation_accepts_configured_base_url` confirms. Mismatched netloc still rejected (`test_oanda_url_validation_rejects_mismatched_netloc`). |
| T-103-FIX1 (SR-C1/SR-L1) | SR-L1 — Hardcoded Binance URL validation | **PASS** | `fetcher_binance.py:37` applies identical fix. Testnet URL `testnet.binance.vision` accepted. Test `test_binance_url_validation_accepts_configured_base_url` confirms. Mismatched netloc rejected (`test_binance_url_validation_rejects_mismatched_netloc`). |
| T-103-FIX1 (SR-C2) | SR-C2 — Silent exception swallowing in health checks | **PASS** | `data.py:52` now calls `logger.exception("Database health check failed")` before returning `False`. `data.py:86` calls `logger.exception("Candle age query failed")` before returning defaults. Test `test_health_check_database_logs_exceptions` verifies log output contains "database" or "health" when DB connection fails. |

#### Quality Gate

- lint: **PASS** — `ruff check .` all checks passed
- types: **PASS** — `mypy src` no issues in 47 source files
- tests: **PASS** — 55 passed, coverage 85% (up from 82% pre-fix)

#### New Issues Found

None — fixes are clean. No new linting errors, type errors, or test regressions. Coverage improved by 3% due to 5 new tests added with the fix.

#### Verdict

**PASS** — Both critical findings (SR-C1, SR-C2) are fully resolved. URL validation now dynamically validates against configured `base_url` in both fetchers. Health check exception logging is in place with structured `logger.exception()` calls. All 55 tests pass with 85% coverage. Stage report can be reconsidered for approval.

---

## Stage 2: Event Detection & Tokenization

### Code Review

- **Date:** 2026-03-03
- **Scope:** Full Stage 2 — all 6 implementation tasks (T-201 through T-206) on `stage/2-event-detection`

#### Stage 1 Deferred Finding Resolution

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

#### Findings

##### Critical

_None._

##### Warning

- [W-1] **src/trading/signal.py:122-131** — `generate_batch()` calls `generate()` per snapshot without passing `previous_features` to the tokenizer. Crossover, rising, and falling classification rules (10 of 22 tokens per instrument) will never activate in batch mode. This is documented as intentional for Stage 2 (sequential context deferred to orchestration layer), but batch-generated signals will be systematically less informative than single-call signals with history. Recommend adding a comment in `generate_batch` documenting this limitation and its target resolution stage.

- [W-2] **src/analysis/bayesian.py:268-303** — K-fold cross-validation in `_out_of_fold_predictions` splits data by index position, not by time. If token sets are not chronologically ordered, fold boundaries may leak future data into training folds. In practice, `_align_data` preserves insertion order from `token_sets`, which typically follows candle timestamps. Adding an explicit sort-by-time before splitting would make this guarantee explicit.

- [W-3] **src/trading/signal.py:87-88** — No runtime type validation on `config.parameters["model"]` and `config.parameters["rules"]`. Since `config.parameters` is `dict[str, Any]`, passing incorrect types (e.g., a dict instead of `BayesianModel`) would produce a confusing `AttributeError` deep inside `predict()`. An `isinstance` guard would improve error diagnostics.

##### Note

- [N-1] **src/trading/signal.py:83-120** — `BayesianV1Generator.generate()` does not log which inference path is taken (Bayesian engine vs scaffold fallback). A debug-level log entry would aid production tracing.

- [N-2] **src/analysis/bayesian.py:393** — `return cal_y[-1]` at end of `_apply_calibration` is unreachable when `cal_x[0] < raw < cal_x[-1]` (the for-loop always finds a matching interval). Defensive but dead code. Coverage correctly reports it as uncovered.

- [N-3] **src/analysis/events.py:82-95** — Event labeling checks `future.high` for UP events and `future.low` for DOWN events, which is more sensitive than using `future.close`. This is arguably correct (detects if the level was _reached_ at any point) but differs from some common implementations that use close-to-close returns. The behavior matches the docstring, so this is informational.

- [N-4] **Classification config** — Both `EUR_USD_classifications.json` and `BTC_USD_classifications.json` have identical rule structures (22 tokens each) with only instrument prefix and ATR thresholds differing. If additional instruments are added, this pattern could be template-generated. Low priority for 2 instruments.

#### Spec Compliance

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

#### Task Acceptance Verification

| Task | Criteria Met | Notes |
|------|-------------|-------|
| T-201 | ✅ All met | 6 deferred findings resolved; threshold boundary tests; registry edge cases; ensemble weight validation |
| T-202 | ✅ All met | Event labeling with forward-looking windows; both instruments; frozen `EventLabel`; 17 tests |
| T-203 | ✅ All met | 10 condition types; 22 rules per instrument; frozen `TokenSet`; 41 tests; real config integration |
| T-204 | ✅ All met | MI scoring, Jaccard dedup, top-N capped at 50; INFO logging; 23 tests |
| T-205 | ✅ All met | Laplace smoothing, log-odds, isotonic calibration, posterior cap, phi correlation; 37 tests |
| T-206 | ✅ All met | BayesianV1Generator rewritten with tokenize→predict path; scaffold fallback retained; DEC-013; feature_providers.json fixed; data-layer edge cases; 16 tests |

#### Quality Gate

- lint: **PASS** — `ruff check .` all checks passed
- types: **PASS** — `mypy src` no issues in 47 source files (strict mode)
- tests: **PASS** — 218 passed in 0.71s — coverage 89% global (≥80% target met)

#### Coverage by Stage 2 Module

| Module | Stmts | Miss | Cover |
|--------|-------|------|-------|
| `src/analysis/events.py` | 50 | 0 | 100% |
| `src/analysis/tokenizer.py` | 76 | 0 | 100% |
| `src/analysis/token_selection.py` | 104 | 0 | 100% |
| `src/analysis/bayesian.py` | 169 | 4 | 98% |
| `src/trading/signal.py` | 140 | 8 | 94% |
| `src/analysis/signal_contract.py` | 32 | 0 | 100% |

Stage 2 modules average **98.5% coverage**. Uncovered lines are defensive fallbacks (bayesian.py:235,293,379,393) and scaffold generators (signal.py:65,141,159,170,175,196,257,274 — MLV1/Ensemble/Router paths deferred to Stage 3).

#### Positive Observations

1. **Excellent test depth:** 168 new tests added across Stage 2 (50 → 218). All Stage 2 core modules at 94–100% coverage.
2. **Frozen dataclasses throughout:** `EventDefinition`, `EventLabel`, `ClassificationRule`, `TokenSet`, `TokenScore`, `SelectedTokenSet`, `TokenLikelihood`, `BayesianModel`, `CorrelationWarning` — all immutable per DEC-010.
3. **Numerically stable Bayesian engine:** Log-odds form prevents underflow; sigmoid handles extreme values; Laplace smoothing prevents log(0); posterior cap prevents overconfidence.
4. **Clean PAVA implementation:** Isotonic calibration via pool-adjacent-violators is a solid, well-understood algorithm. No external dependency needed.
5. **Config-driven token vocabulary:** Classification rules externalized to JSON, loaded at runtime. Adding new indicator tokens requires only config changes.
6. **Dual-path generator design:** BayesianV1Generator cleanly supports both real inference (model+rules) and scaffold fallback, with metadata indicating which path was used (`"source": "bayesian_engine"` vs `"source": "threshold"`).
7. **All Stage 1 deferred findings resolved:** 9 findings targeted at Stage 2 — all addressed with tests confirming the fixes.
8. **Decision log maintained:** DEC-013 properly documents the FeatureProvider sync batch signature deviation from SPEC §3.6 with clear rationale.

#### Verdict

**Ready for merge.** No critical or blocking issues. Three warnings are documented design decisions (batch crossover limitation, fold ordering, type validation) — none are regressions. All 6 task acceptance criteria fully met. SPEC §5.1–5.5 compliance verified. Quality gate passes with 218 tests at 89% coverage. Stage 2 modules average 98.5% coverage.

### Red Team Review

- **Date:** 2026-03-03
- **Reviewer:** Adversarial Subagent (fresh context)
- **Scope:** Stage 2: Event Detection & Tokenization — full codebase on `stage/2-event-detection`

#### Quality Gate

- lint: **PASS** — `ruff check .` all checks passed
- types: **PASS** — `mypy src` no issues in 47 source files (strict mode)
- tests: **PASS** — 218 passed, coverage 89%

#### Critical

- [RC-1] **src/analysis/events.py:88-95** — Event labeling uses high/low watermark scanning instead of close-to-close forward return. Subagent claims SPEC §4.6 requires `(close[T+N] - close[T]) / close[T] >= X/100` (close-to-close measurement, NOT high-watermark). Implementation checks `future.high >= ref_close * (1 + threshold)` for UP events and `future.low <= ref_close * (1 - threshold)` for DOWN events, scanning any candle within the horizon. Subagent claims this systematically produces more optimistic labels, corrupting all downstream training. **Note:** Requires verification against actual SPEC §4.6 text — subagent may be referencing a section that specifies different semantics than what was implemented per task acceptance.

- [RC-2] **src/trading/signal.py:92-98** — `BayesianV1Generator.generate()` never passes `previous_features` to `tokenize()`, silently disabling 8 of 22 classification rules per instrument (36%): 4 `cross_above_val`/`cross_below_val`, 2 `cross_above`/`cross_below`, 2 `rising`/`falling`. Creates train/serve skew if training data had previous features available. Impact: severely limited token vocabulary in production inference path.

#### High

- [RH-1] **src/trading/signal.py:97** — `close=features.values.get("_close", 0.0)` defaults to 0.0 when `_close` is missing from features. This causes BB band tokens (`BB2020_CL_BLW_LWR`) to always fire and (`BB2020_CL_ABV_UPR`) to never fire. Two of 22 tokens per instrument produce incorrect results.

- [RH-2] **src/trading/signal.py:223-227** — Generator override in `route_signal` creates a new `InstrumentRouting` with default thresholds (0.65/0.55/0.40) instead of preserving instrument-specific thresholds. BTC_USD (0.60/0.50/0.45) produces wrong action labels when override is used.

- [RH-3] **src/trading/signal.py:320-321** — `_build_signal` calls `_action_from_probability` with hardcoded default thresholds. When `generate_batch()` is used directly (backtesting path per SPEC §5.2.4), signals use default thresholds regardless of instrument. Creates backtest-to-live action divergence for BTC_USD.

- [RH-4] **src/analysis/events.py:31-38** — `EventLabel` dataclass only has `event_type`, `time`, `label`. Subagent claims SPEC §4.2 events table requires additional fields: `lookforward_periods`, `price_at_signal`, `price_at_resolution`. These fields are not captured, making database persistence impossible without data model changes.

- [RH-5] **src/analysis/events.py** — SPEC §4.6 specifies `min_occurrences` validation (default 100) with alert logging. Not implemented — system proceeds without warning on rare events with insufficient training data.

#### Medium

- [RM-1] **src/analysis/bayesian.py:268-303** — K-fold CV for calibration splits by index position, not time. Could introduce look-ahead bias into calibration function. SPEC says "out-of-fold predictions" without specifying time ordering. Recommend time-ordered folds.

- [RM-2] **src/trading/signal.py:28-52** — `GeneratorRegistry._frozen` flag and `_generators` dict have no locking. Race between `register()` and `freeze()` theoretically possible under concurrent access. In practice unlikely since boot precedes ASGI server. Recommend `MappingProxyType` after freeze.

- [RM-3] **src/api/v1/signals.py:14** — `SignalRouter` uses `@dataclass` (not frozen), is module-level mutable global state shared across API requests. Inconsistent with DEC-010. No current mutation, but not defensively immutable.

- [RM-4] **src/analysis/bayesian.py:367** — Isotonic calibration uses block midpoints instead of boundary values. Reduces calibration resolution for wide PAVA blocks.

- [RM-5] **src/analysis/events.py:17** — Event regex `\d+` only matches integer thresholds. Events like `1.5PCT` would fail to parse. Current events are integer-only (1, 3), but limits extensibility.

#### Low

- [RL-1] **src/trading/signal.py** — Duplicate action computation: `_build_signal` computes action with defaults, then `route_signal` overwrites with instrument thresholds via `replace()`.

- [RL-2] **src/analysis/token_selection.py:76-84** — MI inner loop iterates all vocab per token set: O(|token_sets| * |vocab|). Acceptable at current scale (~572k iterations) but scales poorly.

- [RL-3] **src/analysis/token_selection.py:173** — SPEC §5.4 step 5 requires logging correlation matrix during token selection. Implementation only logs token list and MI scores; phi correlation check is in bayesian.py at training time.

- [RL-4] **src/analysis/events.py:76-103** — `label_events` is O(n * h) where h is horizon in periods. Acceptable but should document complexity.

#### Test Gaps

- [TG-1] **events.py** — No test verifying close-to-close vs high-watermark labeling behavior. Tests validate current (watermark) behavior.
- [TG-2] **signal.py:BayesianV1Generator** — No test for `previous_features` in inference path. Tests only use `below`/`above` conditions.
- [TG-3] **signal.py:BayesianV1Generator** — No test for `_close=0.0` fallback corrupting BB tokens.
- [TG-4] **signal.py:generate_batch** — No test for previous_features propagation between snapshots.
- [TG-5] **signal.py:route_signal** — No test for generator override threshold regression.
- [TG-6] **tokenizer.py:load_classifications** — No test for malformed classification JSON.
- [TG-7] **events.py:label_events** — No test for unsorted candle input.

#### Positive Observations

1. Frozen dataclasses consistently used — all domain models per DEC-010.
2. Numerically stable sigmoid with dual-branch approach; prior clamped to [1e-10, 1-1e-10].
3. Laplace smoothing correctly implemented with `(count + alpha) / (total + 2*alpha)`.
4. Comprehensive threshold boundary tests with strict `>` comparisons per SPEC §5.7.
5. Jaccard dedup greedy and correct — MI-ranked order, checks against already-selected.
6. Phi correlation check with graduated warnings matching SPEC §5.5.
7. No security issues found — parameterized queries, no subprocess calls, no bare excepts.
8. 89% code coverage exceeds 80% target.

#### Verdict

**FAIL** — Two critical findings (RC-1: event labeling semantics, RC-2: missing previous_features) must be addressed. RC-1 may corrupt all downstream training data. RC-2 silently disables 36% of the token vocabulary. High findings RH-1 through RH-5 should also be addressed.

### Stage Report

- **Date:** 2026-03-04
- **Status:** APPROVED
- **Sign-off:** 2026-03-04

#### Quality Gate Summary

- lint: **PASS** — `ruff check .` clean
- types: **PASS** — `mypy src` clean (47 source files, strict mode)
- tests: **PASS** — 218 passed, coverage 89% (≥80% target met)

#### Unified Findings

##### Critical (must fix)

_None._ Both red team critical findings were reclassified per user interview (see User Interview Notes).

##### High (must fix — FIX task)

- [SR-H1] **src/trading/signal.py:97** — Default `close=0.0` when `_close` missing from features silently corrupts Bollinger Band token evaluations. `BB2020_CL_BLW_LWR` always fires, `BB2020_CL_ABV_UPR` never fires. — source: Red Team RH-1
  - **Impact:** 2 of 22 tokens per instrument produce incorrect results when `_close` is absent from FeatureSnapshot.
  - **Remediation:** Require `_close` in features or raise a clear error. Add test for missing `_close`.

- [SR-H2] **src/trading/signal.py:223-227** — Generator override in `route_signal` creates `InstrumentRouting` with default thresholds (0.65/0.55/0.40) instead of preserving instrument-specific thresholds. — source: Red Team RH-2
  - **Impact:** BTC_USD (thresholds 0.60/0.50/0.45) produces wrong action labels when generator override is used.
  - **Remediation:** Copy thresholds from `self.routing[instrument]` when creating override routing.

- [SR-H3] **src/trading/signal.py:320-321** — `_build_signal` calls `_action_from_probability` with hardcoded default thresholds. `generate_batch()` signals use EUR_USD defaults regardless of instrument. — source: Red Team RH-3
  - **Impact:** Backtest-to-live action divergence for BTC_USD when using batch-generated signals.
  - **Remediation:** Pass instrument-specific thresholds through the generation path or accept thresholds as parameter in `_build_signal`.

##### High (deferred to target stages)

- [SR-H4] **src/trading/signal.py:92-98** — `BayesianV1Generator.generate()` never passes `previous_features` to `tokenize()`, disabling 8 of 22 classification rules (crossover, rising, falling). Training also lacks previous_features, so no train/serve skew exists. Symmetrical limitation. — source: Red Team RC-2, Code Review W-1. **Target: Stage 3/5** (orchestration pipeline).

- [SR-H5] **src/analysis/events.py:31-38** — `EventLabel` dataclass missing `lookforward_periods`, `price_at_signal`, `price_at_resolution` fields required by SPEC §4.2 events table schema. Not needed for in-memory training pipeline. — source: Red Team RH-4. **Target: Stage 5** (backtesting with DB persistence).

- [SR-H6] **src/analysis/events.py** — SPEC §4.6 `min_occurrences` validation (default 100) with alert logging not implemented. Not needed for in-memory training; becomes relevant when training on real historical data. — source: Red Team RH-5. **Target: Stage 5** (backtesting).

##### Medium (noted, no action required)

- [SR-M1] **src/analysis/events.py:88-95** — Event labeling uses high-watermark scanning instead of SPEC §4.6 close-to-close return. User decision: keep current approach, make configurable in future strategy config. To be recorded as DEC-014. — source: Red Team RC-1, Code Review N-3
- [SR-M2] **src/analysis/bayesian.py:268-303** — K-fold CV splits by index, not time. Could introduce look-ahead bias into calibration. SPEC says "out-of-fold" without requiring time ordering. — source: Red Team RM-1, Code Review W-2
- [SR-M3] **src/trading/signal.py:28-52** — GeneratorRegistry freeze mechanism not thread-safe. Boot precedes ASGI server in practice. — source: Red Team RM-2
- [SR-M4] **src/api/v1/signals.py:14** — SignalRouter is mutable `@dataclass`, module-level global. Inconsistent with DEC-010. — source: Red Team RM-3, Stage 1 RM-4
- [SR-M5] **src/analysis/bayesian.py:367** — Isotonic calibration uses block midpoints instead of boundary values. — source: Red Team RM-4
- [SR-M6] **src/analysis/events.py:17** — Event regex integer-only (`\d+`). Limits extensibility for decimal thresholds. — source: Red Team RM-5
- [SR-M7] **src/trading/signal.py:87-88** — No runtime type validation on `config.parameters["model"]` and `config.parameters["rules"]`. — source: Code Review W-3

##### Low (noted)

- [SR-L1] **src/trading/signal.py** — Duplicate action computation in `_build_signal` then `route_signal`. — source: Red Team RL-1
- [SR-L2] **src/analysis/token_selection.py:76-84** — MI inner loop O(|token_sets| × |vocab|). Acceptable at current scale. — source: Red Team RL-2
- [SR-L3] **src/analysis/token_selection.py:173** — SPEC §5.4 step 5 correlation matrix logging in token_selection; phi check in bayesian.py instead. — source: Red Team RL-3
- [SR-L4] **src/analysis/events.py:76-103** — `label_events` O(n × h). Acceptable. — source: Red Team RL-4

#### Test Gap Summary

- [SR-TG1] **signal.py:BayesianV1Generator** — No test for `previous_features` in inference path. Deferred with SR-H4. — source: Red Team TG-2, TG-4
- [SR-TG2] **tokenizer.py:load_classifications** — No test for malformed classification JSON. Minor robustness gap. — source: Red Team TG-6
- [SR-TG3] **events.py:label_events** — No test for unsorted candle input. — source: Red Team TG-7

Note: TG-3 (_close=0.0 fallback) and TG-5 (override thresholds) will be covered by the FIX task tests.

#### Contradictions Between Reviews

One contradiction identified and resolved:

- **Event labeling (RC-1):** Code review noted high/low watermark as N-3 (informational, "behavior matches the docstring"). Red team flagged as RC-1 (critical spec violation). Resolution: The SPEC §4.6 text is unambiguous ("NOT a high-watermark measurement"), but the user considers the labeling method a strategy-dependent design choice. Reclassified as Medium with DEC-014 recording the deviation. Future: make configurable per strategy.

All other findings are consistent between reviews. Both reviews agree on quality gate results and positive observations.

#### User Interview Notes

- **RC-1 (event labeling):** User considers the labeling method (close-to-close vs high-watermark) a strategy-dependent design decision, not a fixed spec requirement. High-watermark approach should be retained for now. Will be made configurable per strategy in a future stage. Record as DEC-014.
- **RC-2 (previous_features):** User confirmed no train/serve skew exists since both training and inference lack previous_features. Downgraded to High, deferred to Stage 3/5 when orchestration pipeline provides sequential context.
- **RH-1 (close=0.0):** Bundle into FIX task — require `_close` or raise error.
- **RH-2/RH-3 (thresholds):** Fix now — bundle into FIX task. Important for backtest accuracy.
- **RH-4/RH-5 (EventLabel fields, min_occurrences):** Defer both to Stage 5 (backtesting). Not needed for in-memory training pipeline.
- **No additional issues** reported from manual testing. User is confident in Stage 2 code.

#### Positive Observations

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

#### Remediation Tasks

| ID | Task | Scope | Acceptance | Status |
|---|---|---|---|---|
| T-206-FIX1 | Fix default close fallback and action threshold inconsistencies in signal generators | server | (1) `BayesianV1Generator.generate()` raises `RecoverableSignalError` when `_close` is missing from `features.values` and model+rules are present; test confirms BB tokens are not silently corrupted. (2) Generator override in `route_signal` preserves instrument-specific thresholds from `self.routing[instrument]`; test confirms BTC_USD override uses 0.60/0.50/0.45. (3) `generate_batch()` signals use instrument-appropriate thresholds (or thresholds are passed through config); test confirms BTC_USD batch signals differ from EUR_USD defaults. (4) DEC-014 recorded for event labeling high-watermark approach. (5) Quality gate passes. | TODO |

#### Verdict

**NOT READY** — Three High findings (SR-H1, SR-H2, SR-H3) require remediation before the stage gate. One FIX task (T-206-FIX1) bundles all three fixes plus DEC-014. Three additional High findings (SR-H4, SR-H5, SR-H6) are deferred to their target stages with documented traceability. After the fix is shipped and verified, the stage gate can proceed.

### Fix Verification

- **Date:** 2026-03-04
- **Status:** PASS

#### Verified Fixes

| Fix Task | Original Finding | Status | Notes |
|---|---|---|---|
| T-206-FIX1 (SR-H1) | `close=0.0` default corrupts BB tokens | PASS | `BayesianV1Generator.generate()` now raises `RecoverableSignalError("_close required in features for Bayesian inference")` when `_close` is missing and model+rules are present (line 94-97). Scaffold fallback path unchanged — does not require `_close`. Verified by 3 tests in `TestCloseRequiredForInference`. |
| T-206-FIX1 (SR-H2) | Generator override uses default thresholds | PASS | `route_signal` override path now copies `strong_buy_threshold`, `buy_threshold`, `sell_threshold` from `self.routing[instrument]` (line 233-244). BTC_USD with prob 0.53 correctly returns BUY (>0.50) instead of NEUTRAL. Verified by `test_generator_override_preserves_btc_thresholds` and `test_generator_override_does_not_use_default_thresholds`. |
| T-206-FIX1 (SR-H3) | `generate_batch` uses hardcoded thresholds | PASS | New `_extract_thresholds()` helper (line 362-367) extracts thresholds from `config.parameters["thresholds"]`. `_build_signal()` accepts optional `thresholds` kwarg (line 335). All three generators (BayesianV1, MLV1, EnsembleV1) pass thresholds through. Verified by `test_batch_signal_uses_config_thresholds` and `test_batch_signal_without_thresholds_uses_defaults`. |
| T-206-FIX1 (DEC-014) | Event labeling spec deviation | PASS | DEC-014 recorded in DECISIONS.md documenting high-watermark approach and future configurability plan. |

#### Quality Gate
- lint: PASS — `ruff check .` clean
- types: PASS — `mypy src` clean (47 source files)
- tests: PASS — 225 passed, coverage 89%

#### Regression Check
- All 225 tests pass (218 pre-existing + 7 new)
- No new linting or type errors introduced
- `signal.py` coverage increased from 94% to 95%
- No regressions in signal routing, Bayesian inference, or ensemble generation paths

#### New Issues Found
None — fixes are clean.

#### Verdict
**PASS**

All three High findings (SR-H1, SR-H2, SR-H3) are resolved with targeted fixes and comprehensive test coverage. DEC-014 is properly recorded. No regressions detected. The stage can proceed to approval and the stage gate.

---

## Stage 3: ML Pipeline

### Code Review

- **Date:** 2026-03-04
- **Scope:** Full Stage 3 — T-301 through T-306 (feature engineering, model store, walk-forward, XGBoost, regime detection, meta-learner, EnsembleV1Generator rewrite)

#### Findings

##### Critical
_None._

##### Warning
_None._

##### Note
- [N-1] **src/analysis/meta_learner.py:80** Calibration error is computed on the same OOF data used to train the logistic regression. With only 4 parameters (3 coefficients + 1 intercept), overfitting risk is minimal, but a held-out evaluation split would be more rigorous. Acceptable for v1 given the low-parameter model.
- [N-2] **src/analysis/meta_learner.py:64** `train_meta_learner()` does not validate that all input tuples (`bayesian_posteriors`, `ml_probabilities`, `regime_confidences`, `labels`) have equal length. Length mismatch would cause a numpy error at `column_stack`, but an early explicit check would give a clearer error message.
- [N-3] **src/regime/detector.py:271-344** Pure Python ADX fallback parity test allows 30-point tolerance (`abs(talib_adx - python_adx) < 30`). This is generous — ADX ranges 0–100, so a 30-point difference could cross the 25 threshold. The test does verify both agree on trending vs ranging direction for synthetic data, which mitigates practical impact. Per DEC-006, parity tests are required; the tolerance is documented.
- [N-4] **src/analysis/model_store.py:67** `_deserialize_artifact()` uses `.replace(tzinfo=UTC)` which silently overrides any existing timezone info rather than converting. Since all timestamps are serialized from UTC, this round-trips correctly. Would be slightly more robust as `datetime.fromisoformat(...).astimezone(UTC)` but no practical impact.

#### Spec Compliance Assessment

| Module | SPEC Section | Status | Notes |
|--------|-------------|--------|-------|
| feature_engineering.py | §5.6 | PASS | OHLCV returns (not raw prices), configurable lookback, token flags |
| model_store.py | — | PASS | SHA-256 integrity, versioning, frozen dataclass |
| walk_forward.py | §5.6, §9.1 | PASS | Rolling window, embargo, min folds, OOF collection |
| xgboost_trainer.py | §5.6 | PASS | Optuna HPO, early stopping, AUC threshold, production model |
| detector.py | §5.8 | PASS | vol_30d, ADX_14, 4 labels, confidence formula, bands |
| meta_learner.py | §5.7, §9.5 | PASS | Logistic regression stacking, 3 inputs, 5pp calibration |
| signal.py (Ensemble) | §5.7 | PASS | Meta-learner path + weighted blend fallback |

#### Pattern Compliance

- All domain models frozen (DEC-010): `FeatureMatrix`, `FeatureVector`, `ModelArtifact`, `WalkForwardConfig`, `WalkForwardFold`, `FoldResult`, `WalkForwardResult`, `XGBoostHyperparameters`, `TrainingResult`, `RegimeState`, `MetaLearnerModel` ✓
- TA-Lib with pure Python fallback (DEC-006): ADX computation ✓
- Protocol abstractions (DEC-005): Generators satisfy `SignalGenerator` protocol ✓
- Registry + fallback chains (DEC-011): EnsembleV1Generator registered, supports fallback ✓
- Config-driven design: lookback periods, thresholds, min_samples all configurable ✓

#### Security
- No SQL queries in Stage 3 modules (pure computation) ✓
- No subprocess calls ✓
- No hardcoded secrets ✓
- sklearn/XGBoost/Optuna used as established libraries ✓

#### Test Coverage
- 377 tests, 91% global coverage
- Stage 3 module coverage: feature_engineering 100%, model_store 100%, walk_forward 99%, xgboost_trainer 96%, detector 96%, meta_learner 100%, signal.py 97%
- Edge cases covered: empty data, zero volume, insufficient history, missing features, threshold boundaries, frozen dataclass mutation
- Tests use specific assertions (not just `is not None`)
- XGBoost tests verify train→serialize→predict round-trip
- Meta-learner tests verify coefficient signs, boundary conditions, calibration logic

#### Quality Gate
- lint: PASS
- types: PASS
- tests: PASS — 377 passed, coverage 91%

#### Verdict
Ready for merge. No critical or warning findings. All SPEC acceptance criteria are met. The four notes are informational improvements that don't block the stage gate.

### Red Team Review

- **Date:** 2026-03-04
- **Reviewer:** Adversarial Subagent (fresh context)
- **Scope:** Stage 3 — ML Pipeline (T-301 through T-306)

#### Quality Gate
- lint: PASS
- types: PASS
- tests: PASS — 377 passed, coverage 91%

#### Critical
- [RC-1] **src/regime/detector.py:116** `np.log()` on close prices with no guard against zero or negative values — silent NaN propagation through vol_30d → regime classification → position sizing
- [RC-2] **src/analysis/feature_engineering.py:132,139** Missing indicator values silently default to 0.0 instead of NaN — XGBoost treats NaN as missing (correct), but 0.0 creates spurious correlations in training data

#### High
- [RH-1] **src/analysis/xgboost_trainer.py:137-145** AUC below threshold only logs warning; SPEC §5.6 requires disabling ML component and falling back to Bayesian-only — task acceptance criteria weaker than spec
- [RH-2] **src/analysis/xgboost_trainer.py:179** XGBoost model deserialized on every `predict_xgboost()` call — ~3.5x overhead in batch/backtest scenarios (26,000 deserializations per backtest)
- [RH-3] **src/analysis/model_store.py:46** No path sanitization on `instrument`/`model_type` parameters — latent path traversal if exposed to user input in future stages
- [RH-4] **src/analysis/meta_learner.py:79-83** Calibration evaluated on training data, not held-out data — SPEC §1.5/§9.5 requires "predicted vs. observed ±5pp per decile" which implies out-of-sample evaluation
- [RH-5] **src/trading/signal.py:71-72** `validate_config` always returns True (isinstance check on dict) — misconfigured generators silently fall to scaffold path

#### Medium
- [RM-1] **src/trading/signal.py:32-56** GeneratorRegistry uses instance methods; SPEC §5.2.2 specifies `@classmethod`
- [RM-2] **src/analysis/feature_engineering.py:61** `_safe_ret` function redefined inside loop body on every iteration — unnecessary overhead for large datasets
- [RM-3] **src/regime/detector.py:308-313** Wilder's smoothing docstring says "SMA" but computes a sum — misleading documentation (code is correct)
- [RM-4] **src/analysis/walk_forward.py** No validation that `step_periods` avoids test window overlap — OOF predictions could duplicate timestamps
- [RM-5] **src/analysis/xgboost_trainer.py:246** `n_estimators` hardcoded to 300 in HPO output — misleading when inspected (production model uses median best_iteration)
- [RM-6] **src/trading/signal.py:59-61** `_BaseGenerator` inheritance pattern diverges from DEC-005 (Protocol over inheritance)

#### Low
- [RL-1] **tests/unit/test_regime_detector.py:381** ADX parity test tolerance of 30 is overly generous (should be ~0.01)
- [RL-2] **src/analysis/model_store.py:67** `.replace(tzinfo=UTC)` may silently override non-UTC timezone
- [RL-3] **src/analysis/meta_learner.py:73** LogisticRegression regularization (C=1.0) is implicit, not documented
- [RL-4] **src/analysis/xgboost_trainer.py:62-71** `train_xgboost` has many parameters; consider grouping into config dataclass
- [RL-5] **src/analysis/walk_forward.py:19** Missing blank line between import block and logger assignment

#### Test Gaps
- [TG-1] **detector.py:compute_vol_30d** No test for zero or negative close prices
- [TG-2] **feature_engineering.py** No test for missing indicator keys at specific timestamps
- [TG-3] **xgboost_trainer.py** No test for constant labels (all 0 or all 1)
- [TG-4] **model_store.py** No test for concurrent save/load operations
- [TG-5] **meta_learner.py** No test for out-of-sample calibration
- [TG-6] **signal.py:EnsembleV1Generator** No test for meta-learner with extreme input values (0.0, 1.0)
- [TG-7] **xgboost_trainer.py** No test for NaN/Inf in feature matrix
- [TG-8] **detector.py:detect_regime** No test for vol_median very close to zero (but not exactly zero)

#### Positive Observations
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

#### Verdict
CONDITIONAL PASS — Two critical findings (RC-1, RC-2) should be addressed. Five high findings should be addressed or deferred with decision records. Overall architecture is solid, test coverage is strong, and core ML pipeline design is sound.

### Stage Report

- **Date:** 2026-03-04
- **Status:** APPROVED
- **Sign-off:** 2026-03-04

#### Quality Gate Summary
- lint: PASS
- types: PASS
- tests: PASS — 377 passed, coverage 91%

#### Unified Findings

##### Critical (must fix)

- [SR-C1] **src/regime/detector.py:116** `np.log()` on close prices without guard against zero or negative values — source: Red Team RC-1
  - **Impact:** Silent NaN propagation through vol_30d → regime classification → confidence bands → position sizing. A single zero price from data corruption or edge case produces NaN that flows undetected through the entire regime subsystem.
  - **Remediation:** Add `if np.any(window <= 0): raise ValueError(...)` before `np.log(window)`. Add test for zero/negative close prices.

- [SR-C2] **src/analysis/feature_engineering.py:132,139** Missing indicator values silently default to 0.0 instead of NaN — source: Red Team RC-2
  - **Impact:** XGBoost treats NaN as "missing" (correct behavior with native handling) but treats 0.0 as a real value. Substituting 0.0 for missing indicators (RSI ~50, OBV ~10000+) creates a spurious correlation that the model learns from, degrading out-of-sample performance with potentially incorrect trading signals.
  - **Remediation:** Use `float('nan')` as default for missing indicator and return values. Add test for missing indicator keys at specific timestamps.

##### High (should fix)

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

##### Medium (recommend)

- [SR-M1] **src/trading/signal.py:32-56** GeneratorRegistry uses instance methods; SPEC §5.2.2 specifies `@classmethod` — source: Red Team RM-1
- [SR-M2] **src/analysis/feature_engineering.py:61** `_safe_ret` redefined inside loop body on every iteration — source: Red Team RM-2
- [SR-M3] **src/regime/detector.py:308-313** Wilder's smoothing docstring says "SMA" but computes a sum — source: Red Team RM-3
- [SR-M4] **src/analysis/walk_forward.py** No validation that `step_periods` avoids test window overlap — source: Red Team RM-4
- [SR-M5] **src/analysis/xgboost_trainer.py:246** `n_estimators` hardcoded to 300 in HPO output — source: Red Team RM-5
- [SR-M6] **src/trading/signal.py:59-61** `_BaseGenerator` inheritance diverges from DEC-005 — source: Red Team RM-6

##### Low (noted)

- [SR-L1] **tests/unit/test_regime_detector.py:381** ADX parity test tolerance of 30 is overly generous — source: Red Team RL-1, Code Review N-3
- [SR-L2] **src/analysis/model_store.py:67** `.replace(tzinfo=UTC)` may silently override non-UTC timezone — source: Red Team RL-2, Code Review N-4
- [SR-L3] **src/analysis/meta_learner.py:73** LogisticRegression regularization implicit — source: Red Team RL-3
- [SR-L4] **src/analysis/meta_learner.py:64** Input tuple length not validated — source: Code Review N-2
- [SR-L5] **src/analysis/walk_forward.py:19** Missing blank line between imports and logger — source: Red Team RL-5

#### Test Gap Summary

- [SR-TG1] **detector.py:compute_vol_30d** No test for zero or negative close prices — source: Red Team TG-1
- [SR-TG2] **feature_engineering.py** No test for missing indicator keys at specific timestamps — source: Red Team TG-2
- [SR-TG3] **xgboost_trainer.py** No test for constant labels (all 0 or all 1) — source: Red Team TG-3
- [SR-TG4] **model_store.py** No test for concurrent save/load operations — source: Red Team TG-4
- [SR-TG5] **meta_learner.py** No test for out-of-sample calibration — source: Red Team TG-5
- [SR-TG6] **signal.py:EnsembleV1Generator** No test for meta-learner with extreme inputs (0.0, 1.0) — source: Red Team TG-6
- [SR-TG7] **xgboost_trainer.py** No test for NaN/Inf in feature matrix — source: Red Team TG-7
- [SR-TG8] **detector.py:detect_regime** No test for vol_median very close to zero — source: Red Team TG-8

#### Contradictions Between Reviews

The code review found no critical or warning findings ("Ready for merge"), while the red team found 2 critical and 5 high findings ("Conditional Pass"). This is expected — the code review focused on spec compliance and pattern consistency (which are strong), while the adversarial review probed edge cases, production resilience, and latent risks that only surface under unusual inputs or future API exposure. The red team's findings are well-substantiated and do not contradict the code review's positive assessments.

#### User Interview Notes

- **Criticals confirmed:** User agrees both RC-1 and RC-2 are valid criticals that should be fixed before the stage gate.
- **All highs to be fixed:** User wants all 5 high findings addressed before the gate (no deferrals).
- **No manual testing:** Automated test suite is the only validation so far. Manual testing will be discussed at stage completion.
- **No additional concerns:** No known technical debt or issues beyond the review findings.

#### Positive Observations

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

#### Remediation Tasks

| ID | Task | Scope | Acceptance | Status |
|---|---|---|---|---|
| T-306-FIX1 | Guard non-positive prices in regime detection and use NaN for missing indicator values | server | `compute_vol_30d()` raises `ValueError` when close prices contain zero or negative values; `_extract_row()` uses `float('nan')` instead of `0.0` for missing indicator/return values; tests for zero/negative closes and missing indicator keys at specific timestamps; quality gate passes | TODO |
| T-306-FIX2 | Enforce AUC threshold, implement validate_config, and evaluate calibration on held-out data | server | `train_xgboost()` returns `production_model_bytes=None` when `below_auc_threshold=True` (or MLV1Generator refuses below-threshold models); each generator's `validate_config` checks for required parameters and returns False when missing; `train_meta_learner()` evaluates calibration on held-out split (not training data); tests for AUC enforcement, config validation rejection, and held-out calibration; quality gate passes | TODO |
| T-306-FIX3 | Cache XGBoost deserialization and add path sanitization to model store | server | `predict_xgboost()` or `MLV1Generator` avoids redundant deserialization in batch scenarios; `model_store` validates `instrument`/`model_type` against `^[A-Za-z0-9_]+$` and raises ValueError on invalid input; tests for caching behavior and path traversal rejection; quality gate passes | TODO |

#### Verdict

**NOT READY**

Two critical findings (SR-C1: NaN propagation in regime detection, SR-C2: misleading ML training data) and five high findings require remediation before the stage gate. Three FIX tasks have been added to TASKS.md. The underlying architecture is solid — 91% test coverage, all domain models frozen, strong spec compliance — but these edge cases and spec gaps must be addressed to ensure production-grade reliability for a trading system.

### Fix Verification

- **Date:** 2026-03-04
- **Status:** PASS

#### Verified Fixes

| Fix Task | Original Finding | Status | Notes |
|---|---|---|---|
| T-306-FIX1 (SR-C1) | `np.log()` on close prices without guard against zero/negative | **PASS** | `compute_vol_30d()` at `detector.py:114` now checks `np.any(closes <= 0)` and raises `ValueError("non-positive price detected")` before `np.log(window)`. Tests `test_zero_price_raises` and `test_negative_price_raises` confirm both cases. |
| T-306-FIX1 (SR-C2) | Missing indicator values default to 0.0 instead of NaN | **PASS** | `_extract_row()` at `feature_engineering.py:127` uses `_NAN = float("nan")` as default for both `ret.get(field, _NAN)` (line 134) and `ind.get(key, _NAN)` (line 141). Tests `test_missing_indicator_produces_nan` and `test_missing_ohlcv_return_produces_nan` verify NaN propagation. |
| T-306-FIX2 (SR-H1) | AUC below threshold only logs warning; doesn't disable ML | **PASS** | `train_xgboost()` at `xgboost_trainer.py:149` sets `final_model_bytes = None if below else production_bytes`. `TrainingResult.production_model_bytes` typed as `bytes | None`. Test `test_below_auc_threshold_true_returns_none_model` verifies `result.production_model_bytes is None` when AUC < threshold. |
| T-306-FIX2 (SR-H4) | Calibration evaluated on training data, not held-out | **PASS** | `train_meta_learner()` at `meta_learner.py:73-88` splits data 80/20, trains on 80%, evaluates calibration on held-out 20%. `n_training_samples` reflects the train split count. Tests `test_calibration_evaluated_on_held_out_data` (n=500, expects 400 training samples) and `test_basic_training` (n=100, expects 80) confirm. |
| T-306-FIX2 (SR-H5) | `validate_config` always returns True | **PASS** | `MLV1Generator.validate_config()` at `signal.py:160-168` checks `model_bytes` and `feature_names` must appear together (partial config rejected). `EnsembleV1Generator.validate_config()` at `signal.py:243-250` validates `weights` must be a list of length 2. Seven tests in `TestValidateConfig` cover valid, scaffold, partial, and bad-weights cases for all three generators. |
| T-306-FIX3 (SR-H2) | XGBoost model deserialized on every predict call | **PASS** | `predict_xgboost()` at `xgboost_trainer.py:183-185` converts bytearray to bytes for hashability, then calls `_get_booster()` which is decorated with `@functools.lru_cache(maxsize=8)`. Test `test_cached_deserialization` verifies same object identity on second call and cache hits ≥ 1. |
| T-306-FIX3 (SR-H3) | No path sanitization on instrument/model_type | **PASS** | `model_store.py:40-48` defines `_SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")` and `_validate_path_component()`. Called from `_model_dir()` (line 57-58) for both `instrument` and `model_type`. Six tests verify rejection of `../etc`, `../../passwd`, `foo/bar`, `..`, and path traversal on load. |

#### Quality Gate
- lint: **PASS** — `ruff check .` all checks passed
- types: **PASS** — `mypy src` no issues in 51 source files
- tests: **PASS** — 397 passed, coverage 92%

#### Regression Check
- All 397 tests pass (377 pre-fix + 20 new)
- Coverage improved from 91% to 92%
- No new linting or type errors introduced
- No regressions in regime detection, feature engineering, XGBoost training, meta-learner, model store, or signal routing

#### New Issues Found
None — fixes are clean.

#### Verdict
**PASS**

All 7 findings (2 critical, 5 high) are fully resolved across 3 FIX tasks. Each fix has targeted test coverage verifying the specific behavior change. No regressions detected. The Stage Report can now be updated to APPROVED.

---

## Stage 4: UAT & Admin UI

### Code Review

- **Date:** 2026-03-05
- **Scope:** Full Stage 4 — T-401 through T-405 (React foundation, UAT API, UAT Runner UI, admin panels, UAT.md refresh)

#### Findings

##### Critical

- [C-1] **src/api/v1/models.py:46** Path traversal risk — `model_type` query parameter is not validated against `_MODEL_TYPES` before being passed to `list_versions()`, which constructs file paths. A malicious `model_type=../../etc` could probe the filesystem. The `model_store.py` has path sanitization (T-306-FIX3) but defense-in-depth requires validation at the API boundary too.

- [C-2] **src/api/v1/data.py:200,251,314,424** Information leakage — database exception messages are interpolated directly into HTTP 500 response details (`f"Failed to query OHLCV: {exc}"`). Database exceptions can contain connection strings, SQL fragments, or internal state. Should use generic error messages and log details server-side only.

##### Warning

- [W-1] **src/app.py:15** Version mismatch — FastAPI app declares `version="0.1.0"` while `VERSION` file is `0.4.5`. Should read from VERSION file dynamically.

- [W-2] **src/api/v1/regime.py:133** Incorrect step size comment — `step = 20` comment says "20 trading days" but for 1h bars this is 20 hours. The computation still produces a reasonable vol_median (sparse sampling of the available data), but the comment is misleading and the step should be ~720 (30 days × 24h) to match the "monthly recalculation" spec requirement (SPEC §5.8.2).

- [W-3] **src/api/v1/regime.py:92-93** Unhandled ValueError — `compute_vol_30d`/`compute_adx_14` can raise `ValueError` on non-positive prices in database data, producing unhandled 500 errors. Should be wrapped in try/except with fallback to `_unknown_regime`.

- [W-4] **src/api/v1/data.py:39%** Low test coverage — four complete API endpoints (`/ohlcv`, `/features/metadata`, `/features/{instrument}`, `/features/compute`) have zero test coverage. The `regime.py` endpoint (43%) only tests the "no database" fallback, not the core computation path.

- [W-5] **src/api/schemas.py** Loose typing — `UATTestResult.status`, `RegimeResponse.regime_label`, `RegimeResponse.confidence_band` use `str` instead of `Literal` types, weakening type safety and OpenAPI schema precision.

- [W-6] **client/src/pages/AdminPage.tsx:687** React Fragment key warning — `<>` used inside `.map()` without a key. Should use `<React.Fragment key={key}>` to avoid React console warning.

- [W-7] **client/index.html** Missing `class="dark"` on `<html>` element — shadcn/ui components include `dark:` variant styles (e.g., `dark:bg-input/30`, `dark:border-input`) that never activate because no `.dark` class exists in the DOM. The base theme is dark via CSS variables, but `dark:` refinements are dead code.

- [W-8] **client/src/pages/AdminPage.tsx:476** RegimeMonitor uses `Promise.all` — if either instrument's regime endpoint fails, both instruments show nothing. Should use `Promise.allSettled` for partial results.

- [W-9] **client/src/lib/api.ts:222** OHLCV client method broken — `interval` and `start` are required backend params but optional/missing in the client method. Any call would receive 422. Currently unused but latent bug.

##### Note

- [N-1] **src/app.py:25** UAT router is mounted unconditionally — in production, UAT test execution should be gated by environment or auth to prevent CPU exhaustion via repeated test runs.

- [N-2] **src/uat/runner.py:122** Full Python tracebacks returned in UAT `error` field — exposes file paths and internal code structure. Acceptable for dev, should be sanitized for production.

- [N-3] **src/api/v1/data.py:111,132** Hardcoded instrument list `["EUR_USD", "BTC_USD"]` and `kill_switch_active=False` in health check — should derive from config and actual system state respectively.

- [N-4] **client/src/pages/HealthPage.tsx** `kill_switch_active` field is fetched but never displayed — critical operational data for a trading system that should be prominent.

- [N-5] **client/src/App.tsx** No 404 catch-all route — navigating to `/foo` renders empty content area with sidebar. Should show a 404 component.

- [N-6] **client/src/pages/AdminPage.tsx:117,303** Silent error swallowing — metadata and generators load failures are caught and silently set to empty/null with no user feedback.

- [N-7] **client/vite.config.ts:32** Production sourcemaps enabled (`sourcemap: true`) — exposes TypeScript source. Acceptable for internal tool but should be disabled if ever externally accessible.

- [N-8] **tests/unit/test_uat_api.py:156,179,209** Hardcoded magic numbers (7 suites, 28 tests) — tests are brittle and will break if suites are added/removed. Test the framework logic, not the current count.

- [N-9] **client/src/pages/AdminPage.tsx:49,187,355,652** Native `<select>` dropdown `<option>` elements lack explicit dark mode styling — may render with browser default light theme on some platforms (Windows Chrome).

#### Quality Gate
- lint: PASS
- types: PASS
- tests: PASS — 429 passed, 91% coverage

#### Verdict
Ready for merge with conditions — 2 critical findings (path traversal, info leakage) should be addressed via fix tasks. The warnings are real but non-blocking for a localhost-only admin tool at this stage. Client code is clean with no XSS risks.

### Red Team Review

- **Date:** 2026-03-05
- **Reviewer:** Adversarial Subagent (fresh context)
- **Scope:** Full Stage 4 — UAT & Admin UI (T-401 through T-405), server + client + tests

#### Quality Gate
- lint: PASS
- types: PASS
- tests: PASS — 429 passed, 91% coverage
- client build: PASS

#### Critical

- [RC-1] **src/api/v1/data.py:200,251,314,424** Raw exception messages leaked to API clients — database connection failures could reveal full `DATABASE_URL` including credentials in HTTP 500 response bodies. Four endpoints affected. Violates SPEC 7.3 (secrets from env only) and 10.1 (no secrets in output).

#### High

- [RH-1] **src/api/v1/regime.py:72 + src/regime/detector.py** Regime volatility computed from hourly data with daily annualization factors — `sqrt(252)` and `sqrt(365)` are calibrated for daily returns, not hourly. Hourly returns produce volatility estimates ~4.9x too low, biasing regime classification toward `LOW_VOL_*` states. Pre-existing Stage 3 issue surfaced by Stage 4 admin UI.

- [RH-2] **src/api/v1/data.py:346-378** `compute_features` endpoint fetches entire OHLCV history without LIMIT — with 3 years of 1-minute data (~1.6M rows), this could cause memory exhaustion and server unresponsiveness.

- [RH-3] **client/src/lib/api.ts:222-228** Client `ohlcv` function signature mismatches server — `interval` and `start` are required on the server but optional/missing on the client. Any call produces 422. Broken API contract.

- [RH-4] **src/app.py:16** FastAPI version hardcoded to `"0.1.0"` while VERSION file is `0.4.5` — OpenAPI schema and Swagger UI report wrong version.

#### Medium

- [RM-1] **client/src/pages/AdminPage.tsx:687** React Fragment missing `key` prop in list rendering — can cause incorrect DOM reconciliation in ModelDashboard.

- [RM-2] **src/api/v1/models.py:46** `model_type` query parameter not validated against allowed list — inconsistent with `instrument` validation on line 42.

- [RM-3] **src/api/v1/data.py:169,273,346** Inconsistent instrument validation — `get_ohlcv`, `get_features`, `compute_features` accept any string without validation, unlike regime and models endpoints.

- [RM-4] **src/api/v1/uat.py:23** Module-level UAT runner instantiation eagerly imports all suite dependencies (numpy, xgboost, sklearn) at server startup — adds startup time/memory even if UAT is never used.

- [RM-5] **src/api/v1/uat.py:38** UAT run endpoint lacks rate limiting or concurrency control — multiple concurrent requests could overload server with CPU-intensive ML tests.

#### Low

- [RL-1] **src/api/v1/data.py:132** `kill_switch_active` hardcoded to `False` — acceptable for Stage 4 but must be wired to actual state in Stage 5+.

- [RL-2] **src/api/v1/data.py:71** N+1 query pattern in `_query_last_candle_ages` — separate query per instrument, could be a single grouped query.

- [RL-3] **client/src/components/ErrorBoundary.tsx:23** `console.error` in production — appropriate for error boundaries but consider structured reporting.

- [RL-4] **client/src/pages/AdminPage.tsx:287** Feature table silently truncates to last 50 timestamps — no user-visible indicator of truncation.

- [RL-5] **src/api/v1/regime.py:129-142** Inefficient rolling vol computation — creates progressively larger array copies at each step. Could pass only the necessary window.

- [RL-6] **src/api/v1/data.py:43,63,180,237,289,357** psycopg imported inside function bodies — adds import overhead on every request. Consider module-level import with try/except guard.

#### Test Gaps

- [TG-1] **POST /api/v1/features/compute** No tests at all — a write endpoint that modifies DB state has zero coverage.

- [TG-2] **GET /api/v1/ohlcv, GET /api/v1/features** No dedicated tests — missing validation error (422), missing DATABASE_URL, response shape tests.

- [TG-3] **Admin panel client components** No frontend tests for FeatureExplorer, SignalInspector, RegimeMonitor, ModelDashboard.

- [TG-4] **POST /api/v1/uat/run** No test for `test_id` and `suite` both provided simultaneously — current behavior (prioritize `test_id`) is undocumented and untested.

- [TG-5] **client/src/lib/api.ts** No tests for API timeout or malformed JSON responses.

#### Positive Observations

1. Clean quality gate: 429 tests, 91% coverage, zero lint/type errors, client builds cleanly with TypeScript strict mode.
2. Well-structured UAT framework: frozen dataclasses, clean separation of runner and suites, proper error handling distinguishing assertion failures from unexpected errors.
3. Good client error handling: typed `ApiError`, network failure catches, graceful 502 proxy response.
4. Consistent dark mode: all components use Tailwind dark mode classes with semantic color badges.
5. SQL injection prevention: all queries use parameterized `%s` placeholders throughout.
6. Path traversal protection: `model_store.py` validates with `^[A-Za-z0-9_-]+$` regex.
7. Good error boundary: React `ErrorBoundary` with recovery mechanism.

#### Verdict
**CONDITIONAL PASS** — RC-1 (exception leakage) must be fixed. RH-1 (regime vol computation) is pre-existing Stage 3 and should be tracked separately. RH-3 (broken OHLCV client) and RH-4 (version mismatch) are straightforward Stage 4 fixes. The codebase demonstrates solid engineering: parameterized SQL, frozen dataclasses, typed APIs, comprehensive UAT coverage. Issues are primarily in the integration layer (API validation consistency, error message handling) rather than core logic.

### Stage Report

- **Date:** 2026-03-05
- **Status:** APPROVED
- **Sign-off:** 2026-03-05

#### Quality Gate Summary
- lint: PASS
- types: PASS
- tests: PASS — 429 passed, 91% coverage
- client build: PASS

#### Unified Findings

##### Critical (must fix)

- [SR-C1] **src/api/v1/data.py:200,251,314,424** Exception message leakage in HTTP 500 responses — source: both (C-2 + RC-1)
  - **Impact:** Database exceptions can expose `DATABASE_URL` credentials, SQL fragments, and internal state in API response bodies. Violates SPEC 7.3 and 10.1.
  - **Remediation:** Replace `{exc}` interpolation with generic error messages. Log full exception server-side only (already done via `logger.exception` in some handlers). Apply to all 4 affected endpoints.

- [SR-C2] **src/api/v1/models.py:46** `model_type` query parameter not validated at API boundary — source: both (C-1 + RM-2)
  - **Impact:** Unvalidated user input passed to `list_versions()` which constructs file paths. While `model_store.py` has path sanitization (T-306-FIX3), defense-in-depth requires validation at the API layer. Inconsistent with `instrument` validation on line 42.
  - **Remediation:** Add validation: reject `model_type` values not in `_MODEL_TYPES` with 400 error. Add instrument validation to `get_ohlcv`, `get_features`, and `compute_features` for consistency.

##### High (should fix)

- [SR-H1] **src/api/v1/data.py:346-378** `compute_features` fetches entire OHLCV history without LIMIT — source: Red Team (RH-2)
  - **Impact:** With 3 years of 1-minute data (~1.6M rows), this could cause memory exhaustion and server unresponsiveness. No pagination or upper bound.
  - **Remediation:** Add a reasonable row limit (e.g., 50,000 rows) or restrict to a configurable time window. Log a warning if data is truncated.

- [SR-H2] **client/src/lib/api.ts:222-228** Client `ohlcv` function signature broken — source: both (W-9 + RH-3)
  - **Impact:** `interval` and `start` are required server params but optional/missing in client. Any call produces 422. Currently unused but latent bug.
  - **Remediation:** Fix client function to require `interval` and `start` params matching the server contract.

- [SR-H3] **src/app.py:16** FastAPI version hardcoded to `"0.1.0"` — source: both (W-1 + RH-4)
  - **Impact:** OpenAPI schema and Swagger UI report wrong version (actual: 0.4.5).
  - **Remediation:** Read version from `VERSION` file at startup.

- [SR-H4] **src/api/v1/regime.py:92-93,133** Regime endpoint error handling and step size — source: Code Review (W-2, W-3)
  - **Impact:** `compute_vol_30d`/`compute_adx_14` can raise unhandled `ValueError` on bad data, producing 500 errors. Step size comment is misleading (says "20 trading days" but 1h bars means 20 hours).
  - **Remediation:** Wrap regime computation in try/except with `_unknown_regime` fallback. Fix step size to ~720 for monthly recalculation, or correct the comment.

##### Medium (recommend)

- [SR-M1] **client/src/pages/AdminPage.tsx:687** React Fragment missing `key` in `.map()` — source: both (W-6 + RM-1). Replace `<>` with `<React.Fragment key={key}>`.
- [SR-M2] **src/api/schemas.py** Loose typing — `status`, `regime_label`, `confidence_band` use `str` instead of `Literal` — source: Code Review (W-5).
- [SR-M3] **client/index.html** Missing `class="dark"` on `<html>` — shadcn/ui `dark:` variants are dead code — source: Code Review (W-7).
- [SR-M4] **client/src/pages/AdminPage.tsx:476** `Promise.all` in RegimeMonitor — one failure hides both instruments — source: Code Review (W-8).
- [SR-M5] **src/api/v1/uat.py:23** Eager UAT runner import at startup — loads numpy/xgboost/sklearn even when unused — source: Red Team (RM-4).
- [SR-M6] **src/api/v1/uat.py:38** UAT run endpoint lacks concurrency control — source: Red Team (RM-5).
- [SR-M7] **src/api/v1/data.py:39%, regime.py:43%** Low test coverage on API endpoints — source: Code Review (W-4).

##### Low (noted)

- [SR-L1] UAT router unconditionally mounted (N-1), traceback leakage in UAT errors (N-2), hardcoded instruments in health (N-3), kill_switch not displayed (N-4), no 404 route (N-5), silent error swallowing (N-6), production sourcemaps (N-7), brittle test counts (N-8), native select dark mode (N-9).
- [SR-L2] kill_switch_active hardcoded to False (RL-1), N+1 query (RL-2), console.error in ErrorBoundary (RL-3), silent feature table truncation (RL-4), inefficient rolling vol (RL-5), repeated psycopg imports (RL-6).

##### Deferred (tracked separately)

- [SR-D1] **src/regime/detector.py** Regime volatility uses daily annualization factors on hourly data (~4.9x error) — source: Red Team (RH-1). Pre-existing Stage 3 issue. Deferred per user decision — to be addressed when regime detection is used for trading decisions (Stage 5+).

#### Test Gap Summary

- [SR-TG1] **POST /api/v1/features/compute** Zero test coverage — write endpoint modifying DB state — source: Red Team (TG-1)
- [SR-TG2] **GET /api/v1/ohlcv, GET /api/v1/features** No dedicated endpoint tests — source: Red Team (TG-2)
- [SR-TG3] **Admin panel client components** No frontend tests — source: Red Team (TG-3)
- [SR-TG4] **POST /api/v1/uat/run** Undocumented behavior when both `suite` and `test_id` provided — source: Red Team (TG-4)

#### Contradictions Between Reviews

None — reviews are consistent. Both reviews identified the exception message leakage as the most critical finding. The code review classified `model_type` validation as Critical while the red team classified it as Medium; unified as Critical per defense-in-depth principle. The red team identified the unbounded compute query (RH-2) which the code review missed.

#### User Interview Notes

- Reviews are comprehensive — no additional issues beyond what was found.
- RH-1 (regime annualization) is a pre-existing Stage 3 issue and should be deferred, not block Stage 4. Tracked as SR-D1.
- All remaining critical and high findings should be fixed as remediation tasks before the stage gate.
- No manual testing issues found. No timeline concerns.

#### Positive Observations

1. **Clean quality gate:** 429 tests, 91% coverage, zero lint/type errors, client builds with TypeScript strict mode.
2. **Strong security posture:** All SQL queries use parameterized `%s` placeholders. Path traversal protection in model_store. No XSS risks in React (no `dangerouslySetInnerHTML`). No secrets in code.
3. **Well-structured UAT framework:** Frozen dataclasses, clean runner/suite separation, proper error categorization (assertion vs unexpected), 28 behavioral tests covering all Stage 1-3 subsystems.
4. **Good client architecture:** Typed `ApiError`, graceful proxy 502, error boundary with recovery, consistent dark mode with semantic badges.
5. **Spec-aligned delivery:** All 5 implementation tasks match their acceptance criteria. DEC-015 recorded for client technology decision.

#### Remediation Tasks

| ID | Task | Scope | Acceptance | Status |
|---|---|---|---|---|
| T-405-FIX1 | Sanitize API error responses and add input validation | server | All `HTTPException(500)` in `data.py` use generic messages (no `{exc}` interpolation); `models.py` validates `model_type` against `_MODEL_TYPES` with 400 on invalid; `data.py` validates `instrument` on `get_ohlcv`, `get_features`, `compute_features`; `compute_features` has a row limit (≤50,000); `regime.py` wraps computation in try/except with `_unknown_regime` fallback; quality gate passes | TODO |
| T-405-FIX2 | Fix client API contract and app version | fullstack | `api.ts` `ohlcv()` requires `interval` and `start` params matching server; `app.py` reads version from `VERSION` file; `regime.py` step size corrected or comment fixed; React Fragment key added in ModelDashboard; `class="dark"` added to `index.html`; quality gate passes | TODO |

#### Verdict

**NOT READY** — 2 critical findings (exception leakage, unvalidated model_type) and 4 high findings (unbounded compute, broken OHLCV client, version mismatch, regime error handling) require remediation. Two FIX tasks have been drafted to address all critical + high findings plus the most impactful medium items. The codebase is architecturally sound with strong security fundamentals — issues are localized to the API integration layer and are straightforward to fix.

### Fix Verification

- **Date:** 2026-03-05
- **Status:** PASS

#### Verified Fixes

| Fix Task | Original Finding | Status | Notes |
|---|---|---|---|
| T-405-FIX1 | SR-C1 (exception leakage) | PASS | All 4 `HTTPException(500)` in `data.py` (lines 209, 261, 326, 438) now use generic messages. `logger.exception` logs full details server-side. Verified: no `{exc}` interpolation remains in any HTTP error detail. |
| T-405-FIX1 | SR-C2 (model_type validation) | PASS | `models.py:45-49` validates `model_type` against `_MODEL_TYPES` with 400 error. Test `test_models_endpoint_rejects_invalid_model_type` confirms. |
| T-405-FIX1 | SR-C2 (instrument validation) | PASS | `data.py:27-32` adds `_SUPPORTED_INSTRUMENTS` set and `_validate_instrument()` helper. Called at lines 184, 295, 365 for `get_ohlcv`, `get_features`, `compute_features`. Tests confirm 400 on unsupported instruments. |
| T-405-FIX1 | SR-H1 (unbounded compute) | PASS | `data.py:388` adds `LIMIT 50000` to the compute_features OHLCV query. |
| T-405-FIX1 | SR-H4 (regime error handling) | PASS | `regime.py:92-97` wraps `compute_vol_30d`/`compute_adx_14` in `try/except (ValueError, ZeroDivisionError)` returning `_unknown_regime` fallback. Test `test_regime_computation_error_returns_unknown` confirms. |
| T-405-FIX2 | SR-H2 (broken OHLCV client) | PASS | `api.ts:222-231` now requires `interval: string` and `start: string` as mandatory params in `ohlcv()` signature. `params` object is non-optional. |
| T-405-FIX2 | SR-H3 (version mismatch) | PASS | `app.py:13-14` reads `VERSION` file dynamically. `app.py:18` uses `_app_version`. Tests `test_app_version_matches_version_file` and `test_openapi_version_matches` confirm version matches `VERSION` file. |
| T-405-FIX2 | SR-H4 (regime step comment) | PASS | `regime.py:137` comment corrected from "20 trading days" to "~20 bars for rolling window sampling". |
| T-405-FIX2 | SR-M1 (Fragment key) | PASS | `AdminPage.tsx:1` imports `Fragment`; line 687 uses `<Fragment key={key}>` instead of bare `<>`. |
| T-405-FIX2 | SR-M3 (dark class) | PASS | `index.html:2` has `<html lang="en" class="dark">`. |

#### Quality Gate
- lint: PASS
- types: PASS
- tests: PASS — 441 passed (12 new), 93% coverage

#### New Issues Found
None — fixes are clean. No regressions detected. All 429 previously passing tests still pass. 12 new tests added covering validation and error handling paths.

#### Verdict
**PASS**

All 10 findings across both FIX tasks are resolved. Error messages are sanitized, input validation is consistent across all API endpoints, client contract matches server, app version is dynamic, and regime computation has proper error handling. The stage can proceed to gate approval.
