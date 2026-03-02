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
