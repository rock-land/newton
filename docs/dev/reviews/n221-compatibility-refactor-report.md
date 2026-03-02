# N-221 Compatibility Refactor Report

Date: 2026-02-18  
Branch: `stage/2-event-detection`

## Scope completed

This report covers N-221A/B/C for Stage-1 compatibility while introducing SPEC.v4 signal scaffolding.

## N-221A — Code surfaces (DONE)

### Implemented
- Added shared Signal contract module:
  - `src/analysis/signal_contract.py`
  - Includes `Signal`, `GeneratorConfig`, `FeatureSnapshot`, `SignalGenerator` protocol, and action vocabulary validation.
- Added signal registry + routing scaffolding:
  - `src/trading/signal.py`
  - Boot-time mutable/runtime read-only registry (`freeze()` semantics)
  - Deterministic routing (primary → fallback → NEUTRAL fail-safe)
  - Structured fallback log hook (`signal_generator_fallback` warning event)
  - Explicit ownership boundary note: `generate_batch()` produces signals only; backtest simulation remains in backtest module.
- Added additive signal endpoints:
  - `src/api/v1/signals.py`
  - `GET /api/v1/signals/generators`
  - `GET /api/v1/signals/{instrument}`
- Wired signal router into app without modifying Stage-1 endpoint paths:
  - `src/app.py`
- Updated placeholder scaffolds to explicit TODO headers for N-201+ alignment and to reduce naming drift.

### Compatibility notes
- Stage-1 API paths remain available and unchanged:
  - `/api/v1/health`
  - `/api/v1/ohlcv/{instrument}`
  - `/api/v1/features/{instrument}`
  - `/api/v1/features/metadata`
- New signal endpoints are additive only.

## N-221B — Tests & quality gates (DONE)

### Test updates
- Added unit tests:
  - `tests/unit/test_signal_contract_and_routing.py`
  - `tests/unit/test_signals_api.py`
- Coverage includes:
  - action vocabulary + required Signal fields
  - deterministic `generate_batch()` behavior
  - fallback semantics and structured fallback logging hook
  - additive signal API surfaces
  - OpenAPI path presence for Stage-1 endpoints

### Required gates
- `pytest -q` ✅ (42 passed)
- `ruff check .` ✅
- `mypy src` ✅
- `bandit -r src/` ✅

### Smoke checks
- API boot smoke via `scripts/run_api.sh` ✅
- Endpoint smoke:
  - `GET /api/v1/health` ✅
  - `GET /api/v1/signals/generators` ✅
  - `GET /api/v1/signals/EUR_USD` ✅
- Basic Stage-1 UI smoke assumption:
  - `client/public/index.html` present and app mount remains in `src/app.py` ✅

## N-221C — Docs & governance (DONE)

- Closed checklist items in:
  - `docs/dev/reviews/N-221-stage1-compatibility-checklist.md`
- Updated task statuses in:
  - `TASKS.md` (`N-221`, `N-221A`, `N-221B`, `N-221C` → `DONE`)
- Spec deviations:
  - None required for this pass (`spec/deviations/` update not needed)

## Final status

- N-221A: DONE
- N-221B: DONE
- N-221C: DONE
- N-221 umbrella: DONE

No blockers encountered.
