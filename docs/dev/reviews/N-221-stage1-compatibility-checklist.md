# N-221 — Stage 1 Compatibility Refactor Checklist

Purpose: Ensure Stage 1 surfaces remain stable while introducing SPEC.v4 SignalGenerator abstraction.

## A) Contract & Type Alignment

- [x] Introduce `Signal` contract in a dedicated shared module (e.g., `src/analysis/signal_contract.py`)
- [x] Ensure signal action vocabulary is FINAL_SPEC-compatible:
  - [x] `STRONG_BUY`
  - [x] `BUY`
  - [x] `SELL`
  - [x] `NEUTRAL`
- [x] Include required signal fields:
  - [x] `probability: float`
  - [x] `confidence: float`
  - [x] `component_scores: dict[str, float]`
  - [x] `metadata: dict[str, Any]`

## B) Skeleton/Placeholder Cleanup

- [x] Audit Stage 1/2 skeleton files for naming drift (`event_detector`, `tokenizer`, `bayesian`, `ml_model`, etc.)
- [x] Remove/rename placeholders that conflict with SPEC.v4 interfaces
- [x] Keep file structure stable where possible (minimize churn)
- [x] Add TODO headers to remaining stubs with task IDs (N-201+)

## C) API Compatibility

- [x] Verify existing Stage 1 endpoints remain unchanged:
  - [x] `/api/v1/health`
  - [x] `/api/v1/ohlcv/{instrument}`
  - [x] `/api/v1/features/{instrument}`
  - [x] `/api/v1/features/metadata`
- [x] Add no breaking changes to current response schemas
- [x] Ensure new signal endpoints are additive (not replacing Stage 1 endpoints)

## D) Data/DB Compatibility

- [x] Confirm no Stage 1 schema regressions in migrations
- [x] Keep `ohlcv`, `features`, `feature_metadata` read/write paths intact
- [x] Ensure any Stage 2 schema additions are additive migrations only

## E) Backtest Boundary Enforcement

- [x] Confirm generator interface uses `generate_batch()` (not `backtest()`)
- [x] Keep simulation logic in existing backtest module (FINAL_SPEC §8 boundary)
- [x] Add code comment/docs note clarifying ownership boundary

## F) Routing & Fallback Semantics

- [x] Define deterministic routing behavior (primary → fallback → neutral fail-safe)
- [x] Emit structured log on fallback event
- [x] Ensure fallback does not trigger hidden behavior changes in trading module

## G) Quality Gates (must pass)

- [x] `pytest`
- [x] `ruff check`
- [x] `mypy src`
- [x] `bandit -r src/`
- [x] Smoke test API boot (`scripts/run_api.sh`)
- [x] Manual UI smoke test for Stage 1 health/data screens

## H) Documentation Updates

- [x] Update `TASKS.md` statuses/notes for N-221
- [x] Update `SPEC.v4.md` if implementation constraints discovered
- [x] Record any spec deviations in `spec/deviations/DEV-*.md` if needed

## Execution Split (recommended)

### N-221A — Code surfaces
- [x] Complete sections A–F of this checklist

### N-221B — Tests & quality gates
- [x] Complete section G of this checklist

### N-221C — Docs & governance
- [x] Complete section H of this checklist

## Exit Criteria for N-221 (umbrella)

- [x] Stage 1 behavior unchanged and verified
- [x] SPEC.v4 contract scaffolding established
- [x] No regressions in tests/lint/type/security
- [x] Ready to start N-201 implementation
