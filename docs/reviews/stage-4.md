# Stage 4: UAT & Admin UI

## Code Review

- **Date:** 2026-03-05
- **Scope:** Full Stage 4 — T-401 through T-405 (React foundation, UAT API, UAT Runner UI, admin panels, UAT.md refresh)

### Findings

#### Critical

- [C-1] **src/api/v1/models.py:46** Path traversal risk — `model_type` query parameter is not validated against `_MODEL_TYPES` before being passed to `list_versions()`, which constructs file paths. A malicious `model_type=../../etc` could probe the filesystem. The `model_store.py` has path sanitization (T-306-FIX3) but defense-in-depth requires validation at the API boundary too.

- [C-2] **src/api/v1/data.py:200,251,314,424** Information leakage — database exception messages are interpolated directly into HTTP 500 response details (`f"Failed to query OHLCV: {exc}"`). Database exceptions can contain connection strings, SQL fragments, or internal state. Should use generic error messages and log details server-side only.

#### Warning

- [W-1] **src/app.py:15** Version mismatch — FastAPI app declares `version="0.1.0"` while `VERSION` file is `0.4.5`. Should read from VERSION file dynamically.

- [W-2] **src/api/v1/regime.py:133** Incorrect step size comment — `step = 20` comment says "20 trading days" but for 1h bars this is 20 hours. The computation still produces a reasonable vol_median (sparse sampling of the available data), but the comment is misleading and the step should be ~720 (30 days × 24h) to match the "monthly recalculation" spec requirement (SPEC §5.8.2).

- [W-3] **src/api/v1/regime.py:92-93** Unhandled ValueError — `compute_vol_30d`/`compute_adx_14` can raise `ValueError` on non-positive prices in database data, producing unhandled 500 errors. Should be wrapped in try/except with fallback to `_unknown_regime`.

- [W-4] **src/api/v1/data.py:39%** Low test coverage — four complete API endpoints (`/ohlcv`, `/features/metadata`, `/features/{instrument}`, `/features/compute`) have zero test coverage. The `regime.py` endpoint (43%) only tests the "no database" fallback, not the core computation path.

- [W-5] **src/api/schemas.py** Loose typing — `UATTestResult.status`, `RegimeResponse.regime_label`, `RegimeResponse.confidence_band` use `str` instead of `Literal` types, weakening type safety and OpenAPI schema precision.

- [W-6] **client/src/pages/AdminPage.tsx:687** React Fragment key warning — `<>` used inside `.map()` without a key. Should use `<React.Fragment key={key}>` to avoid React console warning.

- [W-7] **client/index.html** Missing `class="dark"` on `<html>` element — shadcn/ui components include `dark:` variant styles (e.g., `dark:bg-input/30`, `dark:border-input`) that never activate because no `.dark` class exists in the DOM. The base theme is dark via CSS variables, but `dark:` refinements are dead code.

- [W-8] **client/src/pages/AdminPage.tsx:476** RegimeMonitor uses `Promise.all` — if either instrument's regime endpoint fails, both instruments show nothing. Should use `Promise.allSettled` for partial results.

- [W-9] **client/src/lib/api.ts:222** OHLCV client method broken — `interval` and `start` are required backend params but optional/missing in the client method. Any call would receive 422. Currently unused but latent bug.

#### Note

- [N-1] **src/app.py:25** UAT router is mounted unconditionally — in production, UAT test execution should be gated by environment or auth to prevent CPU exhaustion via repeated test runs.

- [N-2] **src/uat/runner.py:122** Full Python tracebacks returned in UAT `error` field — exposes file paths and internal code structure. Acceptable for dev, should be sanitized for production.

- [N-3] **src/api/v1/data.py:111,132** Hardcoded instrument list `["EUR_USD", "BTC_USD"]` and `kill_switch_active=False` in health check — should derive from config and actual system state respectively.

- [N-4] **client/src/pages/HealthPage.tsx** `kill_switch_active` field is fetched but never displayed — critical operational data for a trading system that should be prominent.

- [N-5] **client/src/App.tsx** No 404 catch-all route — navigating to `/foo` renders empty content area with sidebar. Should show a 404 component.

- [N-6] **client/src/pages/AdminPage.tsx:117,303** Silent error swallowing — metadata and generators load failures are caught and silently set to empty/null with no user feedback.

- [N-7] **client/vite.config.ts:32** Production sourcemaps enabled (`sourcemap: true`) — exposes TypeScript source. Acceptable for internal tool but should be disabled if ever externally accessible.

- [N-8] **tests/unit/test_uat_api.py:156,179,209** Hardcoded magic numbers (7 suites, 28 tests) — tests are brittle and will break if suites are added/removed. Test the framework logic, not the current count.

- [N-9] **client/src/pages/AdminPage.tsx:49,187,355,652** Native `<select>` dropdown `<option>` elements lack explicit dark mode styling — may render with browser default light theme on some platforms (Windows Chrome).

### Quality Gate
- lint: PASS
- types: PASS
- tests: PASS — 429 passed, 91% coverage

### Verdict
Ready for merge with conditions — 2 critical findings (path traversal, info leakage) should be addressed via fix tasks. The warnings are real but non-blocking for a localhost-only admin tool at this stage. Client code is clean with no XSS risks.

## Red Team Review

- **Date:** 2026-03-05
- **Reviewer:** Adversarial Subagent (fresh context)
- **Scope:** Full Stage 4 — UAT & Admin UI (T-401 through T-405), server + client + tests

### Quality Gate
- lint: PASS
- types: PASS
- tests: PASS — 429 passed, 91% coverage
- client build: PASS

### Critical

- [RC-1] **src/api/v1/data.py:200,251,314,424** Raw exception messages leaked to API clients — database connection failures could reveal full `DATABASE_URL` including credentials in HTTP 500 response bodies. Four endpoints affected. Violates SPEC 7.3 (secrets from env only) and 10.1 (no secrets in output).

### High

- [RH-1] **src/api/v1/regime.py:72 + src/regime/detector.py** Regime volatility computed from hourly data with daily annualization factors — `sqrt(252)` and `sqrt(365)` are calibrated for daily returns, not hourly. Hourly returns produce volatility estimates ~4.9x too low, biasing regime classification toward `LOW_VOL_*` states. Pre-existing Stage 3 issue surfaced by Stage 4 admin UI.

- [RH-2] **src/api/v1/data.py:346-378** `compute_features` endpoint fetches entire OHLCV history without LIMIT — with 3 years of 1-minute data (~1.6M rows), this could cause memory exhaustion and server unresponsiveness.

- [RH-3] **client/src/lib/api.ts:222-228** Client `ohlcv` function signature mismatches server — `interval` and `start` are required on the server but optional/missing on the client. Any call produces 422. Broken API contract.

- [RH-4] **src/app.py:16** FastAPI version hardcoded to `"0.1.0"` while VERSION file is `0.4.5` — OpenAPI schema and Swagger UI report wrong version.

### Medium

- [RM-1] **client/src/pages/AdminPage.tsx:687** React Fragment missing `key` prop in list rendering — can cause incorrect DOM reconciliation in ModelDashboard.

- [RM-2] **src/api/v1/models.py:46** `model_type` query parameter not validated against allowed list — inconsistent with `instrument` validation on line 42.

- [RM-3] **src/api/v1/data.py:169,273,346** Inconsistent instrument validation — `get_ohlcv`, `get_features`, `compute_features` accept any string without validation, unlike regime and models endpoints.

- [RM-4] **src/api/v1/uat.py:23** Module-level UAT runner instantiation eagerly imports all suite dependencies (numpy, xgboost, sklearn) at server startup — adds startup time/memory even if UAT is never used.

- [RM-5] **src/api/v1/uat.py:38** UAT run endpoint lacks rate limiting or concurrency control — multiple concurrent requests could overload server with CPU-intensive ML tests.

### Low

- [RL-1] **src/api/v1/data.py:132** `kill_switch_active` hardcoded to `False` — acceptable for Stage 4 but must be wired to actual state in Stage 5+.

- [RL-2] **src/api/v1/data.py:71** N+1 query pattern in `_query_last_candle_ages` — separate query per instrument, could be a single grouped query.

- [RL-3] **client/src/components/ErrorBoundary.tsx:23** `console.error` in production — appropriate for error boundaries but consider structured reporting.

- [RL-4] **client/src/pages/AdminPage.tsx:287** Feature table silently truncates to last 50 timestamps — no user-visible indicator of truncation.

- [RL-5] **src/api/v1/regime.py:129-142** Inefficient rolling vol computation — creates progressively larger array copies at each step. Could pass only the necessary window.

- [RL-6] **src/api/v1/data.py:43,63,180,237,289,357** psycopg imported inside function bodies — adds import overhead on every request. Consider module-level import with try/except guard.

### Test Gaps

- [TG-1] **POST /api/v1/features/compute** No tests at all — a write endpoint that modifies DB state has zero coverage.

- [TG-2] **GET /api/v1/ohlcv, GET /api/v1/features** No dedicated tests — missing validation error (422), missing DATABASE_URL, response shape tests.

- [TG-3] **Admin panel client components** No frontend tests for FeatureExplorer, SignalInspector, RegimeMonitor, ModelDashboard.

- [TG-4] **POST /api/v1/uat/run** No test for `test_id` and `suite` both provided simultaneously — current behavior (prioritize `test_id`) is undocumented and untested.

- [TG-5] **client/src/lib/api.ts** No tests for API timeout or malformed JSON responses.

### Positive Observations

1. Clean quality gate: 429 tests, 91% coverage, zero lint/type errors, client builds cleanly with TypeScript strict mode.
2. Well-structured UAT framework: frozen dataclasses, clean separation of runner and suites, proper error handling distinguishing assertion failures from unexpected errors.
3. Good client error handling: typed `ApiError`, network failure catches, graceful 502 proxy response.
4. Consistent dark mode: all components use Tailwind dark mode classes with semantic color badges.
5. SQL injection prevention: all queries use parameterized `%s` placeholders throughout.
6. Path traversal protection: `model_store.py` validates with `^[A-Za-z0-9_-]+$` regex.
7. Good error boundary: React `ErrorBoundary` with recovery mechanism.

### Verdict
**CONDITIONAL PASS** — RC-1 (exception leakage) must be fixed. RH-1 (regime vol computation) is pre-existing Stage 3 and should be tracked separately. RH-3 (broken OHLCV client) and RH-4 (version mismatch) are straightforward Stage 4 fixes. The codebase demonstrates solid engineering: parameterized SQL, frozen dataclasses, typed APIs, comprehensive UAT coverage. Issues are primarily in the integration layer (API validation consistency, error message handling) rather than core logic.

## Stage Report

- **Date:** 2026-03-05
- **Status:** APPROVED
- **Sign-off:** 2026-03-05

### Quality Gate Summary
- lint: PASS
- types: PASS
- tests: PASS — 429 passed, 91% coverage
- client build: PASS

### Unified Findings

#### Critical (must fix)

- [SR-C1] **src/api/v1/data.py:200,251,314,424** Exception message leakage in HTTP 500 responses — source: both (C-2 + RC-1)
  - **Impact:** Database exceptions can expose `DATABASE_URL` credentials, SQL fragments, and internal state in API response bodies. Violates SPEC 7.3 and 10.1.
  - **Remediation:** Replace `{exc}` interpolation with generic error messages. Log full exception server-side only (already done via `logger.exception` in some handlers). Apply to all 4 affected endpoints.

- [SR-C2] **src/api/v1/models.py:46** `model_type` query parameter not validated at API boundary — source: both (C-1 + RM-2)
  - **Impact:** Unvalidated user input passed to `list_versions()` which constructs file paths. While `model_store.py` has path sanitization (T-306-FIX3), defense-in-depth requires validation at the API layer. Inconsistent with `instrument` validation on line 42.
  - **Remediation:** Add validation: reject `model_type` values not in `_MODEL_TYPES` with 400 error. Add instrument validation to `get_ohlcv`, `get_features`, and `compute_features` for consistency.

#### High (should fix)

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

#### Medium (recommend)

- [SR-M1] **client/src/pages/AdminPage.tsx:687** React Fragment missing `key` in `.map()` — source: both (W-6 + RM-1). Replace `<>` with `<React.Fragment key={key}>`.
- [SR-M2] **src/api/schemas.py** Loose typing — `status`, `regime_label`, `confidence_band` use `str` instead of `Literal` — source: Code Review (W-5).
- [SR-M3] **client/index.html** Missing `class="dark"` on `<html>` — shadcn/ui `dark:` variants are dead code — source: Code Review (W-7).
- [SR-M4] **client/src/pages/AdminPage.tsx:476** `Promise.all` in RegimeMonitor — one failure hides both instruments — source: Code Review (W-8).
- [SR-M5] **src/api/v1/uat.py:23** Eager UAT runner import at startup — loads numpy/xgboost/sklearn even when unused — source: Red Team (RM-4).
- [SR-M6] **src/api/v1/uat.py:38** UAT run endpoint lacks concurrency control — source: Red Team (RM-5).
- [SR-M7] **src/api/v1/data.py:39%, regime.py:43%** Low test coverage on API endpoints — source: Code Review (W-4).

#### Low (noted)

- [SR-L1] UAT router unconditionally mounted (N-1), traceback leakage in UAT errors (N-2), hardcoded instruments in health (N-3), kill_switch not displayed (N-4), no 404 route (N-5), silent error swallowing (N-6), production sourcemaps (N-7), brittle test counts (N-8), native select dark mode (N-9).
- [SR-L2] kill_switch_active hardcoded to False (RL-1), N+1 query (RL-2), console.error in ErrorBoundary (RL-3), silent feature table truncation (RL-4), inefficient rolling vol (RL-5), repeated psycopg imports (RL-6).

#### Deferred (tracked separately)

- [SR-D1] **src/regime/detector.py** Regime volatility uses daily annualization factors on hourly data (~4.9x error) — source: Red Team (RH-1). Pre-existing Stage 3 issue. Deferred per user decision — to be addressed when regime detection is used for trading decisions (Stage 5+).

### Test Gap Summary

- [SR-TG1] **POST /api/v1/features/compute** Zero test coverage — write endpoint modifying DB state — source: Red Team (TG-1)
- [SR-TG2] **GET /api/v1/ohlcv, GET /api/v1/features** No dedicated endpoint tests — source: Red Team (TG-2)
- [SR-TG3] **Admin panel client components** No frontend tests — source: Red Team (TG-3)
- [SR-TG4] **POST /api/v1/uat/run** Undocumented behavior when both `suite` and `test_id` provided — source: Red Team (TG-4)

### Contradictions Between Reviews

None — reviews are consistent. Both reviews identified the exception message leakage as the most critical finding. The code review classified `model_type` validation as Critical while the red team classified it as Medium; unified as Critical per defense-in-depth principle. The red team identified the unbounded compute query (RH-2) which the code review missed.

### User Interview Notes

- Reviews are comprehensive — no additional issues beyond what was found.
- RH-1 (regime annualization) is a pre-existing Stage 3 issue and should be deferred, not block Stage 4. Tracked as SR-D1.
- All remaining critical and high findings should be fixed as remediation tasks before the stage gate.
- No manual testing issues found. No timeline concerns.

### Positive Observations

1. **Clean quality gate:** 429 tests, 91% coverage, zero lint/type errors, client builds with TypeScript strict mode.
2. **Strong security posture:** All SQL queries use parameterized `%s` placeholders. Path traversal protection in model_store. No XSS risks in React (no `dangerouslySetInnerHTML`). No secrets in code.
3. **Well-structured UAT framework:** Frozen dataclasses, clean runner/suite separation, proper error categorization (assertion vs unexpected), 28 behavioral tests covering all Stage 1-3 subsystems.
4. **Good client architecture:** Typed `ApiError`, graceful proxy 502, error boundary with recovery, consistent dark mode with semantic badges.
5. **Spec-aligned delivery:** All 5 implementation tasks match their acceptance criteria. DEC-015 recorded for client technology decision.

### Remediation Tasks

| ID | Task | Scope | Acceptance | Status |
|---|---|---|---|---|
| T-405-FIX1 | Sanitize API error responses and add input validation | server | All `HTTPException(500)` in `data.py` use generic messages (no `{exc}` interpolation); `models.py` validates `model_type` against `_MODEL_TYPES` with 400 on invalid; `data.py` validates `instrument` on `get_ohlcv`, `get_features`, `compute_features`; `compute_features` has a row limit (≤50,000); `regime.py` wraps computation in try/except with `_unknown_regime` fallback; quality gate passes | TODO |
| T-405-FIX2 | Fix client API contract and app version | fullstack | `api.ts` `ohlcv()` requires `interval` and `start` params matching server; `app.py` reads version from `VERSION` file; `regime.py` step size corrected or comment fixed; React Fragment key added in ModelDashboard; `class="dark"` added to `index.html`; quality gate passes | TODO |

### Verdict

**NOT READY** — 2 critical findings (exception leakage, unvalidated model_type) and 4 high findings (unbounded compute, broken OHLCV client, version mismatch, regime error handling) require remediation. Two FIX tasks have been drafted to address all critical + high findings plus the most impactful medium items. The codebase is architecturally sound with strong security fundamentals — issues are localized to the API integration layer and are straightforward to fix.

## Fix Verification

- **Date:** 2026-03-05
- **Status:** PASS

### Verified Fixes

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

### Quality Gate
- lint: PASS
- types: PASS
- tests: PASS — 441 passed (12 new), 93% coverage

### New Issues Found
None — fixes are clean. No regressions detected. All 429 previously passing tests still pass. 12 new tests added covering validation and error handling paths.

### Verdict
**PASS**

All 10 findings across both FIX tasks are resolved. Error messages are sanitized, input validation is consistent across all API endpoints, client contract matches server, app version is dynamic, and regime computation has proper error handling. The stage can proceed to gate approval.
