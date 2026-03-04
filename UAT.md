# Newton User Acceptance Tests

A practical test plan for human verification. Each item is something you can see, click, or run — not a unit-test assertion. All granular logic tests are covered by `pytest` (429+ tests) and the automated UAT suite (28 behavioral tests).

**Prerequisites:**
1. Start TimescaleDB: `docker compose up -d`
2. Apply migrations: `python scripts/db_bootstrap.py`
3. Start API server: `./scripts/run_api.sh` (runs on port 8000)
4. Start client dev server: `cd client && npm run dev` (runs on port 4173)
5. Ensure OHLCV data is loaded for EUR_USD and BTC_USD (1h interval)

**How to use this file:**
- Work through each section in order
- Check the box when the test passes
- Add notes for issues, unexpected behavior, or observations
- If a test fails, describe the actual behavior in the Notes column

---

## A. Quality Gate

These verify the development toolchain is healthy. Run from the project root.

| Pass | Test | How to verify | Notes |
|------|------|---------------|-------|
| [ ] | Linting passes | Run `ruff check .` — output: "All checks passed!" | |
| [ ] | Type checking passes | Run `mypy src` — output: "Success: no issues found in NN source files" | |
| [ ] | All tests pass with coverage | Run `pytest -q` — all tests pass, coverage >= 80% global | |
| [ ] | Client builds cleanly | Run `cd client && npm run build` — no TypeScript or build errors | |

---

## B. Automated UAT Suite

The UAT suite contains 28 behavioral tests across 7 suites that exercise the full backend pipeline with synthetic data (no DB required). You can run them two ways:

**Option 1 — Via the UAT Runner UI (recommended):**
Navigate to `http://localhost:4173/uat`, click "Run All", and verify 28/28 pass.

**Option 2 — Via API:**
`POST http://localhost:8000/api/v1/uat/run` with `{}` body.

| Pass | Suite | Tests | What it covers | Notes |
|------|-------|-------|----------------|-------|
| [ ] | Data Pipeline | DP-01 to DP-04 | Candle normalization, OHLC integrity detection, deduplication, indicator computation | |
| [ ] | Event Detection | ED-01 to ED-04 | Binary event labeling, flat-price handling, tokenizer mapping, MI-based token selection | |
| [ ] | Bayesian | BA-01 to BA-04 | Model training with Laplace smoothing, posterior clamping, isotonic calibration, phi correlation | |
| [ ] | ML Training | ML-01 to ML-04 | Feature matrix construction, walk-forward folds with embargo, model artifact save/load, XGBoost prediction | |
| [ ] | Regime | RG-01 to RG-04 | Regime classification (4 labels), confidence bands, non-positive price guard, ADX range | |
| [ ] | Ensemble | EN-01 to EN-04 | Meta-learner training, prediction validity, calibration error check, ensemble signal generation | |
| [ ] | End-to-End | E2E-01 to E2E-04 | Neutral fail-safe, fallback chain activation, multi-instrument independence, generator registry | |
| [ ] | **All 28 pass** | — | Summary bar shows 28/28 passed, 0 failed | |

---

## C. Health Dashboard

**Page:** `http://localhost:4173/` (Health)

| Pass | Test | What to look for | Notes |
|------|------|------------------|-------|
| [ ] | Page loads with sidebar | Sidebar shows Newton branding and three nav links: Health, UAT Runner, Admin. Active link is highlighted. | |
| [ ] | Status cards display | Four cards visible: API Status, Database, Uptime, Generated At | |
| [ ] | Broker connectivity | Brokers table shows Oanda and Binance rows with connected/disconnected status | |
| [ ] | Instrument freshness | Instruments table shows EUR_USD and BTC_USD with last candle age in seconds | |
| [ ] | Auto-refresh works | Watch the "Last updated" timestamp — it refreshes every ~10 seconds | |
| [ ] | Error state | Stop the API server, reload the page — error message appears (e.g., "API server unreachable"). Restart the server and verify recovery. | |

---

## D. UAT Runner UI

**Page:** `http://localhost:4173/uat`

| Pass | Test | What to look for | Notes |
|------|------|------------------|-------|
| [ ] | Suite cards render | 7 suite cards visible, each showing suite name and test count badge | |
| [ ] | Run All | Click "Run All" — all 28 tests execute, summary bar shows "28/28 passed" with total duration | |
| [ ] | Run single suite | Click "Run Suite" on any suite card — only that suite's tests run and results appear | |
| [ ] | Results table | Each test row shows ID, name, pass/fail badge, and duration in milliseconds | |
| [ ] | Expandable details | Click any test row — accordion expands showing suite, status, duration, and detail text. Click again to collapse. | |
| [ ] | Re-run individual test | Click "Re-run" on a single test — only that test re-executes and its result updates | |
| [ ] | Loading states | During execution, buttons show spinners and are disabled (no concurrent runs) | |
| [ ] | Error state | Stop API server, try "Run All" — error banner appears with message | |

---

## E. Admin Panels

**Page:** `http://localhost:4173/admin`

### E1. Feature Explorer

| Pass | Test | What to look for | Notes |
|------|------|------------------|-------|
| [ ] | Tab loads | Click "Feature Explorer" tab — instrument and interval dropdowns visible, overview explanation text describes RSI, MACD, Bollinger Bands, OBV, ATR | |
| [ ] | Compute features | Select EUR_USD + 1h, click "Compute Features" — success summary appears showing candles read, features computed, metadata stored. Repeat for BTC_USD. | |
| [ ] | Load features | Click "Load Features" — pivoted table appears with timestamps as rows and indicator names as columns. Values should be numeric (not empty). | |
| [ ] | Switch instrument | Change dropdown to BTC_USD and reload — different feature values appear | |

### E2. Signal Inspector

| Pass | Test | What to look for | Notes |
|------|------|------------------|-------|
| [ ] | Tab loads | Click "Signal Inspector" tab — instrument and generator dropdowns visible, overview text explains signal actions (STRONG_BUY, BUY, SELL, NEUTRAL) and three engine types | |
| [ ] | Generate signal | Select instrument and a generator (e.g., bayesian_v1), click "Generate Signal" — signal card appears with action badge (colored), probability value, confidence value, generator ID | |
| [ ] | Component scores | Below the signal card, a component scores table shows named scores with numeric values | |
| [ ] | Metadata | Metadata section displays the full JSON metadata from the signal response | |

### E3. Regime Monitor

| Pass | Test | What to look for | Notes |
|------|------|------------------|-------|
| [ ] | Auto-loads on tab click | Click "Regime Monitor" tab — regime data loads automatically for both EUR_USD and BTC_USD (no button click needed) | |
| [ ] | Instrument cards | Each instrument shows: regime label badge (e.g., "LOW_VOL_TRENDING"), confidence value with band label (HIGH/MEDIUM/LOW), vol_30d, ADX_14, vol_median | |
| [ ] | Overview text | Explanation describes the 4 regime types, what vol_30d and ADX measure, and confidence band thresholds | |

### E4. Model Dashboard

| Pass | Test | What to look for | Notes |
|------|------|------------------|-------|
| [ ] | Tab loads | Click "Model Dashboard" tab — instrument and model type dropdowns visible, overview text describes Bayesian, XGBoost, and Meta-Learner model types | |
| [ ] | Load models | Select instrument, click "Load Models" — if models have been trained, version history table appears. If none trained, "No model artifacts found" message displays. | |
| [ ] | Model details | If models exist: each row shows model type, version, training date, AUC-ROC metric. Expandable rows show hyperparameters and artifact hash. | |

---

## F. API Endpoints

Verify key endpoints return valid responses. Use browser, curl, or any HTTP client against `http://localhost:8000`.

| Pass | Test | How to verify | Notes |
|------|------|---------------|-------|
| [ ] | Health | `GET /api/v1/health` — returns JSON with `status`, `db`, `brokers`, `instruments`, `checksum` fields | |
| [ ] | OHLCV data | `GET /api/v1/ohlcv/EUR_USD?interval=1h&start=2020-01-01T00:00:00Z` — returns `data` array with candle objects (time, open, high, low, close, volume) | |
| [ ] | Feature metadata | `GET /api/v1/features/metadata` — returns `registry` array listing indicator definitions (RSI_14, MACD_*, BB_*, OBV, ATR_14) | |
| [ ] | Features query | `GET /api/v1/features/EUR_USD?interval=1h&start=2020-01-01T00:00:00Z` — returns `data` array with feature rows (time, namespace, feature_key, value) | |
| [ ] | Signal generation | `GET /api/v1/signals/EUR_USD` — returns signal with `action`, `probability`, `confidence`, `scaffold: true` | |
| [ ] | Regime detection | `GET /api/v1/regime/EUR_USD` — returns `regime_label`, `confidence`, `confidence_band`, `vol_30d`, `adx_14`, `vol_median` | |
| [ ] | Model listing | `GET /api/v1/models/EUR_USD` — returns `artifacts` array (may be empty if no models trained) | |
| [ ] | Feature compute | `POST /api/v1/features/compute` with body `{"instrument": "EUR_USD", "interval": "1h"}` — returns `candles_read`, `features_computed`, `metadata_stored` counts | |

---

## G. Cross-Cutting Checks

| Pass | Test | What to look for | Notes |
|------|------|------------------|-------|
| [ ] | Dark mode | All pages render with dark background, light text, proper contrast. No white-on-white or invisible elements. | |
| [ ] | Dropdown readability | All `<select>` dropdowns across every page show readable text in both collapsed and expanded states | |
| [ ] | Vite proxy | Client dev server at :4173 successfully proxies `/api` requests to :8000 — no CORS errors in browser console | |
| [ ] | Swagger docs | Navigate to `http://localhost:8000/api/docs` — Swagger UI loads with all endpoints listed | |
| [ ] | Error resilience | Stop API server while client is open — pages show error states. Restart server — pages recover on next refresh/action. | |
