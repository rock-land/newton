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
- **Status:** PENDING
- **Sign-off:** —

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
