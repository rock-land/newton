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
