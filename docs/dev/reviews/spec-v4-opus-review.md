# SPEC.v4 Opus Review — Modular Signal Architecture

**Reviewer:** Opus (independent spec review)  
**Date:** 2026-02-18  
**Documents Reviewed:**  
- `FINAL_SPEC.md` (baseline, dated 2026-02-17)  
- `spec/SPEC.v4.md` (draft, dated 2026-02-18)  
- `TASKS.md` (current task tracking)

---

## Executive Verdict: CONDITIONAL PASS

SPEC.v4 introduces a sound architectural idea — a pluggable `SignalGenerator` interface with a registry and per-instrument routing — that aligns well with Newton's extensibility principles. However, the draft has **integration gaps**, **interface conflicts**, and **ambiguities** that must be resolved before implementation begins. The issues are fixable without rethinking the design.

**Recommendation:** Resolve the critical and major issues below, then proceed with Stage 2 implementation using the corrected SPEC.v4 as an addendum to FINAL_SPEC.md (not a merge — see Governance section).

---

## Critical Issues

### C-1: Signal dataclass conflicts with FINAL_SPEC signal model

**SPEC.v4 §1.2** defines:
```python
action: Literal["long", "short", "close", "hold"]
```

**FINAL_SPEC §5.6** defines signal actions as:
```
STRONG_BUY | BUY | SELL | NEUTRAL
```

And FINAL_SPEC §2.2 explicitly states: *"v1 is long-only; SELL signal closes existing longs"* — there is no `short` action in v1.

**Risks:**
- v4's `"short"` action contradicts the v1 scope (no short selling).
- v4's `"long"/"close"/"hold"` vocabulary doesn't map to FINAL_SPEC's `STRONG_BUY/BUY/SELL/NEUTRAL` without a translation layer.
- Downstream consumers (risk engine, executor, trading module) are specified against the FINAL_SPEC vocabulary.

**Fix:** The `Signal` dataclass must use the FINAL_SPEC action vocabulary (`STRONG_BUY`, `BUY`, `SELL`, `NEUTRAL`) or explicitly define the mapping. Remove `"short"` from v1 scope. If v4 wants to future-proof for short selling, make the action type extensible but document `"short"` as reserved/unused in v1.

**Suggested edit (SPEC.v4 §1.2):**
```python
action: Literal["STRONG_BUY", "BUY", "SELL", "NEUTRAL"]  # v1 vocabulary per FINAL_SPEC §5.6
```
Add a note: *"Future versions may add `SHORT` and `COVER` actions. v1 generators MUST NOT emit `SHORT`."*

### C-2: `generate()` return type loses threshold/score information

**SPEC.v4 §1.2** has `generate()` returning a single `Signal` with `confidence: float`.

**FINAL_SPEC §5.4-5.6** specifies a multi-stage pipeline:
1. Bayesian engine → calibrated posterior probability
2. ML model → probability score  
3. Meta-learner → combined probability  
4. Thresholds → action (STRONG_BUY/BUY/SELL/NEUTRAL)

The `Signal` collapses this into a single `confidence` + `action`. But the FINAL_SPEC requires the **individual component scores** to be available for:
- Meta-learner training (needs Bayesian and ML scores separately)
- Calibration analysis (per-component calibration plots)
- Reporting (§5.7.6 requires regime + signal breakdown)
- Backtest evaluation (AUC per component)

**Risk:** If `ensemble_v1` calls `bayesian_v1.generate()` and `ml_v1.generate()`, it only gets final `Signal` objects — not the raw probabilities needed for stacking.

**Fix:** Either:
- (a) Add a `raw_probability: float` field to `Signal` (distinct from `confidence`), so generators always expose the underlying score, OR
- (b) Add a separate `score()` method returning raw probability, keeping `generate()` for the fully-resolved signal, OR  
- (c) Use `metadata: dict` to carry component scores (least structured, but workable).

**Recommended approach:** Option (a). Add `probability: float` to `Signal` — the raw calibrated probability from the generator. The `action` field is then derived by the router/consumer using per-instrument thresholds. This preserves the meta-learner's ability to access raw scores.

### C-3: `backtest()` method creates parallel backtest infrastructure

**FINAL_SPEC §8** specifies a comprehensive backtest framework with walk-forward validation, purged K-fold, per-instrument fill models, pessimistic mode, regime-aware reporting, and bias controls. The backtest engine lives in `src/backtest/`.

**SPEC.v4 §2** gives each generator its own `backtest()` method that takes `historical_features` and returns `list[tuple[datetime, Signal]]`.

**Risks:**
- This creates two parallel backtest systems: the FINAL_SPEC backtest engine (which handles fill simulation, slippage, risk, walk-forward) and per-generator `backtest()` methods.
- The v4 `backtest()` method has no concept of walk-forward windows, embargo periods, fill simulation, or position management — it just generates signals. That's not backtesting; it's batch signal generation.
- If a generator's `backtest()` method is the primary test path, it bypasses all the realism controls from §6.2 and §8.

**Fix:** Rename `backtest()` to `generate_historical()` or `generate_batch()`. Make it explicit that this method provides **signal generation for historical data** — the actual backtesting (fill simulation, P&L, metrics) is handled by the backtest engine from FINAL_SPEC §8. The generator is a component *within* the backtest, not a standalone backtest system.

**Suggested edit (SPEC.v4 §1.2):**
```python
def generate_batch(
    self,
    instrument: str,
    historical_features: list[dict[str, Any]],
    config: GeneratorConfig
) -> list[tuple[datetime, Signal]]:
    """Generate signals for a sequence of historical feature snapshots.
    
    Used by the backtest engine (FINAL_SPEC §8) for walk-forward evaluation.
    Does NOT perform fill simulation, P&L calculation, or risk checks.
    """
    ...
```

Update §2 title from "Backtest Interface" to "Historical Signal Generation Interface" and add a cross-reference to FINAL_SPEC §8.

---

## Major Issues

### M-1: `features: dict[str, Any]` input is untyped and unspecified

**SPEC.v4 §1.2** `generate()` takes `features: dict[str, Any]` — a completely untyped bag. 

**FINAL_SPEC §4.3** has a well-specified feature store with namespaces, typed feature keys, and a defined query pattern. The Bayesian engine needs tokenized events (§5.2), the ML model needs OHLCV returns + indicator features (§5.5), and the meta-learner needs component scores + regime confidence (§5.6).

**Risk:** Each generator will need different feature shapes, but the interface doesn't express this. Callers won't know what to pass. Type safety is lost. Runtime errors will replace compile-time guarantees.

**Fix:** Define a `FeatureSnapshot` dataclass (or similar) that provides structured access to the feature store data. Generators can consume what they need. At minimum, document what keys each built-in generator expects.

```python
@dataclass
class FeatureSnapshot:
    """Structured feature data for a single timestamp."""
    instrument: str
    timestamp: datetime
    ohlcv: dict[str, float]  # open, high, low, close, volume
    indicators: dict[str, float]  # feature_key -> value (from feature store)
    tokens: list[str]  # active tokens for this candle
    regime: str | None  # current regime label
    regime_confidence: float | None
```

### M-2: Registry is a global mutable singleton — no lifecycle management

`GeneratorRegistry` uses class-level `_generators: dict` — a global mutable singleton.

**Risks:**
- No lifecycle management (init, shutdown, health checks for generators).
- No thread/async safety (concurrent registration/access).
- No validation that a registered generator actually conforms to the protocol at registration time.
- Testing becomes fragile (global state leaks between tests).

**Fix:** Make the registry an instance (injected via DI or app startup), not a class-level singleton. Add `validate_on_register` that instantiates and type-checks the generator. Add test isolation guidance (fresh registry per test).

### M-3: Routing config lacks fallback behavior specification

**SPEC.v4 §1.4** shows routing with `primary` and `fallback` per instrument, but doesn't specify:
- **When** does fallback activate? (Generator raises exception? Returns low-confidence signal? Is disabled in config?)
- **How** is fallback logged/alerted? (This is a trading system — silent failover is dangerous.)
- What happens if **both** primary and fallback fail?
- Does fallback apply per-signal or does the instrument switch generators persistently?

**Fix:** Define explicit fallback triggers and behavior:
```
Fallback activates when:
1. Primary generator raises an exception during generate()
2. Primary generator is disabled in config (enabled: false)

Fallback does NOT activate for:
- Low confidence signals (that's the generator's valid output)

If both primary and fallback fail: halt signal generation for that instrument. Alert (CRITICAL).
Fallback activation is logged as WARNING and exposed as Prometheus metric.
```

### M-4: No versioning/compatibility contract between generators and features

**SPEC.v4 §1.2** has a `version` property on generators but no specification of what constitutes a breaking change, how versions are compared, or what happens when a generator's expected feature set changes.

**Risk:** A generator trained on feature set X may silently produce garbage when fed feature set Y after a feature store change. FINAL_SPEC §5.5 specifies ML models trained on specific feature sets — model/feature drift is a real concern.

**Fix:** Generators should declare their required features (at minimum as metadata). The registry or router should validate that the feature store can satisfy the generator's requirements before routing signals to it.

### M-5: `update_signal_config` API endpoint lacks governance

**SPEC.v4 §1.5** has `POST /api/v1/signals/config` to update signal configuration at runtime. FINAL_SPEC §13.2 requires explicit human approval for strategy changes, with evidence bundles and audit trails.

**Risk:** The v4 API allows hot-swapping signal generators without the governance gates from FINAL_SPEC §13. This could circumvent the approval workflow.

**Fix:** Signal config changes must go through the same governance pipeline as strategy changes:
- Changes are proposed (not immediately active).
- Require approval with evidence.
- Logged to `config_changes` table.
- Generator routing changes are equivalent to strategy activation changes and require the same approval level.

### M-6: TASKS.md has duplicate task IDs

`TASKS.md` has two `N-202`, two `N-203`, and two `N-204` entries — one set from SPEC.v4 (SignalGenerator tasks) and one set from FINAL_SPEC (event detection tasks). This will cause confusion in commit references and status tracking.

**Fix:** Renumber the SPEC.v4 tasks or use a sub-ID scheme:
- `N-201` → SignalGenerator interface + Registry (keep)
- `N-202a` → Event detection engine core (from FINAL_SPEC)
- `N-202b` → bayesian_v1 as SignalGenerator (from SPEC.v4)
- Or renumber the v4 tasks as N-250, N-251, N-252, N-253.

---

## Minor Issues

### m-1: `Signal.generated_at` vs FINAL_SPEC timestamp conventions

FINAL_SPEC §4.5 mandates all timestamps are `TIMESTAMPTZ` (timezone-aware UTC). The `Signal` dataclass uses `datetime` without specifying timezone awareness. Should enforce `datetime` as UTC-aware per project convention.

### m-2: `GeneratorConfig.parameters` is fully untyped

`parameters: dict[str, Any]` means no schema validation at the config level. FINAL_SPEC uses typed JSON schemas for all configuration. Consider adding per-generator config schemas via the `validate_config()` method, and document that generators MUST validate their params.

### m-3: `ensemble_v1` is both a generator and a consumer of generators

The ensemble appears in the generators list but also references other generators as components. The interface doesn't distinguish between leaf generators (produce signals from features) and composite generators (combine other generators' outputs). This works but should be documented explicitly to avoid circular dependency confusion.

### m-4: Missing `async` on `generate()` method

FINAL_SPEC's `FeatureProvider.get_features()` is `async`. If generators need to query the feature store or call async infrastructure, `generate()` should be `async def generate(...)`. The current sync signature may force blocking calls or awkward workarounds.

### m-5: Open questions (§7) need deadlines

The three open questions (hot-reload, version conflicts, shadow mode) are valid but have no resolution timeline. Recommend: decide hot-reload before Stage 2 implementation (it affects the registry design), defer shadow mode to Stage 7 (paper trading), and resolve version conflicts as part of M-4 fix.

### m-6: No `__str__` / `__repr__` on Signal for logging

Given the importance of structured logging (FINAL_SPEC §11.1), `Signal` should have a well-defined string representation for log output.

---

## Suggested Edits by File/Section

### SPEC.v4.md

| Section | Edit | Priority |
|---------|------|----------|
| §1.2 `Signal.action` | Change to `Literal["STRONG_BUY", "BUY", "SELL", "NEUTRAL"]`; note `SHORT` reserved for v2 | **Critical** |
| §1.2 `Signal` fields | Add `probability: float` field for raw score | **Critical** |
| §1.2 `generate()` features param | Replace `dict[str, Any]` with typed `FeatureSnapshot` or document expected keys per generator | **Major** |
| §1.2 `backtest()` | Rename to `generate_batch()`; clarify it feeds into FINAL_SPEC §8 backtest engine | **Critical** |
| §1.3 `GeneratorRegistry` | Convert from class-singleton to instance; add validation on register | **Major** |
| §1.4 Routing | Add explicit fallback trigger rules and failure behavior | **Major** |
| §1.5 API | Add governance requirements cross-referencing FINAL_SPEC §13 | **Major** |
| §2 | Retitle "Historical Signal Generation"; add cross-ref to FINAL_SPEC §8 | **Critical** |
| §3.3 `ensemble_v1` | Document as composite generator; note it requires component generators to be registered first | **Minor** |
| §7 Open Questions | Add resolution timeline; decide hot-reload before Stage 2 starts | **Minor** |
| New section | Add "Compatibility with FINAL_SPEC" section explicitly mapping v4 concepts to FINAL_SPEC sections | **Major** |

### TASKS.md

| Section | Edit | Priority |
|---------|------|----------|
| Stage 2 task IDs | Renumber to eliminate N-202/N-203/N-204 duplicates | **Major** |

### FINAL_SPEC.md

| Section | Edit | Priority |
|---------|------|----------|
| §3.1 Architecture diagram | No change needed now; v4 is additive | — |
| §5.4-5.6 | Add forward reference: *"Signal generation components implement the SignalGenerator interface defined in SPEC.v4"* | **Minor** (only after v4 is approved) |

---

## Recommended Governance Approach

### Keep FINAL_SPEC + SPEC.v4 as addendum (RECOMMENDED)

**Rationale:**
1. FINAL_SPEC is a battle-tested, internally consistent 2100+ line document. Merging v4 into it risks introducing inconsistencies and makes future diffs harder to review.
2. SPEC.v4's scope is narrow (signal generation interface layer) and doesn't touch data, risk, execution, backtest, or UI specs.
3. The addendum model matches Newton's existing governance: FINAL_SPEC is the baseline, v4 is an architectural extension.
4. Future signal architecture changes can be tracked as v4.1, v4.2, etc. without touching the baseline.

**Implementation:**
- SPEC.v4 becomes the authoritative document for signal generation architecture.
- FINAL_SPEC remains authoritative for everything else (data, risk, execution, backtest, strategy engine internals, UI, governance).
- Where v4 and FINAL_SPEC overlap (signal actions, backtest), v4 must explicitly reference and align with FINAL_SPEC sections.
- Add to FINAL_SPEC Decision Log: `D-22: Modular signal architecture via SPEC.v4 addendum`.
- TASKS.md `Source of truth` line is already correct: `FINAL_SPEC.md + SPEC.v4.md (signal architecture)`.

**Do NOT produce a merged baseline** unless/until:
- v4 has been implemented and validated through at least Stage 2+3.
- The interface has stabilized.
- At that point, a FINAL_SPEC v2 could incorporate the signal architecture natively.

---

## Readiness Decision for Stage 2 Kickoff

### CONDITIONAL GO

Stage 2 can proceed **after resolving the three Critical issues (C-1, C-2, C-3)**:
1. Fix the `Signal.action` vocabulary to match FINAL_SPEC.
2. Add `probability` field (or equivalent) to `Signal` for meta-learner compatibility.
3. Rename `backtest()` to `generate_batch()` and clarify relationship with FINAL_SPEC backtest engine.

**Major issues (M-1 through M-6)** should be resolved during early Stage 2 implementation (specifically during N-201 SignalGenerator interface task). They are design-level concerns that naturally get resolved when writing the actual code and tests.

**Estimated effort to resolve Critical issues:** 1-2 hours of spec editing. No code impact (zero-code baseline still holds for these changes).

**Stage 2 implementation order recommendation:**
1. Fix SPEC.v4 (Critical issues) → approve as addendum
2. N-201: SignalGenerator interface + Registry (resolves M-1, M-2, M-4 during implementation)  
3. N-202+: Event detection, tokenization (FINAL_SPEC tasks)
4. N-203+: bayesian_v1 as SignalGenerator implementation
5. Fix TASKS.md duplicate IDs (M-6)

---

*Review complete. This document is the independent architectural assessment and does not constitute approval — BJ retains approval authority per FINAL_SPEC §13.2.*
