# Stage 5: Trading Engine

## Code Review

- **Date:** 2026-03-05
- **Scope:** Full Stage 5 — BrokerAdapter protocol, Oanda/Binance adapters, risk management, circuit breakers, order executor, position reconciler, trading API endpoints (T-501 through T-508)

### Quality Gate
- lint: PASS — `ruff check .` all checks passed
- types: PASS — `mypy src` no issues in 64 source files
- tests: PASS — 661 passed, 93% global coverage

### Stage 5 Module Coverage
| Module | Stmts | Miss | Coverage |
|--------|-------|------|----------|
| `src/api/v1/trading.py` | 162 | 0 | 100% |
| `src/trading/broker_base.py` | 48 | 0 | 100% |
| `src/trading/broker_oanda.py` | 166 | 37 | 78% |
| `src/trading/broker_binance.py` | 173 | 41 | 76% |
| `src/trading/circuit_breaker.py` | 194 | 0 | 100% |
| `src/trading/executor.py` | 171 | 0 | 100% |
| `src/trading/reconciler.py` | 94 | 0 | 100% |
| `src/trading/risk.py` | 145 | 0 | 100% |

### Findings

#### Critical
None.

#### Warning

- [W-1] **[src/trading/risk.py:387-409]** In-trade controls are direction-blind for SELL trades. `profit_pct = (current_price - entry_price) / entry_price` only works for BUY. For SELL trades, a profitable move (price going down) yields a negative `profit_pct`, so trailing stop activation/advance never triggers. Conversely, a price move against a short position (price up) shows as positive profit, which would incorrectly trigger trailing logic. Time stop and volatility stop are unaffected (direction-independent). Hard stops are set correctly per direction in `executor._compute_stop_loss`. **Impact:** Trailing stop management broken for short positions — profitable shorts never get breakeven protection.

- [W-2] **[src/trading/executor.py:189,232]** `execute_signal` declares `portfolio_config: object` (line 189) then passes it with `# type: ignore[arg-type]` (line 232) to `run_pre_trade_checks` which expects `RiskPortfolio`. Functionally correct because callers pass `RiskPortfolio`, but the loose typing masks potential misuse at the type-checker level.

- [W-3] **[src/trading/broker_oanda.py, src/trading/broker_binance.py]** Broker adapter coverage at 78% and 76% respectively. The uncovered lines correspond to the real HTTP client classes (`UrllibOandaTradingClient`, `UrllibBinanceTradingClient`) and some error paths. Expected for real HTTP implementations but should be improved with integration tests in a later stage.

#### Note

- [N-1] **[src/trading/circuit_breaker.py:89-108]** `CircuitBreakerManager` uses mutable state (dicts, booleans) without synchronization. Safe for the current single-developer, single-process architecture (DEC-003), but would need locks/atomic operations if concurrent access is introduced.

- [N-2] **[src/trading/executor.py:519]** Bare `except Exception: pass` in idempotency check swallows all exceptions (including `TypeError`, `ValueError`) when the order doesn't exist. A narrower exception type (e.g., `KeyError`, `LookupError`) would be safer.

- [N-3] **[src/trading/reconciler.py:170]** Reconciliation classifies by `(instrument, direction)` presence but doesn't compare unit counts. Two records MATCH even if broker says 1000 units and system says 500. The details dict includes counts for manual review but there's no automated mismatch detection for quantity discrepancies.

- [N-4] **[tests/unit/test_broker_binance.py:405]** Weak assertion: `assert len(result) >= 0` in `TestGetCandles.test_returns_candles` always passes regardless of actual result. Should assert a specific expected count.

- [N-5] **[src/trading/risk.py:286,299]** Model freshness threshold (30 days) and regime confidence threshold (0.2) are hardcoded. These follow SPEC §6.3 values but could be config parameters for operational flexibility.

- [N-6] **[src/api/v1/trading.py:190-196]** Module-level `_service` global for dependency injection. Tests handle this by calling `configure()` in setup, but there's no automatic cleanup between tests — state could bleed if test ordering changes.

### Spec Compliance

- **§6.1 Config Architecture:** ✅ 3-tier precedence (instrument > strategy > global) correctly implemented in `resolve_risk_config`
- **§6.2 Global Risk Defaults:** ✅ All risk parameters present in `RiskDefaults` schema with Pydantic validation
- **§6.3 Pre-Trade Checks:** ✅ All 7 checks implemented (position limit, portfolio exposure, circuit breaker, data freshness, model freshness warning, regime confidence, position sizing via Kelly)
- **§6.4 In-Trade Controls:** ⚠️ Time stop and volatility check correct; trailing stop logic broken for SELL direction (W-1)
- **§6.5 Circuit Breakers:** ✅ All 5 types implemented (daily loss, max drawdown, consecutive losses, model degradation, kill switch) with correct scoping
- **§8.1 REST API:** ✅ All trading endpoints implemented (`GET /trades`, `POST /kill`, `DELETE /kill`, `GET /config/risk`, `PUT /config/risk`)
- **§4.2 Config Changes:** ✅ Audit logging for kill switch and risk config changes via `ConfigChangeStore`
- **§5.9/§5.11 Order Execution:** ✅ Full lifecycle with idempotency check
- **§5.12 Position Reconciliation:** ✅ MATCH/SYSTEM_EXTRA/BROKER_EXTRA classification with correct actions

### Pattern Compliance

- ✅ `@dataclass(frozen=True)` on all domain models (DEC-010)
- ✅ Protocol-based abstractions for all boundaries: `BrokerAdapter`, `TradeStore`, `ReconciliationStore`, `ConfigChangeStore`, `OandaTradingHTTPClient`, `BinanceTradingHTTPClient` (DEC-005)
- ✅ Config-driven design with Pydantic v2 validation (DEC-007)
- ✅ Registry pattern not applicable to this stage's scope
- ✅ In-memory fakes for all protocols used in tests (no fragile mock.patch)
- ✅ No secrets or API keys in source code
- ✅ API responses validated via Pydantic models
- ✅ Error responses don't leak internals (503 for unconfigured service, 400 for missing confirmation, 422 for validation)

### Positive Observations

1. **Excellent test coverage** — 100% on 6 of 8 Stage 5 modules. Tests use concrete fakes rather than `mock.patch`, making them resilient to refactoring.
2. **Clean quality gate** — Zero lint issues, zero type errors across 64 source files.
3. **Well-structured domain models** — Consistent use of frozen dataclasses with clear ownership boundaries between modules.
4. **Idempotent order execution** (§5.11) — Properly checks for existing filled orders before placing new ones, preventing double execution.
5. **Kill switch has defense in depth** — Confirmation required on deactivation, audit logged, positions closed through executor chain.
6. **Reconciliation handles edge cases well** — Broker API failures return empty (no crash), trades without broker IDs excluded, per-broker isolation prevents cross-contamination.

### Verdict
**Needs fixes** — W-1 (direction-blind trailing stops) is a functional bug that should be addressed before the stage gate. W-2 and W-3 are lower priority but recommended.

---

## Red Team Review

- **Date:** 2026-03-05
- **Reviewer:** Adversarial Subagent (fresh context)
- **Scope:** Stage 5: Trading Engine — T-501 through T-508

### Quality Gate
- lint: PASS
- types: PASS
- tests: PASS — 661 passed, coverage 93%

### Critical
- [RC-1] **[src/trading/broker_binance.py:119-126]** Binance `_fetch()` enforces `isinstance(data, dict)` but `/api/v3/klines` returns a JSON array. `get_candles()` will always throw `ValueError` when called against the real Binance API. The data fetcher (`fetcher_binance.py`) correctly accepts `list[list[Any]]` but the trading adapter wraps the same endpoint with this incompatible type check.
- [RC-2] **[src/trading/broker_binance.py:219]** `data.get("candles", [])` looks up a key that doesn't exist in the Binance klines response (which is a raw array, not a dict). Silently returns zero candles.
- [RC-3] **[src/trading/broker_binance.py:302,308,338]** `modify_stop_loss()` and `close_position()` hardcode `quantity: "0.01"`. Will leave unprotected residual positions regardless of actual position size.
- [RC-4] **[src/trading/broker_oanda.py:248]** Kelly sizing returns dollar risk amount but it's passed directly as trade quantity (instrument units). `units = equity * risk_pct` produces a dollar amount, not instrument units. Position sizes will be systematically wrong.
- [RC-5] **[src/trading/broker_binance.py:245-248]** `get_positions()` always returns `[]`. Reconciliation will classify every internal BTC_USD OPEN trade as SYSTEM_EXTRA and force-close it. Catastrophic for real Binance positions.

### High
- [RH-1] **[src/trading/risk.py]** `gap_risk_multiplier`, `high_volatility_size_reduction`, `high_volatility_stop_pct` are carried in config but never used in any calculation — SPEC §6.4 violations.
- [RH-2] **[src/trading/circuit_breaker.py:150-153]** Daily loss breaker silently untrips when equity recovers intraday. SPEC §6.5 says reset only at 00:00 UTC.
- [RH-3] **[src/trading/circuit_breaker.py]** SPEC §6.5 requires daily_loss to "Close positions; halt entries" and max_drawdown to "Close all; halt all." No caller triggers position closure for non-kill-switch breakers.
- [RH-4] **[src/trading/executor.py:519-521]** Idempotency check `except Exception: pass` swallows all exceptions. Network/auth failures fall through to place duplicate orders.
- [RH-5] **[src/trading/broker_binance.py:252-286]** `place_market_order` does NOT place a stop-loss order after entry fill. SPEC §5.9 requires OCO placement for Binance. The `stop_loss` parameter is accepted but ignored.
- [RH-6] **[src/trading/broker_binance.py:301-302]** `modify_stop_loss` hardcodes `"side": "SELL"`, assumes always long.
- [RH-7] **[src/api/v1/trading.py:190-196]** Module-level mutable global state. Concurrent PUT `/config/risk` requests could create race conditions.

### Medium
- [RM-1] **[src/trading/broker_base.py:86-92]** `make_client_order_id` uses millisecond timestamp — can collide in tight loops. Test allows only 1 unique from 100 calls.
- [RM-2] **[src/trading/risk.py:202-205]** Kelly sizing produces dollar risk, not instrument units. Missing price/stop-distance conversion.
- [RM-3] **[src/trading/risk.py:298-305]** Regime confidence `passed=False` but doesn't block trading — misleading check result.
- [RM-4] **[src/trading/broker_oanda.py:377-396]** Fragile Oanda timestamp parser with complex string slicing.
- [RM-5] **[src/trading/risk.py:389-406]** Trailing stop naming inverted — "activation" at lower threshold, "advance/breakeven" at higher.
- [RM-6] **[src/trading/broker_binance.py:104]** No `recvWindow` parameter. Binance rejects timestamps >1000ms from server time.

### Low
- [RL-1] **[src/trading/broker_oanda.py:30]** `OANDA_BASE_URL` points to practice environment. Appropriate for pre-production.
- [RL-2] **[src/trading/executor.py:512]** Idempotency path hardcodes `direction="BUY"` regardless of actual direction.
- [RL-3] **[src/trading/broker_oanda.py:267-277]** `modify_stop_loss` returns placeholder values in OrderResult.
- [RL-4] **[src/trading/circuit_breaker.py:477]** `_rolling_sharpe` uses population variance and is not annualized.
- [RL-5] **[tests/unit/test_broker_binance.py:405]** Tautological assertion `assert len(result) >= 0`.

### Test Gaps
- [TG-1] **[broker_binance.py:place_market_order]** No test for stop-loss placement after entry fill (not implemented — RH-5).
- [TG-2] **[risk.py:gap_risk_multiplier, high_volatility_*]** No tests because not implemented (RH-1).
- [TG-3] **[circuit_breaker.py:daily_loss]** No test for position closure on non-kill-switch breaker trip.
- [TG-4] **[broker_binance.py:get_candles]** Test wraps response in `{"candles": ...}` matching broken implementation, not real API. Tests the mock.
- [TG-5] **[reconciler + Binance]** No test for reconciler with Binance adapter's empty positions against open internal trades.
- [TG-6] **[trading API]** No thread-safety test for mutable service global.
- [TG-7] **[executor.py:execute_signal with SELL]** No test for long-only SELL behavior per SPEC §2.2.

### Positive Observations
1. Excellent protocol-based design — textbook DEC-005 application.
2. Comprehensive circuit breaker coverage with correct scoping.
3. Good retry logic with 3x exponential backoff and correct 4xx exclusion.
4. Thorough executor lifecycle testing — 100% coverage on executor, circuit_breaker, reconciler, risk.
5. Clean frozen dataclass usage per DEC-010.
6. Good audit logging pattern with before/after values and actor attribution.

### Verdict
**FAIL** — 5 critical findings must be addressed before stage gate. RC-1/RC-2 (Binance candle retrieval broken), RC-3 (hardcoded 0.01 BTC quantity), RC-4 (dollar risk conflated with instrument units), RC-5 (reconciliation will force-close every BTC position).

---

## Stage Report

- **Date:** 2026-03-05
- **Status:** PENDING
- **Sign-off:** —

#### Quality Gate Summary
- lint: PASS
- types: PASS
- tests: PASS — 661 passed, 93% global coverage

#### Unified Findings

##### Critical (must fix)

- [SR-C1] **[src/trading/broker_binance.py:119-126,219]** Binance candle retrieval broken — `_fetch()` enforces `isinstance(data, dict)` but `/api/v3/klines` returns a JSON array; `get_candles()` then looks up non-existent `"candles"` key, silently returning zero candles. Source: RC-1 + RC-2.
  - **Impact:** Binance candle data is completely unavailable through the trading adapter. Any feature relying on trading-adapter candles for BTC_USD will operate on empty data.
  - **Remediation:** Refactor `_fetch()` to accept both dict and list responses. Fix `get_candles()` to parse the raw klines array directly (matching `fetcher_binance.py` pattern). Fix test fake to return real API response format.

- [SR-C2] **[src/trading/broker_binance.py:302,308,338]** Hardcoded `quantity: "0.01"` in `modify_stop_loss()` and `close_position()` — ignores actual position size. Source: RC-3.
  - **Impact:** Stop-loss modifications protect only 0.01 BTC regardless of position size; close_position leaves residual unprotected BTC.
  - **Remediation:** Accept and use actual position quantity. `modify_stop_loss` should query current position size or accept it as parameter. `close_position` should close the full position.

- [SR-C3] **[src/trading/risk.py:202-205, src/trading/broker_oanda.py:248]** Kelly sizing returns dollar risk amount (`equity * risk_pct`) but the value is used directly as instrument units. Missing price/stop-distance conversion to translate dollar risk into forex lots or BTC quantity. Source: RC-4 + RM-2.
  - **Impact:** Position sizes systematically wrong for both instruments. A $1000 dollar risk on EUR_USD would be sent as 1000 units instead of the correct lot size based on current price and stop distance.
  - **Remediation:** Add unit conversion: `units = dollar_risk / (stop_distance_per_unit)` where stop distance accounts for instrument pip/tick size and current price.

- [SR-C4] **[src/trading/broker_binance.py:245-248]** `get_positions()` always returns `[]` — reconciliation classifies every internal BTC_USD OPEN trade as SYSTEM_EXTRA and force-closes it. Source: RC-5.
  - **Impact:** Catastrophic for real Binance positions. Every reconciliation cycle would attempt to close all BTC trades.
  - **Remediation:** Implement `get_positions()` using Binance `GET /api/v3/account` to retrieve actual balances/positions.

##### High (should fix)

- [SR-H1] **[src/trading/risk.py:387-409]** In-trade trailing stop logic is direction-blind — `profit_pct = (current_price - entry_price) / entry_price` only works for BUY. Short positions never get breakeven protection; price moves against shorts incorrectly trigger trailing logic. Source: W-1 + RM-5.
  - **Impact:** Trailing stop management completely broken for short positions.
  - **Remediation:** Compute `profit_pct` direction-aware: for SELL, use `(entry_price - current_price) / entry_price`.

- [SR-H2] **[src/trading/broker_binance.py:252-286]** `place_market_order` accepts but ignores the `stop_loss` parameter — no OCO or separate stop-loss order placed after entry fill. SPEC §5.9 requires OCO placement for Binance. Source: RH-5.
  - **Impact:** Binance trades have no automatic stop-loss protection after entry.
  - **Remediation:** After market order fill, place a STOP_LOSS_LIMIT order. If that fails, close the position and alert (per SPEC §5.9 fallback).

- [SR-H3] **[src/trading/broker_binance.py:301-302]** `modify_stop_loss` hardcodes `"side": "SELL"` — assumes all positions are long. Source: RH-6.
  - **Impact:** Stop-loss modification for short positions would place the wrong order side.
  - **Remediation:** Derive side from position direction (SELL side for long positions, BUY side for short).

- [SR-H4] **[src/trading/circuit_breaker.py:150-153]** Daily loss breaker silently untrips when equity recovers intraday. SPEC §6.5 requires reset only at 00:00 UTC. Source: RH-2.
  - **Impact:** Risk limit can be bypassed by intraday equity recovery — trades resume even after the daily loss threshold was hit.
  - **Remediation:** Latch the daily loss breaker once tripped; only reset via the scheduled 00:00 UTC reset.

- [SR-H5] **[src/trading/circuit_breaker.py]** Non-kill-switch breakers (daily_loss, max_drawdown) don't trigger position closure. SPEC §6.5 requires daily_loss to "Close positions; halt entries" and max_drawdown to "Close all; halt all." Source: RH-3.
  - **Impact:** Tripped breakers halt new entries but leave existing positions unprotected.
  - **Remediation:** Add position closure callback/hook when daily_loss or max_drawdown breakers trip.

- [SR-H6] **[src/trading/executor.py:519-521]** Idempotency check `except Exception: pass` swallows all exceptions — network/auth failures silently fall through to place duplicate orders. Source: RH-4 + N-2.
  - **Impact:** Duplicate order risk on transient failures during idempotency lookup.
  - **Remediation:** Narrow to `KeyError`/`LookupError` for "order not found" case. Re-raise or handle network/auth exceptions explicitly.

##### Medium (recommend)

- [SR-M1] **[src/trading/risk.py]** `gap_risk_multiplier`, `high_volatility_size_reduction`, `high_volatility_stop_pct` carried in config but never used in calculations — SPEC §6.4 drift. Source: RH-1.
- [SR-M2] **[src/trading/executor.py:189,232]** `portfolio_config: object` with `# type: ignore[arg-type]` — loose typing masks potential misuse. Source: W-2.
- [SR-M3] **[src/trading/broker_base.py:86-92]** `make_client_order_id` uses millisecond timestamp — can collide in tight loops. Source: RM-1.
- [SR-M4] **[src/trading/risk.py:298-305]** Regime confidence `passed=False` doesn't block trading — misleading check result. Source: RM-3.
- [SR-M5] **[src/trading/broker_oanda.py:377-396]** Fragile Oanda timestamp parser with complex string slicing. Source: RM-4.
- [SR-M6] **[src/trading/broker_binance.py:104]** No `recvWindow` parameter — Binance rejects timestamps >1000ms from server time. Source: RM-6.
- [SR-M7] **[src/trading/reconciler.py:170]** Reconciliation doesn't compare unit counts — quantity mismatches pass as MATCH. Source: N-3.
- [SR-M8] **[src/api/v1/trading.py:190-196]** Module-level mutable `_service` global. Safe per DEC-003 (single-process) but fragile for test isolation. Source: RH-7 + N-6.

##### Low (noted)

- [SR-L1] **[src/trading/broker_oanda.py:30]** `OANDA_BASE_URL` points to practice environment — appropriate for pre-production. Source: RL-1.
- [SR-L2] **[src/trading/executor.py:512]** Idempotency path hardcodes `direction="BUY"` — system is long-only per SPEC §2.2 but should track actual direction. Source: RL-2.
- [SR-L3] **[src/trading/broker_oanda.py:267-277]** `modify_stop_loss` returns placeholder values in OrderResult. Source: RL-3.
- [SR-L4] **[src/trading/circuit_breaker.py:477]** `_rolling_sharpe` uses population variance and is not annualized. Source: RL-4.
- [SR-L5] **[tests/unit/test_broker_binance.py:405]** Tautological assertion `assert len(result) >= 0`. Source: RL-5 + N-4.
- [SR-L6] **[src/trading/risk.py:286,299]** Hardcoded freshness/confidence thresholds (follow SPEC §6.3 values). Source: N-5.
- [SR-L7] **[src/trading/broker_oanda.py, broker_binance.py]** Broker adapter coverage at 78%/76% — expected for real HTTP implementations, defer to integration testing stage. Source: W-3.

#### Test Gap Summary

- [SR-TG1] **[broker_binance.py:place_market_order]** No test for stop-loss placement after entry fill — feature not implemented (SR-H2). Source: TG-1.
- [SR-TG2] **[risk.py:gap_risk_multiplier, high_volatility_*]** No tests because not implemented (SR-M1). Source: TG-2.
- [SR-TG3] **[circuit_breaker.py:daily_loss]** No test for position closure on non-kill-switch breaker trip. Source: TG-3.
- [SR-TG4] **[broker_binance.py:get_candles]** Test wraps response in `{"candles": ...}` matching broken code, not real Binance API — tests the mock, not the logic. Source: TG-4.
- [SR-TG5] **[reconciler + Binance]** No test for reconciler with Binance adapter's empty positions against open internal trades. Source: TG-5.
- [SR-TG6] **[trading API]** No thread-safety test for mutable service global — low priority per DEC-003. Source: TG-6.
- [SR-TG7] **[executor.py:execute_signal with SELL]** No test for SELL signal execution behavior per SPEC §2.2. Source: TG-7.

#### Contradictions Between Reviews

Code Review found no Critical findings; Red Team found 5 Critical. This is not a true contradiction — the Code Review assessed correctness against the test fakes (which pass), while the Red Team compared implementations against real broker API contracts and discovered the fakes were masking fundamental bugs (e.g., TG-4: Binance candle test matches the broken implementation, not the real API). The Red Team's deeper analysis is correct — these are genuine critical issues.

#### User Interview Notes

Interview skipped (session continuation). No additional context from user beyond the review findings.

#### Positive Observations

1. **Excellent protocol-based design** — textbook DEC-005 application across all boundaries (BrokerAdapter, TradeStore, ReconciliationStore, ConfigChangeStore, HTTP clients).
2. **Outstanding test coverage** — 100% on 6 of 8 Stage 5 modules (risk, circuit_breaker, executor, reconciler, trading API, broker_base). Tests use concrete fakes, not `mock.patch`.
3. **Clean quality gate** — zero lint issues, zero type errors across 64 source files, 93% global coverage.
4. **Well-structured domain models** — consistent frozen dataclasses (DEC-010) with clear ownership boundaries.
5. **Defense-in-depth kill switch** — confirmation required on deactivation, audit logged, positions closed through executor chain.
6. **Good retry logic** — 3x exponential backoff with correct 4xx exclusion in both broker adapters.
7. **Idempotent order execution** (§5.11) — properly checks for existing filled orders before placing new ones.
8. **Clean audit logging** — before/after values with actor attribution for all config changes.

#### Remediation Tasks

| ID | Task | Scope | Acceptance | Status |
|---|---|---|---|---|
| T-508-FIX1 | Binance adapter critical fixes: candle retrieval, get_positions, OCO stop-loss, dynamic quantity, direction-aware stop modification | server | `_fetch()` accepts JSON arrays; `get_candles()` parses raw klines array correctly; `get_positions()` returns actual positions from `/api/v3/account`; `place_market_order` places stop-loss order after fill (or closes + alerts on failure); `modify_stop_loss`/`close_position` use actual position quantity; `modify_stop_loss` derives side from direction; candle test uses real API response format; all tests pass with 100% coverage on changed code | TODO |
| T-508-FIX2 | Position sizing units conversion: dollar risk to instrument units | server | Kelly sizing output converted from dollar risk to instrument units using price/stop-distance; Oanda adapter sends correct lot size; Binance adapter sends correct BTC quantity; tests verify conversion math for both instruments; existing risk tests updated | TODO |
| T-508-FIX3 | Risk engine and circuit breaker spec compliance fixes | server | Trailing stop logic direction-aware for SELL trades; daily loss breaker latches once tripped (reset only at 00:00 UTC); non-kill-switch breakers trigger position closure callback; idempotency check uses narrow exception type (`KeyError`/`LookupError`); tests cover SELL trailing stops, daily loss latch behavior, breaker position closure, and narrow exception handling | TODO |

#### Verdict

**NOT READY** — 4 Critical and 6 High findings must be addressed before the stage gate. The Binance adapter has multiple fundamental issues (broken candle retrieval, empty positions, no OCO stop-loss, hardcoded quantities) that would cause real financial harm in production. Position sizing conflates dollar risk with instrument units across both brokers. Risk engine trailing stops and circuit breaker reset behavior violate SPEC §6.4/§6.5. Three remediation tasks (T-508-FIX1, T-508-FIX2, T-508-FIX3) have been added to TASKS.md to address all Critical and High findings.
