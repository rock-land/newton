# Newton Decisions Log

Purpose: Record key engineering/product decisions and rationale to prevent drift and re-litigation.

Format:
- ID: DEC-XXX
- Date
- Decision
- Context
- Consequences
- Status: Proposed / Accepted / Superseded

---

## DEC-001
- **Date:** 2026-02-19
- **Decision:** `SPEC.md` is the canonical specification. Decision precedence: `DECISIONS.md` > `SPEC.md`.
- **Context:** A single source of truth prevents ambiguity and spec drift.
- **Consequences:** Implementation must follow SPEC.md unless a decision log entry explicitly overrides it.
- **Status:** Accepted

## DEC-002
- **Date:** 2026-02-19
- **Decision:** Git workflow enforces stage branches with push on each task completion.
- **Context:** Avoid local-only drift and ensure progress is auditable.
- **Consequences:** On each task marked DONE, commit + push to current stage branch; merge to `main` only at stage completion.
- **Status:** Accepted

## DEC-003
- **Date:** 2026-02-19
- **Decision:** Python 3.11+ monolith with FastAPI as the server framework.
- **Context:** Solo developer (A6); manageable complexity. Modules separated by directory and interface; extraction to services deferred to when needed. FastAPI chosen for async support, automatic OpenAPI docs, and Pydantic integration.
- **Consequences:** All server code lives in `src/`. No microservice boundaries. Type hints required throughout (mypy strict mode).
- **Status:** Accepted

## DEC-004
- **Date:** 2026-02-19
- **Decision:** TimescaleDB (PostgreSQL 16 + TimescaleDB extension) for all time-series storage.
- **Context:** OHLCV candles and features are time-series data. TimescaleDB hypertables optimize range queries, compression, and retention policies. PostgreSQL provides relational capabilities for non-time-series data (trades, config, reconciliation).
- **Consequences:** `ohlcv` and `features` tables are hypertables. Requires Docker (or managed service) for TimescaleDB. Connection via psycopg (binary).
- **Status:** Accepted

## DEC-005
- **Date:** 2026-02-19
- **Decision:** Protocol-based abstractions over inheritance for all pluggable components.
- **Context:** Python `Protocol` classes (PEP 544) enable structural subtyping, making components testable via duck typing without inheritance coupling. Enables clean mocking in tests.
- **Consequences:** `FeatureProvider`, `SignalGenerator`, `BrokerAdapter`, and HTTP client interfaces are all `Protocol` classes. Implementations satisfy the protocol without inheriting from it.
- **Status:** Accepted

## DEC-006
- **Date:** 2026-02-19
- **Decision:** TA-Lib as the canonical technical indicator engine with pure Python fallback.
- **Context:** SPEC.md §2.1 mandates preferring mature, well-tested libraries. TA-Lib is the industry standard. Pure Python fallback ensures the system runs in environments where the C library is unavailable.
- **Consequences:** `src/data/indicators.py` implements dual-mode: TA-Lib when available, manual computation otherwise. Parity tests verify equivalence between implementations.
- **Status:** Accepted

## DEC-007
- **Date:** 2026-02-19
- **Decision:** Configuration-driven design with Pydantic v2 validation and cross-field constraints.
- **Context:** All system parameters must be externalized (SPEC.md §7). Pydantic v2 provides runtime validation with type coercion, cross-field validators, and JSON schema generation.
- **Consequences:** Config schemas live in `src/data/schema.py`. Config files in `config/` directory. Precedence: per-instrument `risk_overrides` > global `risk.json` defaults. Invalid config fails fast at load time.
- **Status:** Accepted

## DEC-008
- **Date:** 2026-02-19
- **Decision:** Dual-broker architecture: Oanda (EUR/USD forex spot) and Binance (BTC/USD crypto spot BTCUSDT pair).
- **Context:** SPEC.md §1.2 mandates two instruments from day one to force true multi-instrument architecture. v1 is spot-only — no futures, leverage, or margin.
- **Consequences:** Separate fetcher implementations per broker. `BrokerAdapter` protocol unifies order/position management. Volume normalization differs (Oanda: base currency, Binance: quote currency USDT).
- **Status:** Accepted

## DEC-009
- **Date:** 2026-02-19
- **Decision:** Staged scaffold pattern — empty module files retained across all stages to lock API naming.
- **Context:** Prevents naming drift between stages. Module files (events.py, bayesian.py, broker_base.py, etc.) exist as scaffolds with TODO comments referencing their target stage.
- **Consequences:** Empty modules have a single docstring. They are not dead code — they are placeholders aligned to SPEC.md section references. Do not delete them.
- **Status:** Accepted

## DEC-010
- **Date:** 2026-02-19
- **Decision:** Immutable frozen dataclasses for all domain models.
- **Context:** Prevents accidental mutation of candle records, signals, features, and other domain objects. Enables safe sharing across async contexts.
- **Consequences:** All data transfer objects use `@dataclass(frozen=True)`. Mutations require creating a new instance.
- **Status:** Accepted

## DEC-011
- **Date:** 2026-02-19
- **Decision:** Signal generator registry with fallback chains (primary → fallback → neutral fail-safe).
- **Context:** SPEC.md §5.2 mandates swappable signal generators with per-instrument routing. Fallback chain ensures the system always produces a signal, even on generator failure.
- **Consequences:** `GeneratorRegistry` is mutable at boot, frozen at runtime. `SignalRouter` attempts primary generator, falls back to secondary on `RecoverableSignalError`, emits `neutral_fail_safe_signal` if all fail. Fallback events are logged.
- **Status:** Accepted

## DEC-012
- **Date:** 2026-03-02
- **Decision:** Defer Dockerfile implementation to Stage 7 (Paper Trading).
- **Context:** The Dockerfile is currently a stub placeholder (`# Scaffold Dockerfile placeholder`). Containerized deployment is not needed until paper trading (Stage 7) or production deployment (Stage 8). Building a Dockerfile now would require premature decisions about runtime dependencies, environment variables, and service orchestration that will change as the system matures through Stages 2–6.
- **Consequences:** Dockerfile stub retained per DEC-009 (scaffold pattern). No Docker-based deployment until Stage 7. Development uses local Python environment and `docker compose` for TimescaleDB only.
- **Status:** Accepted

## DEC-013
- **Date:** 2026-03-03
- **Decision:** FeatureProvider uses synchronous batch signature instead of SPEC §3.6 async single-timestamp signature.
- **Context:** SPEC §3.6 defines `async get_features(instrument, timestamp, lookback) -> dict[str, float]`. The implemented signature is `get_features(*, instrument, interval, candles, lookback) -> dict[datetime, dict[str, float]]` (sync, batch). Batch computation is more efficient for indicators that require lookback windows (e.g., RSI-14 needs 14 prior candles). Async is unnecessary in the current single-process architecture. The batch interface also enables vectorized NumPy/TA-Lib computation across the full candle sequence. Red Team finding SR-H5.
- **Consequences:** All FeatureProvider implementations use sync batch signature. Callers pass `Sequence[CandleRecord]` and receive per-timestamp feature dicts. If async is needed in a future multi-service architecture, the protocol can be updated with an async wrapper.
- **Status:** Accepted

## DEC-014
- **Date:** 2026-03-04
- **Decision:** Event labeling uses high-watermark method (high/low price within horizon) instead of SPEC §4.6 close-to-close forward return.
- **Context:** SPEC §4.6 defines events as `(close[T+N] - close[T]) / close[T] >= X/100` (close-to-close). The implementation checks whether `future.high` (UP) or `future.low` (DOWN) breaches the threshold at any point within the horizon window. The labeling method is strategy-dependent: high-watermark is more appropriate for active trading strategies (detecting intrabar opportunities), while close-to-close is better for hold-to-horizon strategies. Stage 2 Red Team finding RC-1.
- **Consequences:** Event labels reflect whether the price level was reached at any point in the forward window, not just at the horizon endpoint. This produces more frequent positive labels than close-to-close. The labeling method should be made configurable per strategy in a future stage (e.g., `"event_method": "watermark" | "close_to_close"` in strategy config).
- **Status:** Accepted
