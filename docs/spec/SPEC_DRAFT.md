# Newton Trading System — FINAL SPECIFICATION

**Document:** `docs/spec/SPEC_DRAFT.md`
**Date:** 2026-02-17
**Status:** Implementation-ready. Zero-code baseline.
**Inputs:** `SPEC.v3.md`, `SPEC_NOTES.md`, `SPEC_DECISIONS_LOCK.md`, `SPEC_REVISIONS.md`
**Canonical Location:** `projects/newton/spec/`

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Scope and Non-Goals](#2-scope-and-non-goals)
3. [Architecture](#3-architecture)
4. [Data Specification and Extensible Feature Model](#4-data-specification-and-extensible-feature-model)
5. [Strategy Engine and Regime Subsystem](#5-strategy-engine-and-regime-subsystem)
6. [Execution Model (Spot v1) and Reconciliation](#6-execution-model-spot-v1-and-reconciliation)
7. [Risk Model](#7-risk-model)
8. [Backtesting Framework and Realism Assumptions](#8-backtesting-framework-and-realism-assumptions)
9. [Performance Metrics](#9-performance-metrics)
10. [Client UI Functional Specification](#10-client-ui-functional-specification)
11. [Monitoring, Operations, and Security](#11-monitoring-operations-and-security)
12. [Documentation Strategy](#12-documentation-strategy)
13. [Governance](#13-governance)
14. [Branching and Stage Gates](#14-branching-and-stage-gates)
15. [Stage-by-Stage Implementation Plan](#15-stage-by-stage-implementation-plan)
16. [Open Questions](#16-open-questions)
17. [Decision Log](#17-decision-log)
18. [Alternatives Considered](#18-alternatives-considered)
19. [Appendices](#19-appendices)

---

## 1. Executive Summary

### 1.1 System Objective

Develop a fully automated multi-instrument trading system that generates sustainable income using a hybrid machine-learning approach to identify and execute trades across forex and cryptocurrency markets.

### 1.2 Project Status

**This project is at a pre-development / zero-code baseline.** No code has been written. No phases have been implemented. All specification content describes the target system to be built from scratch.

### 1.3 Target Markets (v1)

| Instrument | Broker / Exchange | Market Type | Contract Type | Trading Hours |
|---|---|---|---|---|
| EUR/USD | Oanda (v20 REST API) | Forex (Spot) | Spot FX | 24/5 (Sun 17:00 – Fri 17:00 ET) |
| BTC/USD | Binance (REST + WebSocket API) | Cryptocurrency (Spot) | Spot (BTCUSDT pair) | 24/7 |

**Design Intent:** Including two fundamentally different instruments forces a true multi-instrument, multi-market architecture from day one. The system must account for differing market microstructure, volatility profiles, liquidity characteristics, and trading hours.

**v1 is spot-only.** No futures, no leverage, no funding rates. The architecture is designed to support derivatives in future versions without major refactoring, but v1 scope is exclusively spot market execution. BTC/USD uses the Binance spot BTCUSDT pair with no leverage.

### 1.4 Timeframes

- **Signal generation:** 1h candles (primary). Optional 4h confirmation deferred to v1.1.
- **Execution horizon:** Intra-day to swing (holding periods of hours to days, max 48 hours).
- BTC/USD may require instrument-specific holding period tuning due to higher volatility.

### 1.5 Strategy Class

Hybrid model: event-based Bayesian analysis for interpretability and risk framework, combined with a supervised ML model (initially XGBoost; CNN-LSTM evaluated in Stage 3) for pattern recognition. Each instrument uses a **strategy configuration tailored to its behavior** while sharing common infrastructure.

### 1.6 Success Criteria (Measurable)

| Criterion | Target | Measurement Period | Gate Type | Per-Instrument |
|---|---|---|---|---|
| Profit Factor | > 1.3 | 3-month paper trade | Go/No-Go for live | Yes |
| Sharpe Ratio (annualized) | > 0.8 | 3-month paper trade | Go/No-Go for live | Yes |
| Max Drawdown | < 15% (default; configurable per strategy) | 3-month paper trade | Hard stop if breached | Yes |
| Win Rate | > 45% | 3-month paper trade | Informational | Yes |
| Backtest-to-Paper Deviation | < 20% on Sharpe | 3-month paper trade | Investigate if breached | Yes |
| Live Max Drawdown | < 20% (default; configurable per strategy) | Ongoing | Kill switch | Per-instrument + portfolio |
| System Availability | > 99.5% | Monthly | Investigate if breached | System-wide |
| Signal Calibration | Predicted vs. observed ±5 pp per decile | Per walk-forward fold | Retrain if breached | Yes |

**Assumption [A1]:** These targets are achievable for medium-frequency strategies on these instruments. If paper trading shows Sharpe < 0.5 on either instrument, the strategy hypothesis for that instrument should be revisited, not tuned.

**Note:** BTC/USD success criteria may require adjustment (e.g., wider drawdown tolerance) given higher baseline volatility. This will be evaluated during Stage 5 backtesting and explicitly decided before paper trading begins. Any adjustments must be configured via per-strategy overrides (see §7.4).

---

## 2. Scope and Non-Goals

### 2.1 In Scope (v1)

- Data ingestion from **Oanda** (EUR/USD spot) and **Binance** (BTC/USD spot, BTCUSDT pair) across 1m, 5m, 1h, 4h, 1d timeframes.
- Historical data backfill (minimum 3 years: 2023-01-01 to present) and validation for both instruments.
- Extensible feature/indicator computation: initial set includes RSI(14), MACD(12,26,9), Bollinger Bands(20,2.0), OBV, ATR(14). New indicators can be added via the feature provider interface without schema changes or disruptive refactoring.
- Bayesian inference engine for generating trade signals based on tokenized indicator events.
- Supervised ML model (XGBoost as default; CNN-LSTM as optional alternative) to provide a complementary probability score.
- Stacking meta-learner to combine Bayesian and ML signals into a calibrated probability.
- Backtesting engine with walk-forward validation and purged K-fold cross-validation.
- Paper trading module via Oanda practice account (EUR/USD) and Binance testnet (BTC/USD spot).
- Risk management: broker-side stops, Kelly-based position sizing, drawdown circuit breakers — all configurable per strategy with global defaults.
- Performance metrics: configurable per strategy with global defaults.
- Operational monitoring: structured logging, Prometheus metrics, Telegram alerts.
- Position reconciliation loop (per-broker).
- Regime detection subsystem with deterministic classification and strategy-aware behavior.
- **Instrument-specific strategy configurations** sharing common infrastructure.
- Client application (web UI) with strict separation from server, progressing each stage.
- Developer documentation, user/operator documentation, and in-app help.

### 2.2 Explicitly Out of Scope (v1)

- HFT (sub-second).
- Futures, leverage, margin trading, funding rates — v1 is spot-only. Architecture supports future derivatives without major refactor.
- Instruments beyond EUR/USD and BTC/USD (v2+).
- Non-technical data sources (sentiment, news, order book) — **architecture supports future addition via FeatureProvider interface without major refactor** (see §3.6).
- Short selling (v1 is long-only; SELL signal closes existing longs).
- Multi-timeframe confirmation logic (deferred to v1.1).
- Online/incremental learning (v2).
- Dynamic strategy generation beyond static configs (v1 uses static configs; see §5.8 for roadmap).

---

## 3. Architecture

### 3.1 High-Level Architecture

```
+==============================================================+
|                    Newton Server (Single Process)              |
|  +------------------+  +-------------------+  +-------------+ |
|  |  Data Module     |  | Analysis Module   |  | Trading     | |
|  |  data/           |  | analysis/         |  | Module      | |
|  |  - fetcher_oanda |->| - event_detector  |->| trading/    | |
|  |  - fetcher_binance| | - tokenizer       |  | - signal    | |
|  |  - indicators    |  | - bayesian        |  | - risk      | |
|  |  - pipeline      |  | - ml_model        |  | - executor  | |
|  |  - feature_store |  | - meta_learner    |  |   _oanda    | |
|  |  - verifier      |  | - regime          |  |   _binance  | |
|  |  - db            |  | - feature_provider|  | - reconciler| |
|  +--------|---------+  +---------|---------+  +------|------+ |
|           |                      |                    |        |
+===========|======================|====================|========+
            |                      |                    |
   +--------v---------+    +------v-------+    +-------v--------+
   |   TimescaleDB    |    |   Model      |    |   Broker APIs  |
   |   (PostgreSQL)   |    |   Artifacts  |    |   - Oanda v20  |
   +------------------+    |   (disk)     |    |   - Binance    |
                           +--------------+    |     (Spot)     |
                                               +----------------+

   +------------------+
   | Client (Web UI)  |--- REST/WS API only (strict boundary)
   +------------------+
```

**Key architectural principles:**

1. **Monolith server** — single developer, manageable complexity. Modules separated by directory and interface; extraction to services deferred to when needed.
2. **Multi-broker abstraction** — `BrokerAdapter` interface allows Oanda and Binance to be treated uniformly by upper layers.
3. **Strict client/server separation** — UI communicates only via versioned REST/WebSocket APIs. No shared state, no direct DB access from client.
4. **Instrument-aware pipeline** — every stage (data, analysis, trading) is parameterized by instrument with per-instrument configuration.
5. **Spot-first, derivatives-ready** — v1 uses spot execution only. The broker adapter interface and order model are designed so that adding futures/margin support requires implementing new adapter methods, not restructuring the core.

### 3.2 Client/Server Boundary

**Rules:**

1. The server exposes a **versioned REST API** (prefix: `/api/v1/`) and optional WebSocket channels as the sole interface for all clients.
2. The client **never** accesses the database, file system, or model artifacts directly.
3. API contracts (OpenAPI 3.1 schema) are the **source of truth** for client/server interaction.
4. The client **validates server behavior**: all API responses include checksums, timestamps, and status codes that the client can verify and surface discrepancies.
5. The UI is **replaceable**: any conforming client can substitute the default web UI without server modification.

**API Versioning Strategy:**

- URL-path versioning: `/api/v1/`, `/api/v2/`, etc.
- Breaking changes require a version bump. Non-breaking additions (new optional fields) are allowed within a version.
- Deprecated endpoints are marked with `Sunset` header and removed no sooner than 2 minor releases later.
- OpenAPI schema is auto-generated from server code (FastAPI) and published as a build artifact.

**Verification Observability:**

- Client-side health panel shows: API connectivity, response latency (p50/p95), schema validation errors, data freshness.
- Any API response failing schema validation is flagged in the UI with details.

### 3.3 Broker Adapter Interface

```python
class BrokerAdapter(Protocol):
    """Abstract broker interface. Implemented per broker."""

    async def get_candles(self, instrument: str, interval: str,
                          start: datetime, end: datetime) -> list[Candle]: ...
    async def get_account(self) -> AccountInfo: ...
    async def get_positions(self) -> list[Position]: ...
    async def place_market_order(self, instrument: str, units: float,
                                  stop_loss: float,
                                  client_order_id: str) -> OrderResult: ...
    async def modify_stop_loss(self, trade_id: str,
                                new_stop: float) -> OrderResult: ...
    async def close_position(self, trade_id: str) -> OrderResult: ...
    async def get_order_status(self, client_order_id: str) -> OrderStatus: ...
```

**Implementations:** `OandaAdapter` (spot forex), `BinanceSpotAdapter` (spot crypto).

**Rationale:** Uniform interface allows the trading module to be broker-agnostic. Instrument configuration maps each instrument to its adapter. New brokers or market types (e.g., futures) can be added by implementing the interface.

### 3.4 Instrument Configuration

Each instrument has an independent configuration that specifies behavior across all system layers:

```json
// config/instruments/EUR_USD.json
{
  "instrument_id": "EUR_USD",
  "broker": "oanda",
  "display_name": "EUR/USD",
  "asset_class": "forex",
  "market_type": "spot",
  "base_currency": "EUR",
  "quote_currency": "USD",
  "pip_size": 0.0001,
  "min_trade_size": 1,
  "max_trade_size": 1000000,
  "trading_hours": "24/5",
  "intervals": ["1m", "5m", "1h", "4h", "1d"],
  "signal_interval": "1h",
  "typical_spread_pips": 1.5,
  "default_slippage_pips": 1.0,
  "strategy_config": "config/strategies/EUR_USD_strategy.json",
  "risk_overrides": {}
}
```

```json
// config/instruments/BTC_USD.json
{
  "instrument_id": "BTC_USD",
  "broker": "binance",
  "display_name": "BTC/USDT",
  "asset_class": "crypto",
  "market_type": "spot",
  "base_currency": "BTC",
  "quote_currency": "USDT",
  "symbol": "BTCUSDT",
  "pip_size": 0.01,
  "min_trade_size": 0.00001,
  "max_trade_size": 100,
  "trading_hours": "24/7",
  "intervals": ["1m", "5m", "1h", "4h", "1d"],
  "signal_interval": "1h",
  "typical_spread_pct": 0.05,
  "default_slippage_pct": 0.02,
  "strategy_config": "config/strategies/BTC_USD_strategy.json",
  "risk_overrides": {
    "hard_stop_pct": 0.03,
    "high_volatility_stop_pct": 0.05,
    "max_drawdown_pct": 0.25
  }
}
```

**Key Design Points:**

- Strategy configurations are **instrument-specific** (different event definitions, token sets, thresholds, risk parameters).
- Common infrastructure (pipeline orchestration, Bayesian engine logic, ML training framework, risk framework) is **shared**.
- Risk overrides per instrument allow tuning for different volatility profiles.
- `market_type: "spot"` is explicit for v1. Future instruments may use `"futures"` or `"margin"`.

### 3.5 Failure Domains and Recovery

| Failure | Detection | Response | Recovery |
|---|---|---|---|
| Oanda REST API down | HTTP error / timeout | Retry 3× with exponential backoff (2s, 4s, 8s). Halt EUR/USD signals. Alert. | Resume on next successful fetch. Reconcile positions. |
| Binance REST API down | HTTP error / timeout | Retry 3× with exponential backoff. Halt BTC/USD signals. Alert. | Resume on next successful fetch. Reconcile positions. |
| Oanda WebSocket disconnect | Heartbeat timeout (30s) | Reconnect with backoff. Fall back to REST polling (10s). | Auto-reconnect; alert if > 5 min. |
| Binance WebSocket disconnect | Heartbeat timeout (30s) | Reconnect with backoff. Fall back to REST polling (10s). | Auto-reconnect; alert if > 5 min. |
| Database unreachable | Connection error | Halt all operations. Alert. | Auto-retry every 30s. Resume on reconnect. |
| Application crash | Docker restart policy / systemd | Broker-side stops protect open positions. | On restart: reconcile all positions per broker, resume from latest complete candle. |
| Model file missing/corrupt | Hash check on load | Fall back to Bayesian-only mode per instrument. Alert. | Retrain or restore from backup. |
| Single broker down | Per-broker health check | Continue trading on healthy broker. Halt only the affected instrument. | Resume when broker recovers. |

### 3.6 Extension Points for Future Data Sources

The architecture allows non-technical data (sentiment, news, order book / market microstructure signals) to be added in future versions **without major refactor**.

**Feature Provider Interface:**

```python
class FeatureProvider(Protocol):
    """Interface for pluggable feature sources."""

    @property
    def provider_name(self) -> str: ...

    @property
    def feature_namespace(self) -> str: ...

    async def get_features(self, instrument: str, timestamp: datetime,
                           lookback: int) -> dict[str, float]: ...

    def get_feature_metadata(self) -> list[FeatureMetadata]: ...
```

**Built-in providers (v1):**
- `TechnicalIndicatorProvider` — RSI, MACD, BB, OBV, ATR, and any additional technical indicators added via the extension mechanism.

**Future providers (interface exists, not implemented in v1):**
- `SentimentProvider` — social media / news sentiment scores.
- `OrderBookProvider` — depth imbalance, bid-ask pressure.
- `NewsProvider` — event flags, surprise metrics.

**Adding a new indicator or feature provider:**

1. Implement the `FeatureProvider` protocol (or for technical indicators, extend the `TechnicalIndicatorProvider`).
2. Register the provider in the configuration (`config/feature_providers.json`).
3. The provider's features automatically flow into the feature store with its declared namespace.
4. The tokenizer and ML feature engineering stages query all registered providers.
5. No changes to core pipeline code, database schema, or existing providers are required.

**Testing requirements for new indicators:**
- Unit tests verifying calculation accuracy against a reference implementation.
- Integration test confirming features are stored and retrievable from the feature store.
- Backtest run demonstrating no regression to existing strategy performance.

### 3.7 Key Assumptions

- **[A2]:** Hybrid Bayesian + ML model is the desired approach.
- **[A3]:** Multi-instrument from v1: EUR/USD (Oanda spot) + BTC/USD (Binance spot).
- **[A4]:** No code has been written. This is a zero-code baseline.
- **[A5]:** Python 3.11+ is the implementation language.
- **[A6]:** RTX 5060ti 16GB available on host for GPU-accelerated training.
- **[A7]:** Developer is solo; system must be maintainable by one person.
- **[A8]:** Each instrument may exhibit different market microstructure requiring per-instrument strategy tuning.
- **[A9]:** v1 is spot-only. No futures, leverage, or margin trading.

### 3.8 Contradictions Found and Resolved

| # | Contradiction | Resolution |
|---|---|---|
| 1 | Daily loss limit: SPEC.md says 3%, notes say 2% | Use 2% (more conservative, appropriate for unproven system) |
| 2 | Order type: notes suggest limit, spec says market | Market orders for v1 (simpler, guaranteed fill). Track savings for v2. |
| 3 | Redis: notes mention it; spec omits | Defer to v1.1. Current throughput doesn't justify added infra. |
| 4 | Binance: spec referenced futures | v1 uses Binance spot only (DL-002). No futures dependency. |
| 5 | Indicator schema: JSONB vs. relational | Feature store model (long-format) replaces both approaches. |
| 6 | Trailing stop: spec vs. notes conflict | Trailing stop activates at +1%, breakeven at +2% (notes version, more conservative). |
| 7 | Phase 1 status: earlier specs assumed implemented | Corrected to zero-code baseline. |

---

## 4. Data Specification and Extensible Feature Model

### 4.1 Data Sources

| Source | Instrument | API | Candle Confirmation | Auth |
|---|---|---|---|---|
| Oanda v20 | EUR/USD | REST + WebSocket | `complete: true` flag | API key (env var) |
| Binance | BTC/USDT (spot) | REST + WebSocket | Kline close event | API key + secret (env vars) |

**Fetch Schedule:** Poll every 10 seconds after expected candle close; accept only confirmed/complete candles.

**Binance-Specific Considerations (Spot):**

- BTC/USDT trades 24/7; no market close gaps.
- Volume denomination differs (base vs. quote currency). Normalize to quote currency (USDT).
- Binance rate limits: implement rate limiter (1200 requests/min weight). Track weight per request.
- Spot API does not require futures-specific configuration (no funding rates, no contract type selection).
- Use Binance spot kline/candlestick endpoints for historical and real-time data.

### 4.2 Database Schema (TimescaleDB)

```sql
-- OHLCV data (hypertable partitioned by time)
CREATE TABLE ohlcv (
    time        TIMESTAMPTZ NOT NULL,
    instrument  TEXT NOT NULL,         -- EUR_USD, BTC_USD, etc.
    interval    TEXT NOT NULL,
    open        DOUBLE PRECISION NOT NULL,
    high        DOUBLE PRECISION NOT NULL,
    low         DOUBLE PRECISION NOT NULL,
    close       DOUBLE PRECISION NOT NULL,
    volume      DOUBLE PRECISION NOT NULL,
    spread_avg  DOUBLE PRECISION,
    verified    BOOLEAN DEFAULT FALSE,
    source      TEXT NOT NULL,         -- oanda, binance
    PRIMARY KEY (time, instrument, interval)
);
SELECT create_hypertable('ohlcv', 'time');

-- Feature store (long-format, extensible)
CREATE TABLE features (
    time        TIMESTAMPTZ NOT NULL,
    instrument  TEXT NOT NULL,
    interval    TEXT NOT NULL,
    namespace   TEXT NOT NULL,         -- 'technical', 'sentiment', 'orderbook', etc.
    feature_key TEXT NOT NULL,         -- 'rsi:period=14', 'macd:fast=12,slow=26,signal=9:line', etc.
    value       DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (time, instrument, interval, namespace, feature_key)
);
SELECT create_hypertable('features', 'time');
CREATE INDEX idx_features_lookup ON features (instrument, interval, namespace, feature_key, time DESC);

-- Feature metadata (describes available features)
CREATE TABLE feature_metadata (
    namespace       TEXT NOT NULL,
    feature_key     TEXT NOT NULL,
    display_name    TEXT NOT NULL,
    description     TEXT,
    unit            TEXT,
    params          JSONB,            -- {"period": 14} etc.
    provider        TEXT NOT NULL,    -- provider_name from FeatureProvider
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (namespace, feature_key)
);

-- Events (detected target events)
CREATE TABLE events (
    id              BIGSERIAL,
    time            TIMESTAMPTZ NOT NULL,
    instrument      TEXT NOT NULL,
    interval        TEXT NOT NULL,
    event_name      TEXT NOT NULL,
    event_value     BOOLEAN NOT NULL,
    lookforward_periods INTEGER NOT NULL,
    price_at_signal DOUBLE PRECISION NOT NULL,
    price_at_resolution DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (id)
);
CREATE INDEX idx_events_lookup ON events (instrument, interval, event_name, time);

-- Tokens (active indicator state tokens per candle)
CREATE TABLE tokens (
    time        TIMESTAMPTZ NOT NULL,
    instrument  TEXT NOT NULL,
    interval    TEXT NOT NULL,
    tokens      TEXT[] NOT NULL,
    PRIMARY KEY (time, instrument, interval)
);

-- Trades (system trade log)
CREATE TABLE trades (
    id                  BIGSERIAL PRIMARY KEY,
    client_order_id     TEXT UNIQUE NOT NULL,
    broker_order_id     TEXT,
    instrument          TEXT NOT NULL,
    broker              TEXT NOT NULL,         -- oanda, binance
    direction           TEXT NOT NULL CHECK (direction IN ('BUY', 'SELL')),
    signal_score        DOUBLE PRECISION NOT NULL,
    signal_type         TEXT NOT NULL,
    regime_label        TEXT,                  -- active regime at signal time
    entry_time          TIMESTAMPTZ,
    entry_price         DOUBLE PRECISION,
    exit_time           TIMESTAMPTZ,
    exit_price          DOUBLE PRECISION,
    quantity            DOUBLE PRECISION NOT NULL,
    stop_loss_price     DOUBLE PRECISION,
    status              TEXT NOT NULL CHECK (status IN ('PENDING', 'OPEN', 'CLOSED', 'CANCELLED', 'REJECTED')),
    pnl                 DOUBLE PRECISION,
    commission          DOUBLE PRECISION,
    slippage            DOUBLE PRECISION,
    exit_reason         TEXT,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

-- Reconciliation log
CREATE TABLE reconciliation_log (
    id          BIGSERIAL PRIMARY KEY,
    checked_at  TIMESTAMPTZ DEFAULT NOW(),
    broker      TEXT NOT NULL,
    status      TEXT NOT NULL CHECK (status IN ('MATCH', 'SYSTEM_EXTRA', 'BROKER_EXTRA')),
    details     JSONB,
    resolved    BOOLEAN DEFAULT FALSE
);

-- Regime log (tracks regime state over time)
CREATE TABLE regime_log (
    id              BIGSERIAL PRIMARY KEY,
    time            TIMESTAMPTZ NOT NULL,
    instrument      TEXT NOT NULL,
    regime_label    TEXT NOT NULL,
    confidence      DOUBLE PRECISION,
    vol_30d         DOUBLE PRECISION,
    adx_14          DOUBLE PRECISION,
    trigger         TEXT NOT NULL,       -- 'automatic', 'manual_override'
    details         JSONB
);
CREATE INDEX idx_regime_lookup ON regime_log (instrument, time DESC);

-- Strategy configuration versions
CREATE TABLE strategy_versions (
    id              BIGSERIAL PRIMARY KEY,
    instrument      TEXT NOT NULL,
    version         INTEGER NOT NULL,
    config          JSONB NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    created_by      TEXT NOT NULL,       -- 'user', 'system', 'optimizer'
    approved        BOOLEAN DEFAULT FALSE,
    approved_at     TIMESTAMPTZ,
    approval_evidence JSONB,             -- backtest artifact references
    notes           TEXT,
    UNIQUE (instrument, version)
);

-- Spec deviation log
CREATE TABLE spec_deviations (
    id              BIGSERIAL PRIMARY KEY,
    deviation_id    TEXT UNIQUE NOT NULL,   -- DEV-001, DEV-002, etc.
    spec_section    TEXT NOT NULL,
    description     TEXT NOT NULL,
    justification   TEXT NOT NULL,
    impact          TEXT NOT NULL,
    risk_assessment TEXT NOT NULL,
    status          TEXT NOT NULL CHECK (status IN ('PROPOSED', 'APPROVED', 'REJECTED', 'IMPLEMENTED')),
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    reviewed_at     TIMESTAMPTZ,
    reviewer        TEXT
);

-- Configuration change audit log
CREATE TABLE config_changes (
    id              BIGSERIAL PRIMARY KEY,
    changed_at      TIMESTAMPTZ DEFAULT NOW(),
    changed_by      TEXT NOT NULL,
    section         TEXT NOT NULL,         -- 'risk', 'strategy', 'instrument', etc.
    instrument      TEXT,                  -- NULL for global changes
    old_value       JSONB,
    new_value       JSONB NOT NULL,
    reason          TEXT
);
```

### 4.3 Indicator Data Model — Feature Store Approach

**Problem:** Column naming like `rsi_14` is rigid. Adding new indicators requires schema migration. Querying across arbitrary indicator sets requires knowing column names at code-time.

**Selected approach: Long-format feature store with performance mitigations.**

**Rationale:**

- **Scalability:** Adding new indicators (technical or otherwise) requires zero schema changes — just insert rows with a new feature key (and register in feature_metadata).
- **Self-describing:** The `feature_metadata` table provides discovery and documentation.
- **Namespace isolation:** `technical`, `sentiment`, `orderbook` namespaces prevent collisions and enable selective querying.
- **Multi-instrument native:** Same schema serves all instruments without instrument-specific columns.
- **Extensibility mandate (R-03):** New indicators can be added by implementing the `FeatureProvider` interface and registering — no disruptive refactor.

**Feature Key Format:**
```
{indicator}:{param1}={value1},{param2}={value2}:{component}
```

Examples:
- `rsi:period=14` → RSI with period 14
- `macd:fast=12,slow=26,signal=9:line` → MACD line value
- `macd:fast=12,slow=26,signal=9:signal` → MACD signal value
- `macd:fast=12,slow=26,signal=9:histogram` → MACD histogram
- `bb:period=20,std=2.0:upper` → Bollinger upper band
- `bb:period=20,std=2.0:middle` → Bollinger middle band
- `bb:period=20,std=2.0:lower` → Bollinger lower band
- `obv:` → On-Balance Volume (no params)
- `atr:period=14` → ATR with period 14

**Process for adding a new indicator (e.g., Stochastic RSI):**

1. Implement calculation in `TechnicalIndicatorProvider` (or a new provider class implementing `FeatureProvider`).
2. Register the feature key(s) in `feature_metadata` (e.g., `stochrsi:period=14,smooth_k=3,smooth_d=3:k`).
3. Add unit tests comparing output against a reference library (TA-Lib or equivalent).
4. Run indicator computation pipeline — new features are automatically stored in the feature store.
5. Optionally update token classifications and strategy configs to use the new indicator.
6. Run backtest to confirm no regression to existing strategies.

**Performance Mitigations:**

1. **Composite index** on `(instrument, interval, namespace, feature_key, time DESC)` for point lookups.
2. **Materialized views** for hot query patterns (e.g., latest values for all core indicators for a given instrument/interval).
3. **Batch insert** using `COPY` or `execute_values` for bulk feature writes.
4. **TimescaleDB compression** on older partitions (> 30 days) for storage efficiency.
5. **Benchmark requirement:** Before finalizing Stage 1, benchmark reads of 2 years × 5 indicators × 1h interval. Target: < 500ms for a full feature vector retrieval for a 60-period lookback.

**Query Example — Get latest RSI for EUR/USD 1h:**
```sql
SELECT value FROM features
WHERE instrument = 'EUR_USD'
  AND interval = '1h'
  AND namespace = 'technical'
  AND feature_key = 'rsi:period=14'
ORDER BY time DESC LIMIT 1;
```

**Query Example — Get all features for a candle:**
```sql
SELECT feature_key, value FROM features
WHERE instrument = 'EUR_USD'
  AND interval = '1h'
  AND namespace = 'technical'
  AND time = '2025-01-15T14:00:00Z';
```

### 4.4 Data Quality Checks

| Check | Frequency | Action on Failure |
|---|---|---|
| Gap detection (missing candles) | Every pipeline run, per instrument | Auto-backfill; flag `verified = false` until filled |
| Duplicate check | Every pipeline run | Deduplicate (keep latest) |
| OHLC logic (high ≥ open, close, low; low ≤ open, close, high) | Every pipeline run | Flag row as suspect; exclude from signal generation |
| Stale data (no new candle within 2× expected interval) | Continuous (watchdog), per instrument | Alert; halt new signals for that instrument |
| Outlier detection (candle range > 10× ATR(14)) | Every pipeline run | Flag; do not auto-exclude but alert for manual review |
| Cross-source sanity (if secondary feed available) | Per candle | Alert if primary and secondary prices diverge significantly |

### 4.5 Timezone Policy

- All timestamps are stored and processed in UTC.
- No timezone-naive `datetime` objects anywhere in the codebase. Enforced via linting rule.

### 4.6 Event Definition (Precise)

An event `{INSTRUMENT}_UP_X_PCT_N_PERIODS` is defined as:

> At candle T (signal candle), the event is TRUE if:
> `(close[T + N] - close[T]) / close[T] >= X / 100`
>
> where close[T + N] is the closing price of the candle exactly N periods after T.

This is a **close-to-close forward return** measurement. NOT a high-watermark measurement.

**Rationale:** Close-to-close is unambiguous, reproducible, and conservative.

**Test Hook:** Unit test with a known price series.

**v1 Event Catalog (DL-003):**

The v1 event catalog is constrained per instrument. Each event has explicit definitions and acceptance criteria:

**EUR/USD Events:**

| Name | Direction | Threshold % | Lookforward Periods | Interval | Min Occurrences |
|---|---|---|---|---|---|
| `EURUSD_UP_1PCT_24H` | UP | 1.0 | 24 | 1h | 100 |
| `EURUSD_DOWN_1PCT_24H` | DOWN | 1.0 | 24 | 1h | 100 |

**BTC/USD Events:**

| Name | Direction | Threshold % | Lookforward Periods | Interval | Min Occurrences |
|---|---|---|---|---|---|
| `BTCUSD_UP_3PCT_24H` | UP | 3.0 | 24 | 1h | 100 |
| `BTCUSD_DOWN_3PCT_24H` | DOWN | 3.0 | 24 | 1h | 100 |

**Acceptance criteria for event detection:**
- Given a known price series, event labels must match hand-calculated expectations with zero discrepancy.
- Min occurrences threshold must be validated against the 3-year historical dataset. If an event has fewer occurrences than `min_occurrences`, alert and log — the event definition may need threshold adjustment.
- Events are stored in the `events` table with all required fields.

### 4.7 Data Retention and Compression Policy (DL-009)

| Table | Retention | Compression | Notes |
|---|---|---|---|
| `ohlcv` | Indefinite (all historical data) | TimescaleDB compression after 90 days | Core dataset, never purge |
| `features` | Indefinite | TimescaleDB compression after 30 days | Recomputable but expensive |
| `events` | Indefinite | TimescaleDB compression after 90 days | Required for retraining |
| `tokens` | Indefinite | TimescaleDB compression after 90 days | Required for retraining |
| `trades` | Indefinite | None (small table) | Audit record, never purge |
| `reconciliation_log` | 1 year | None | Compress/archive older than 1 year |
| `regime_log` | Indefinite | None (small table) | Analytics record |
| `strategy_versions` | Indefinite | None | Audit trail |
| `config_changes` | Indefinite | None | Audit trail |
| `spec_deviations` | Indefinite | None | Governance record |

**Backup Policy:**
- **Frequency:** Daily automated backup (pg_dump) to local storage + weekly offsite copy.
- **Retention:** Keep daily backups for 30 days; weekly backups for 1 year.
- **Restore test:** Monthly restore-test to a temporary database, verifying row counts and data integrity checksums.

---

## 5. Strategy Engine and Regime Subsystem

### 5.1 Per-Instrument Strategy Configuration

Each instrument has a strategy configuration file that defines its behavior:

```json
// config/strategies/EUR_USD_strategy.json
{
  "instrument": "EUR_USD",
  "events": ["EURUSD_UP_1PCT_24H", "EURUSD_DOWN_1PCT_24H"],
  "token_config": "config/classifications/EUR_USD_classifications.json",
  "token_selection": {"method": "mutual_information", "top_n": 20, "jaccard_threshold": 0.85},
  "bayesian": {"calibration": "isotonic", "posterior_cap": 0.90, "laplace_alpha": 1},
  "ml_model": {"type": "xgboost", "lookback_periods": 24, "hyperparams": "auto"},
  "meta_learner": {"type": "logistic_regression", "min_samples": 100},
  "thresholds": {"strong_buy": 0.65, "buy": 0.55, "sell": 0.40},
  "risk_overrides": {},
  "performance_overrides": {}
}
```

```json
// config/strategies/BTC_USD_strategy.json
{
  "instrument": "BTC_USD",
  "events": ["BTCUSD_UP_3PCT_24H", "BTCUSD_DOWN_3PCT_24H"],
  "token_config": "config/classifications/BTC_USD_classifications.json",
  "token_selection": {"method": "mutual_information", "top_n": 20, "jaccard_threshold": 0.85},
  "bayesian": {"calibration": "isotonic", "posterior_cap": 0.90, "laplace_alpha": 1},
  "ml_model": {"type": "xgboost", "lookback_periods": 24, "hyperparams": "auto"},
  "meta_learner": {"type": "logistic_regression", "min_samples": 100},
  "thresholds": {"strong_buy": 0.60, "buy": 0.50, "sell": 0.45},
  "risk_overrides": {"hard_stop_pct": 0.03},
  "performance_overrides": {"max_drawdown_pct": 0.25}
}
```

**Shared infrastructure:** Pipeline orchestration, Bayesian engine logic, ML training framework, meta-learner framework, risk framework, reporting.

**Instrument-specific:** Event definitions, token classifications, threshold values, risk parameter overrides, performance metric overrides, model artifacts.

### 5.2 Tokenization

**Format:** `{INSTRUMENT}_{PREFIX}_{PARAM}_{DATAPOINT}_{TYPE}_{VALUE}`

Examples:
- `EURUSD_RSI14_CL_BLW_30` — EUR/USD RSI(14) on Close is Below 30
- `BTCUSD_MACD12269_CL_XABV_0` — BTC/USD MACD(12,26,9) crosses Above 0

Token vocabularies are defined per instrument in `config/classifications/{INSTRUMENT}_classifications.json`.

**Acceptance Test:** Given known indicator values per instrument, verify exact token output.

### 5.3 Token Selection

1. For each event type (per instrument), calculate mutual information `I(Token; Event)` for all tokens.
2. Rank tokens by mutual information.
3. Filter redundant tokens: if Jaccard similarity between two tokens' occurrence vectors > 0.85, keep only the higher-MI token.
4. Select top N tokens (configurable per instrument, default N=20, max N=50).
5. Log the selected token set, their MI scores, and the correlation matrix.

**Acceptance Test:** On synthetic data with a known informative token and a known noise token, verify the informative token is selected and the noise token is not.

### 5.4 Bayesian Engine

**Method:** Naïve Bayes with calibration.

**Process:**

1. Calculate prior: `P(Event) = count(Event=TRUE) / count(all)`
2. Calculate likelihood: `P(Token_i | Event) = count(Token_i AND Event) / count(Event)` with Laplace smoothing (alpha=1, configurable per strategy).
3. Calculate posterior using log-odds form (numerically stable):
   ```
   log_odds = log(P(Event) / P(~Event))
   for each token_i in active_tokens:
       log_odds += log(P(Token_i | Event) / P(Token_i | ~Event))
   posterior = sigmoid(log_odds)
   ```
4. **Calibration:** Apply isotonic regression fitted on out-of-fold predictions.
5. **Cap:** Maximum posterior capped at 0.90 (configurable per instrument strategy).

**Known Limitation:** Naïve Bayes assumes token independence, which is violated. Calibration partially mitigates this. Future: full joint model (PyMC/MCMC).

**Inter-token Correlation Check:** At training time, compute pairwise phi coefficients. If |phi| > 0.7 between any pair, log warning. If > 3 pairs exceed threshold, alert and recommend reducing token set.

### 5.5 ML Model

**Default: XGBoost (v1).**

**Input Features:** Last N periods (configurable per instrument strategy, default 24) of: OHLCV returns (not raw prices), indicator features from feature store (all registered providers), token presence flags. Feature count depends on registered feature providers.

**Training:** Walk-forward: train on rolling 2-year window, validate on next 6 months. Hyperparameter search via Optuna. Early stopping on validation loss.

**Acceptance Criteria:** Out-of-sample AUC-ROC > 0.55 per instrument. If AUC < 0.55: disable ML component for that instrument; fall back to Bayesian-only mode.

**Optional: CNN-LSTM (Stage 3)** — evaluated if XGBoost fails to meet AUC threshold. Uses same feature set reshaped as temporal sequences. Requires GPU (RTX 5060ti). Regularization: dropout (0.2-0.5), early stopping, weight decay. Max parameter budget: 1M parameters.

### 5.6 Meta-Learner (Signal Combination)

**Method:** Logistic regression stacking.

**Inputs:** Bayesian posterior, ML probability, current regime confidence. Trained on out-of-fold predictions from walk-forward.

**Signal Interpretation:**

| Combined Probability | Signal | Action |
|---|---|---|
| > threshold_strong_buy (per strategy) | STRONG_BUY | Open long position (if no existing position for instrument) |
| > threshold_buy (per strategy) | BUY | Open long position (smaller size) |
| < threshold_sell (per strategy) | SELL | Close any open long position for instrument |
| else | NEUTRAL | No action |

Thresholds are per-instrument, defined in strategy configuration, and derived from walk-forward backtest.

### 5.7 Regime Detection Subsystem

#### 5.7.1 Purpose

Detect when market conditions shift, enabling strategy adaptation or protective halting. Regime detection operates independently per instrument.

#### 5.7.2 Regime Model

**Inputs (per instrument):**

1. **vol_30d:** Rolling 30-day annualized realized volatility (close-to-close returns, standard deviation × √252 for forex, √365 for crypto).
2. **ADX_14:** Rolling 14-day Average Directional Index (trend strength).
3. **Hurst exponent:** Deferred to v1.1.

**Regime Classification:**

| Regime Label | Condition | Typical Behavior |
|---|---|---|
| `LOW_VOL_TRENDING` | vol_30d < vol_median AND ADX_14 > 25 | Trend-following strategies favored |
| `LOW_VOL_RANGING` | vol_30d < vol_median AND ADX_14 ≤ 25 | Mean-reversion / range-bound strategies favored |
| `HIGH_VOL_TRENDING` | vol_30d ≥ vol_median AND ADX_14 > 25 | Aggressive trends, higher risk |
| `HIGH_VOL_RANGING` | vol_30d ≥ vol_median AND ADX_14 ≤ 25 | Choppy, high-risk — reduce position sizing |

**vol_median** is calculated over a 2-year rolling window, recalculated monthly (on the first day of each month at 00:00 UTC).

#### 5.7.3 Regime Confidence (DL-005) — Deterministic Formula

**Confidence** quantifies how clearly the current market state falls within a regime. It is computed as follows:

**Step 1 — Compute normalized distances from classification boundaries:**

```
d_vol = |vol_30d - vol_median| / vol_median
d_adx = |ADX_14 - 25| / 25
```

Both `d_vol` and `d_adx` represent the fractional distance from the classification boundary. A value of 0 means exactly on the boundary; higher values mean further into the regime zone.

**Step 2 — Clamp distances to [0, 1]:**

```
d_vol_clamped = min(d_vol, 1.0)
d_adx_clamped = min(d_adx, 1.0)
```

**Step 3 — Compute confidence as geometric mean:**

```
confidence = sqrt(d_vol_clamped × d_adx_clamped)
```

This produces a value in [0, 1].

**Confidence Bands:**

| Band | Confidence Range | Behavior |
|---|---|---|
| HIGH | confidence ≥ 0.5 | Normal trading with current strategy config |
| MEDIUM | 0.2 ≤ confidence < 0.5 | Normal trading; log regime as "soft" |
| LOW | confidence < 0.2 | Reduce position size by 50%; widen stops by 50% |

**Recompute Cadence:** Regime confidence is recomputed on every new 1h candle close, per instrument.

**Example:**
- vol_30d = 0.18, vol_median = 0.15, ADX_14 = 32
- d_vol = |0.18 - 0.15| / 0.15 = 0.20
- d_adx = |32 - 25| / 25 = 0.28
- confidence = sqrt(0.20 × 0.28) = sqrt(0.056) ≈ 0.237 → MEDIUM

#### 5.7.4 Regime-Aware Behavior

| Regime State | System Behavior |
|---|---|
| High confidence, any regime | Normal trading with current strategy config |
| Medium confidence | Normal trading; regime logged as "soft" |
| Low confidence (transitioning) | Reduce position size by 50%; widen stops by 50% |
| Model degradation in current regime (rolling 30-trade Sharpe < 0) | Halt new entries for that instrument (circuit breaker) |
| Manual override active | Use operator-specified regime until override cleared |

#### 5.7.5 Manual Override Controls

- API endpoint: `PUT /api/v1/regime/{instrument}/override`
- Body: `{"regime_label": "HIGH_VOL_RANGING", "reason": "Operator assessment", "expires_at": "2025-03-01T00:00:00Z"}`
- Override automatically expires at `expires_at` or when manually cleared via `DELETE /api/v1/regime/{instrument}/override`.
- All overrides are logged to `regime_log` with `trigger = 'manual_override'`.
- While override is active, automatic regime detection continues to run and log but does not control behavior.

#### 5.7.6 Regime in Reporting

- Every trade record includes `regime_label` at signal time.
- Backtest and live reports include:
  - Performance breakdown by regime (Sharpe, PF, win rate per regime).
  - Regime timeline chart showing regime transitions overlaid on equity curve.
  - Regime duration statistics.
- Charts display regime as colored background bands.

#### 5.7.7 Backtest Methodology for Regime-Aware Evaluation

- Walk-forward windows must be long enough to include multiple regime transitions (minimum 2 years training ensures this).
- Backtest reports include per-regime performance and a "regime-adjusted" Sharpe that weights performance by time-in-regime.
- If a regime has < 20 trades in any fold, its performance estimate is flagged as "low sample" and excluded from go/no-go decisions.

### 5.8 Dynamic Strategy Generation Roadmap

**Staged Capability:**

| Stage | Capability | Version | Description |
|---|---|---|---|
| 1 | Static configs | v1 | Strategy parameters defined in JSON config files. Validated offline via backtest. Edited manually or via UI. |
| 2 | Assisted parameter search | v1.1+ | Offline parameter search over candidate spaces (e.g., threshold sweeps, indicator parameter ranges). Results presented to operator for review. Not auto-deployed. |
| 3 | Server-side generation | v2+ | Automated pipeline that explores parameter spaces, evaluates candidates via walk-forward backtest, and emits versioned strategy config files. Requires approval gate before activation. |

**Governance Gates (all stages):**

1. **Proposal:** New/modified strategy config is generated (manually or automatically).
2. **Backtest validation:** Config must pass minimum performance bars on walk-forward backtest.
3. **Review:** Operator reviews backtest results, parameter choices, and rationale.
4. **Approval:** Operator explicitly approves (sets `approved = true` in `strategy_versions`). Approval must include evidence bundle reference (backtest run ID, metrics summary, regime coverage).
5. **Activation:** Approved config is promoted to active. Previous config is archived (never deleted).
6. **Monitoring:** Post-activation, track performance vs. backtest expectations. Auto-halt if deviation exceeds thresholds (Sharpe deviation > 50% from backtest, or any circuit breaker triggered).

**Acceptance Test:** Verify that a new strategy config cannot be activated without explicit approval. Verify that unapproved configs are not used for live trading.

---

## 6. Execution Model (Spot v1) and Reconciliation

### 6.1 Order Routing

- All orders are **market orders** sent via the instrument's broker adapter.
- v1 is **spot-only**: no leverage, no margin, no funding rates.
- Every order includes broker-side stop-loss:
  - **Oanda:** `stopLossOnFill` parameter on the order.
  - **Binance Spot:** A separate OCO (One-Cancels-Other) order is placed immediately after the entry fill, containing the stop-loss. If OCO placement fails after entry: close position immediately and alert.
- Every order has a unique `client_order_id` format: `NEWTON-{instrument}-{timestamp_ms}`.

**Binance Spot-Specific:**

- BTC/USDT orders use Binance Spot API (`POST /api/v3/order`).
- Minimum notional and lot size rules must be validated pre-submission.
- No funding rates apply (spot market).
- No contract type selection needed (spot, not futures).
- Commission is deducted from the received asset. Account for this in position sizing.

### 6.2 Slippage and Spread Modeling (Backtest) — DL-006

**Locked assumptions for v1 spot backtesting:**

| Parameter | EUR/USD (Oanda Spot) | BTC/USDT (Binance Spot) |
|---|---|---|
| Default spread | 1.5 pips | 0.05% of price |
| Default slippage | 1.0 pip | 0.02% of price |
| Pessimistic multiplier | 2× (applies to both spread and slippage) | 2× |
| Commission | Spread-inclusive (no separate commission) | 0.10% per trade (taker rate for spot) |
| Funding rate | N/A (spot) | N/A (spot) |
| Latency assumption | 100ms order-to-fill | 200ms order-to-fill |
| Fill model | Full fill at modeled price (market order) | Full fill at modeled price (market order) |
| Partial fill simulation | Not simulated in v1 (market orders assumed to fill fully) | Not simulated in v1 |
| Reject simulation | Not simulated in v1 (assumes sufficient liquidity) | Not simulated in v1 |

**Fill price (backtest):** `open[T+1] + slippage + spread/2` for buys; `open[T+1] - slippage - spread/2` for sells.

**Pessimistic mode:** All slippage and spread values are multiplied by the pessimistic multiplier (2×). Commission rates unchanged. This mode is available as a toggle when running backtests.

### 6.3 Retry and Idempotency

- Orders submitted with `client_order_id` for idempotency.
- Retry up to 3× on 5xx/timeout errors.
- Before retry, check for existing order with same `client_order_id` to prevent duplicates.
- No retry on 4xx (client error — log and alert).
- All retry attempts logged with timestamps and error details.

### 6.4 Reconciliation Loop

**Frequency:** Every 60 seconds, **per broker**.

**Process:**

1. Fetch all open positions from broker API.
2. Compare with internal `trades` table (status = 'OPEN').
3. Classify each position:

| State | Meaning | Action |
|---|---|---|
| MATCH | Internal and broker agree | Log OK |
| SYSTEM_EXTRA | System thinks position is open, broker does not | Alert (CRITICAL). Mark internal trade as CLOSED with `exit_reason = 'RECONCILIATION'`. |
| BROKER_EXTRA | Broker has position system doesn't know about | Alert (CRITICAL). Halt new entries for that instrument. Create internal record. Require manual review. |

4. Log result to `reconciliation_log` table.
5. Expose reconciliation status as Prometheus metric per broker: `newton_reconciliation_status{broker="oanda|binance", result="match|system_extra|broker_extra"}`.

---

## 7. Risk Model

### 7.1 Configuration Architecture (R-01)

All risk management parameters are **configurable per strategy**, defaulting to global spec defaults. This enables instrument-specific risk tuning while maintaining safe baselines.

**Configuration Precedence (highest to lowest):**

1. **Instrument override** (in `config/instruments/{INSTRUMENT}.json` → `risk_overrides`)
2. **Strategy override** (in `config/strategies/{INSTRUMENT}_strategy.json` → `risk_overrides`)
3. **Global default** (in `config/risk.json` → `defaults`)

When multiple levels specify the same parameter, the highest-precedence non-null value wins.

**Global Defaults Location:** `config/risk.json`

**Per-Strategy Override Schema:** The `risk_overrides` object in strategy configuration accepts any key from the global defaults. Only specified keys override; unspecified keys fall back to global defaults.

```json
// Example: BTC_USD strategy risk overrides
{
  "risk_overrides": {
    "hard_stop_pct": 0.03,
    "high_volatility_stop_pct": 0.05,
    "max_drawdown_pct": 0.25,
    "daily_loss_limit_pct": 0.03
  }
}
```

**Validation Constraints (preventing unsafe overrides):**

| Parameter | Minimum | Maximum | Rationale |
|---|---|---|---|
| `hard_stop_pct` | 0.005 (0.5%) | 0.10 (10%) | Prevent negligible or catastrophic stops |
| `max_risk_per_trade_pct` | 0.001 (0.1%) | 0.05 (5%) | Cap single-trade risk |
| `max_position_pct` | 0.005 (0.5%) | 0.20 (20%) | Cap position sizing |
| `daily_loss_limit_pct` | 0.005 (0.5%) | 0.05 (5%) | Cap daily losses |
| `max_drawdown_pct` | 0.05 (5%) | 0.30 (30%) | Prevent reckless drawdown tolerance |
| `kelly_fraction` | 0.10 | 0.50 | Half-Kelly to quarter-Kelly range |
| `time_stop_hours` | 1 | 168 (7 days) | Reasonable holding period bounds |

Any override outside these bounds is rejected at load time with a clear error message. The system will not start with invalid risk configuration.

**Audit Logging:** Every change to risk parameters (via UI, API, or config file reload) is logged to the `config_changes` table with: timestamp, who changed it, section, old value, new value, and reason.

### 7.2 Global Risk Defaults

```json
// config/risk.json
{
  "defaults": {
    "max_position_pct": 0.05,
    "max_risk_per_trade_pct": 0.02,
    "kelly_fraction": 0.25,
    "kelly_min_trades": 30,
    "kelly_window": 60,
    "micro_size_pct": 0.005,
    "hard_stop_pct": 0.02,
    "trailing_activation_pct": 0.01,
    "trailing_breakeven_pct": 0.02,
    "time_stop_hours": 48,
    "daily_loss_limit_pct": 0.02,
    "max_drawdown_pct": 0.20,
    "consecutive_loss_halt": 5,
    "consecutive_loss_halt_hours": 24,
    "gap_risk_multiplier": 2.0,
    "volatility_threshold_multiplier": 2.0,
    "high_volatility_size_reduction": 0.5,
    "high_volatility_stop_pct": 0.03
  },
  "portfolio": {
    "max_total_exposure_pct": 0.10,
    "max_portfolio_drawdown_pct": 0.20
  }
}
```

### 7.3 Pre-Trade Checks

| Check | Rule | On Failure | Configurable Per Strategy |
|---|---|---|---|
| Position limit | Max 1 open position per instrument | Reject new order | No (architectural constraint) |
| Portfolio exposure | Max total exposure across all instruments: `portfolio.max_total_exposure_pct` of equity (default 10%) | Reject new order | Portfolio-level only |
| Position sizing | Kelly 1/4, minimum of: Kelly result, `max_position_pct` of equity, `max_risk_per_trade_pct` risk per trade | Use smallest of the three | Yes |
| Circuit breaker active | Check daily loss and drawdown flags (per instrument + portfolio) | Reject new order | Yes (thresholds) |
| Data freshness | Last verified candle < 2 × interval ago | Reject new order | No (safety) |
| Model freshness | Days since last retrain < 30 | Alert (warning, not blocking) | No |
| Regime confidence | If regime confidence = LOW (< 0.2) | Reduce position size by 50% | Yes (confidence threshold) |

**Kelly Criterion Implementation:**

- Rolling window of the last `kelly_window` trades (default 60) per instrument.
- First `kelly_min_trades` trades (default 30): fixed `micro_size_pct` (default 0.5% of equity) micro-sizing.
- Hard cap: never risk > `max_risk_per_trade_pct` per trade, never exceed `max_position_pct` position.
- Kelly formula: `f* = kelly_fraction × (p × b - q) / b` where p = win rate, q = loss rate, b = average win / average loss.

### 7.4 In-Trade Controls

| Control | Specification | Implementation | Configurable Per Strategy |
|---|---|---|---|
| Hard stop-loss | `hard_stop_pct` below entry (default -2%, BTC -3%) | Broker-side stop at entry time | Yes |
| Trailing stop activation | Position profit reaches `trailing_activation_pct` (default +1%) | Modify broker stop to entry price (breakeven) | Yes |
| Trailing stop advance | Position profit reaches `trailing_breakeven_pct` (default +2%) | Modify broker stop to +1% above entry | Yes |
| Time stop | Position open > `time_stop_hours` (default 48 hours) | Market close order; `exit_reason = 'TIME_STOP'` | Yes |
| Volatility check | ATR(14) > `volatility_threshold_multiplier` × 30-day average at signal time (default 2×) | Reduce size by `high_volatility_size_reduction` (default 50%); widen hard stop to `high_volatility_stop_pct` | Yes |

**Stop Update Frequency:** On every new candle close AND on WebSocket tick updates for positions with profit > 0.5%.

**Gap Risk Mitigation:** Size assuming worst-case gap of `gap_risk_multiplier` × stop distance (default 2×).

### 7.5 Circuit Breakers

| Breaker | Trigger | Scope | Action | Reset | Configurable Per Strategy |
|---|---|---|---|---|---|
| Daily loss | Equity drops `daily_loss_limit_pct` from day-open (default 2%) | Per instrument + portfolio | Close positions; halt entries | Automatic at 00:00 UTC | Yes (threshold) |
| Max drawdown | Equity drops `max_drawdown_pct` from ATH (default 20%) | Per instrument (configurable) + portfolio | Close all; halt all | Manual intervention | Yes (threshold) |
| Consecutive losses | `consecutive_loss_halt` consecutive losers (default 5) | Per instrument | Halt entries for `consecutive_loss_halt_hours` (default 24h) | Automatic after timeout | Yes (both values) |
| Model degradation | Rolling 30-trade Sharpe < 0 | Per instrument | Halt entries | When Sharpe ≥ 0 | No (safety) |
| Kill switch | Manual activation | System-wide | Close ALL positions on ALL brokers | Manual reset | No (safety) |

**Kill Switch:**

- Available via UI button AND `POST /api/v1/kill` endpoint.
- On activation: close all positions on all brokers (market orders), cancel all pending, set `kill_switch_active = true`.
- Reset: manual only via `DELETE /api/v1/kill` (requires confirmation).
- Activation and reset are logged to `config_changes` with timestamp and reason.

---

## 8. Backtesting Framework and Realism Assumptions

### 8.1 Validation Methodology

**Primary: Walk-Forward Testing.**

- Minimum train window: 2 years.
- Test window: 6 months.
- Step: 6 months.
- Embargo: 48 hours (no data from 48h before test window start used in training).
- Minimum 4 folds.
- Runs independently per instrument.

**Secondary: Purged K-Fold.**

- K = 5, with 48-hour purge zones between folds.
- Used as robustness check; not the primary validation method.
- Runs independently per instrument.

### 8.2 Simulation Model

Per-instrument fill model using the locked realism assumptions from §6.2:

- **EUR/USD:** Fill at `open[T+1] ± (1.0 pip slippage + 0.75 pip half-spread)`. No separate commission.
- **BTC/USDT:** Fill at `open[T+1] ± (0.02% slippage + 0.025% half-spread)`. Plus 0.10% taker commission per trade.
- **Pessimistic mode:** 2× multiplier on slippage and spread. Commission unchanged.

No partial fills, no rejects simulated in v1. Market orders assumed to fill fully at the modeled price.

### 8.3 Bias Controls

| Bias | Mitigation |
|---|---|
| Look-ahead bias | Walk-forward with 48h embargo; event definitions use only past data |
| Overfitting | Walk-forward + purged K-fold; minimum trade count per fold |
| Survivorship bias | Flag for BTC/USDT (crypto pairs can be delisted); EUR/USD not affected |
| Selection bias | Fixed event catalog and token selection methodology; no manual cherry-picking |
| Data snooping | Hyperparameter search within walk-forward training windows only |

### 8.4 Regime-Aware Backtest Reporting

- Per-regime performance breakdown (Sharpe, PF, win rate per regime per instrument).
- Regime transition timeline overlaid on equity curve.
- Regime-adjusted metrics that weight by time-in-regime.
- Low-sample regime flagging: if a regime has < 20 trades in any fold, its performance estimate is flagged as "low sample" and excluded from go/no-go decisions.

---

## 9. Performance Metrics

### 9.1 Configuration Architecture (R-02)

Performance metric thresholds and targets are **configurable per strategy**, defaulting to the global spec defaults defined below. This allows instrument-specific performance expectations (e.g., wider drawdown tolerance for BTC/USD).

**Default Metric Thresholds (global):**

| Metric | Default Minimum Bar | Hard Gate | Informational | Per-Instrument |
|---|---|---|---|---|
| Sharpe Ratio | > 0.8 | Yes (go/no-go for live) | No | Yes |
| Profit Factor | > 1.3 | Yes (go/no-go for live) | No | Yes |
| Max Drawdown | < 15% | Yes (hard stop if breached) | No | Yes |
| Win Rate | > 45% | No | Yes (informational) | Yes |
| Calmar Ratio | > 0.5 | No | Yes (informational) | Yes |
| Expectancy | > 0 | Yes (must be positive) | No | Yes |
| Trade Count | > 30 per fold | Yes (minimum sample) | No | Yes |
| Calibration Error | < 5 pp per decile | Yes (retrain trigger) | No | Yes |

**Per-Strategy Override Capability:**

Strategy configurations can override thresholds via `performance_overrides`:

```json
{
  "performance_overrides": {
    "max_drawdown_pct": 0.25,
    "sharpe_ratio_min": 0.6,
    "win_rate_min": 0.40
  }
}
```

**Which metrics are hard gates vs. informational:**

- **Hard gates** (must be met for go/no-go decisions): Sharpe Ratio, Profit Factor, Max Drawdown, Expectancy, Trade Count, Calibration Error.
- **Informational** (tracked and reported but do not block progression): Win Rate, Calmar Ratio.

Changing a metric from informational to hard gate (or vice versa) requires a spec deviation record (see §13.1).

**Portfolio-Level Metrics (additional, not overridable per strategy):**

- Portfolio Sharpe (correlation-adjusted).
- Maximum portfolio drawdown (default < 20%).
- Correlation between instrument returns (target: < 0.5 for diversification benefit).

### 9.2 Metric Definitions

| Metric | Formula |
|---|---|
| Sharpe Ratio | `(mean_return - risk_free_rate) / std_return × √(252)` (annualized; use √365 for crypto-only) |
| Profit Factor | `sum(winning_trades_pnl) / abs(sum(losing_trades_pnl))` |
| Max Drawdown | `max(peak_equity - trough_equity) / peak_equity` |
| Win Rate | `count(winning_trades) / count(all_trades)` |
| Calmar Ratio | `annualized_return / max_drawdown` |
| Expectancy | `(win_rate × avg_win) - (loss_rate × avg_loss)` |
| Calibration Error | `max(abs(predicted_probability - observed_frequency))` per decile bin |

---

## 10. Client UI Functional Specification

### 10.1 Architecture

- **Framework:** React (or equivalent SPA framework) communicating exclusively via REST API and WebSocket.
- **Authentication:** HTTP basic auth (username/password from env vars). Accessible on localhost or via SSH tunnel only (DL-008: localhost/controlled access for v1).
- **No direct database access.** All data flows through server API.
- **Progressive delivery (DL-004):** Each implementation stage includes thin client milestones (see §15).

### 10.2 Dashboard (Home)

**Displays:**

- Portfolio equity curve (real-time via WebSocket).
- Per-instrument current status: active position, unrealized P&L, regime label, regime confidence, circuit breaker status.
- System health: API latency, data freshness per instrument, broker connectivity, reconciliation status.
- Recent alerts (last 24h).
- Kill switch button (prominent, requires confirmation dialog).

**Acceptance Criteria:**

- Dashboard loads in < 3 seconds.
- Equity curve updates within 5 seconds of position change.
- Kill switch activates within 2 seconds of confirmation.

### 10.3 Strategy Management

**Workflows:**

1. **View strategies:** List all strategy configs per instrument with version history.
2. **Create/edit strategy:** Form-based editor for strategy parameters (events, thresholds, risk overrides, performance overrides). Validates against schema before save.
3. **Compare strategies:** Side-by-side comparison of two strategy versions with highlighted differences.
4. **Activate strategy:** Promote an approved strategy version to active. Requires confirmation.
5. **Version history:** View all versions, diffs, approval status, evidence bundles, and performance notes.

**Acceptance Criteria:**

- User can create, save, and activate a strategy config without editing JSON directly.
- Invalid configurations (including unsafe risk overrides) are rejected with clear error messages.
- Strategy activation requires the config to be in "approved" state with evidence bundle.

### 10.4 Backtest Interface

**Workflows:**

1. **Run backtest:** Select instrument, strategy config (or version), date range, pessimistic mode toggle. Submit to server. Progress indicator shows status.
2. **View results:** Equity curve chart, trade list, performance metrics table (all metrics from §9), calibration plot, regime overlay.
3. **Trade overlay on charts:** Candlestick chart with entry/exit markers, stop-loss lines, regime bands.
4. **Compare backtests:** Side-by-side performance comparison of two backtest runs.
5. **Pessimistic mode toggle:** Run backtest with 2× slippage/spread.

**Acceptance Criteria:**

- Backtest of 2 years of 1h data completes within 60 seconds per instrument.
- Charts are interactive (zoom, pan, tooltip with trade details).
- All metrics from §9 are displayed.

### 10.5 Live Trading Monitor

**Displays:**

- Open positions with real-time P&L.
- Signal log: recent signals with scores, regime, and decision.
- Trade history: filterable by instrument, date range, result.
- Reconciliation status per broker.
- Circuit breaker status per instrument.

**Controls:**

- Manual position close (with confirmation).
- Pause/resume trading per instrument.
- Kill switch (system-wide).

### 10.6 System Configuration

**Configurable via UI:**

- Risk parameters (per instrument and global) — with validation against bounds from §7.1.
- Performance metric thresholds (per strategy) — with governance tracking.
- Alert preferences (Telegram on/off, alert levels).
- Regime override (set manual regime per instrument with expiry).
- Trading mode (paper/live) — requires elevated confirmation for switch to live.

**Not configurable via UI (require config file edit):**

- Database connection strings.
- API keys.
- Core system architecture settings.
- Validation constraint bounds (min/max for risk parameters).

### 10.7 Reports

- **Daily report:** P&L, trades, regime, alerts.
- **Weekly report:** Rolling Sharpe, drawdown, regime distribution, comparison to backtest expectations.
- **Monthly report:** Full performance analysis, backtest-to-live deviation, model freshness, system availability.
- Reports are viewable in UI and exportable as PDF.

### 10.8 In-App Help

- Every major UI section has a help icon that opens contextual documentation.
- Help content covers: what the section does, key concepts, common workflows, troubleshooting.
- Help content is stored as markdown files served by the API (`GET /api/v1/docs/{section}`).
- Help content is versioned with the application.

---

## 11. Monitoring, Operations, and Security

### 11.1 Logging

- Structured JSON to stdout.
- Every log entry includes: `timestamp` (UTC), `level`, `module`, `instrument` (if applicable), `broker` (if applicable), `message`, `extra` (structured data).
- Log levels: DEBUG, INFO, WARNING, ERROR, CRITICAL.
- No secrets in log output. Enforced via code review.

### 11.2 Metrics (Prometheus)

| Metric | Type | Labels |
|---|---|---|
| `newton_health` | Gauge | `module={data,analysis,trading}` |
| `newton_signal_latency_seconds` | Histogram | `instrument` |
| `newton_trades_total` | Counter | `instrument, direction, result={win,loss}` |
| `newton_pnl_current` | Gauge | `instrument` |
| `newton_equity` | Gauge | `scope={portfolio,EUR_USD,BTC_USD}` |
| `newton_drawdown_pct` | Gauge | `scope={portfolio,EUR_USD,BTC_USD}` |
| `newton_reconciliation_status` | Gauge | `broker, result` |
| `newton_model_rolling_sharpe` | Gauge | `instrument` |
| `newton_model_rolling_accuracy` | Gauge | `instrument` |
| `newton_data_staleness_seconds` | Gauge | `instrument, interval` |
| `newton_circuit_breaker_active` | Gauge | `instrument, type` |
| `newton_regime_current` | Gauge | `instrument, regime_label` |
| `newton_regime_confidence` | Gauge | `instrument` |
| `newton_api_request_duration_seconds` | Histogram | `endpoint, method` |

### 11.3 Alerts (Telegram)

| Alert | Level | Trigger |
|---|---|---|
| Broker API failure (after retries) | CRITICAL | 3 failed retries |
| Reconciliation mismatch | CRITICAL | SYSTEM_EXTRA or BROKER_EXTRA |
| Kill switch activated | CRITICAL | Manual activation |
| Circuit breaker triggered | WARNING | Any breaker fires |
| Data staleness | WARNING | No new candle within 2× interval |
| Model degradation | WARNING | Rolling Sharpe < 0 |
| Regime transition | INFO | Regime label changed |
| Trade executed | INFO | Order filled |
| Daily summary | INFO | 00:00 UTC daily |

Each alert message includes: timestamp, instrument (if applicable), broker (if applicable), and actionable context.

### 11.4 Health Checks

- **Endpoint:** `GET /api/v1/health`
- **Response:** `200 OK` with JSON:

```json
{
  "status": "healthy",
  "db": true,
  "brokers": {
    "oanda": {"connected": true, "last_response_ms": 45},
    "binance": {"connected": true, "last_response_ms": 32}
  },
  "instruments": {
    "EUR_USD": {"last_candle_age_seconds": 120, "reconciled": true, "regime": "LOW_VOL_TRENDING", "regime_confidence": 0.65},
    "BTC_USD": {"last_candle_age_seconds": 85, "reconciled": true, "regime": "HIGH_VOL_RANGING", "regime_confidence": 0.42}
  },
  "kill_switch_active": false,
  "uptime_seconds": 86400
}
```

### 11.5 Security and Secrets

- **Oanda API key:** Stored as env var `OANDA_API_KEY`. Generated with trade-only permissions.
- **Binance API keys:** Stored as env vars `BINANCE_API_KEY` and `BINANCE_API_SECRET`. Generated with spot-trade-only permissions (no withdrawal, no transfer, no futures).
- **Binance IP whitelist:** API keys restricted to server IP.
- **UI auth:** HTTP basic auth (username/password from env vars `NEWTON_UI_USER` and `NEWTON_UI_PASS`).
- **Exposure policy (DL-008):** v1 is localhost/SSH-tunnel only. No public internet exposure. If external access is needed in future, requires upgrade to stronger auth (OIDC/JWT or VPN/Tailscale).
- **No secrets in code or config files.** All secrets loaded from environment variables. Enforced via CI secret scan.
- **Database:** Accessible only from localhost. No remote connections.

### 11.6 Runbooks

Runbooks are maintained in `docs/ops/runbooks.md` and cover:

1. **Broker API outage** — detection, impact assessment, manual intervention, recovery verification.
2. **Database failure** — restart procedures, backup restoration, data integrity verification.
3. **Reconciliation mismatch** — investigation steps, manual resolution, root cause documentation.
4. **Kill switch activation** — when to use, post-activation checklist, restart procedure.
5. **Model retraining** — schedule, validation criteria, rollback if metrics degrade.
6. **Binance-specific** — rate limit exceeded, IP whitelist update, API key rotation.
7. **Data gap recovery** — manual backfill procedures, verification.

---

## 12. Documentation Strategy

### 12.1 Documentation Types

| Type | Audience | Content | Location |
|---|---|---|---|
| **Developer docs** | Developer (self) | Architecture decisions, module APIs, data flows, contribution guide, setup instructions | `docs/dev/` in repo |
| **Operator docs** | System operator | Deployment, configuration, monitoring, runbooks, troubleshooting | `docs/ops/` in repo |
| **User docs** | UI user (may be same person) | UI workflows, strategy management, interpreting reports, FAQ | `docs/user/` in repo, served via API for in-app help |
| **API docs** | Any client developer | REST API reference (auto-generated from OpenAPI) | Auto-generated, served at `/api/v1/docs` |

### 12.2 Documentation Deliverables Per Stage

| Stage | Developer Docs | Operator Docs | User Docs |
|---|---|---|---|
| Stage 1 (Data) | Data pipeline architecture, schema docs, fetcher API | DB setup, data backfill procedures | — |
| Stage 2 (Analysis) | Event/token/Bayesian engine internals, feature store API | Model training procedures | — |
| Stage 3 (ML) | ML pipeline, feature engineering, model evaluation | Model retraining runbook | — |
| Stage 4 (Trading) | Risk engine, executor, reconciler internals | Risk config guide, circuit breaker reference | — |
| Stage 5 (Backtest) | Backtest engine architecture | Running backtests, interpreting results | Backtest UI guide |
| Stage 6 (Integration) | Client architecture, API contract | Deployment, auth setup | Full UI user guide, in-app help |
| Stage 7 (Paper) | Paper trading specifics | Paper account setup, monitoring | Paper trading guide |
| Stage 8 (Live) | — | Live deployment checklist, incident response | Live trading guide |

---

## 13. Governance

### 13.1 Spec Deviation Protocol

When implementation reveals a better solution than what the spec prescribes:

**Process:**

1. **Trigger:** Developer identifies that deviating from the spec would produce a better outcome.
2. **Document:** Create a spec deviation record (in `spec_deviations` table AND `spec/deviations/DEV-NNN.md`):
   - Spec section affected.
   - What the spec says vs. what is proposed.
   - Justification with evidence (benchmark, simplicity, safety, etc.).
   - Impact assessment (what else changes as a result).
   - Risk assessment (what could go wrong with the deviation).
3. **Review:** Self-review against checklist:
   - Does this compromise safety? (If yes: do not deviate without external review.)
   - Does this change the risk profile? (If yes: update risk documentation.)
   - Does this affect other stages? (If yes: document cascading impacts.)
4. **Approve:** Mark deviation as APPROVED (or REJECTED with reasoning).
5. **Implement:** Proceed with implementation. Reference deviation ID in code comments and commit messages.
6. **Changelog:** Update spec changelog with deviation summary.

**Principle:** Adherence to spec is important, but the spec serves the system, not the other way around. Deviations must be explicit, justified, and traceable.

### 13.2 Strategy Approval and Rollback (DL-007)

**Approval Authority:**

- BJ (sole developer/operator) is the approval authority for all strategy configuration changes.
- No automated system may activate a strategy without explicit human approval.

**Required Evidence Before Approval:**

1. Walk-forward backtest results showing all hard-gate metrics met (§9.1).
2. Pessimistic mode backtest results (2× slippage/spread).
3. Per-regime performance breakdown showing no regime with Sharpe < 0 (where sample size ≥ 20 trades).
4. Comparison against currently active strategy (improvement or acceptable trade-off documented).
5. Evidence bundle stored in `strategy_versions.approval_evidence` as JSON reference to backtest run IDs.

**Rollback Triggers:**

- Live Sharpe deviation > 50% below backtest Sharpe (measured over rolling 30-trade window).
- Any circuit breaker triggered that was not triggered in backtesting.
- Two consecutive weeks of negative P&L not seen in backtest.
- Manual operator decision at any time.

**Emergency Rollback Process:**

1. Activate kill switch if positions are at risk.
2. Revert to previously active strategy version via `PUT /api/v1/strategy/{instrument}/activate` with previous version ID.
3. Log rollback with reason to `config_changes`.
4. Post-mortem analysis within 24 hours.

**Audit Trail:**

- All strategy version changes logged in `strategy_versions` table (never deleted).
- All activations and rollbacks logged in `config_changes` table.
- Evidence bundles referenced and preserved.

---

## 14. Branching and Stage Gates

### 14.1 Branch Strategy

- `main` — protected baseline. Always deployable. No direct commits.
- `stage/{N}-{name}` — development branch for each stage (e.g., `stage/1-data-pipeline`).
- Feature branches off stage branches for larger sub-tasks.

### 14.2 Stage Lifecycle

1. Create `stage/{N}-{name}` branch from `main`.
2. Develop and test on stage branch.
3. Stage exit criteria must be met before merge.
4. PR to `main` with checklist review.
5. Merge to `main`. Tag release (e.g., `v0.1.0` for Stage 1).

### 14.3 Stage Exit Gate Checklist (DL-010)

Every stage merge to `main` requires all of the following:

**Automated checks (CI must pass):**

| Check | Tool | Threshold |
|---|---|---|
| Unit tests | pytest | All pass |
| Integration tests | pytest | All pass |
| Type checking | mypy (strict mode) | Zero errors |
| Linting | ruff | Zero errors |
| Secret scan | gitleaks or truffleHog | Zero findings |
| Code coverage (global) | pytest-cov | ≥ 80% line coverage |
| Code coverage (critical paths) | pytest-cov | 100% branch coverage for: risk engine, order execution, reconciliation, circuit breakers |
| API schema validation | openapi-spec-validator | Pass |
| No timezone-naive datetimes | custom lint rule | Zero violations |

**Manual checks (self-review checklist):**

- [ ] All functional requirements for the stage are implemented.
- [ ] No CRITICAL or HIGH severity bugs open.
- [ ] Documentation deliverables for the stage are complete.
- [ ] Performance within NFR bounds (signal latency < 5s, API response < 200ms p95).
- [ ] Any spec deviations documented and approved.
- [ ] Client milestones for the stage are met.
- [ ] PR description includes summary of changes and test evidence.

**Branch protection rules for `main`:**

- No direct pushes.
- PR required with at least self-review.
- All CI checks must pass.
- Squash merge preferred for clean history.

---

## 15. Stage-by-Stage Implementation Plan

### 15.1 Project Status

**No code has been written.** This plan starts from zero.

### 15.2 Stages

#### Stage 1: Data Pipeline

**Duration:** 3-4 weeks.

**Server Milestones:**

| Deliverable | Acceptance Criteria |
|---|---|
| Oanda data fetcher (EUR/USD) | Historical + real-time candle ingestion; row count matches expected ±1% for 3-year backfill |
| Binance spot data fetcher (BTC/USDT) | Historical + real-time candle ingestion; row count matches expected ±1% for 3-year backfill |
| TimescaleDB schema setup | All tables created per §4.2, hypertables configured, indexes verified |
| Feature store (technical indicators) | RSI, MACD, BB, OBV, ATR computed and stored for both instruments; output matches TA-Lib reference < 0.01% deviation on 100 random candles |
| Data quality checks | Gap detection, OHLC verification, staleness watchdog operational |
| Data backfill (3 years both instruments) | Verified data for 2023-01-01 to present for both instruments |
| Health endpoint (`/api/v1/health`) | Returns DB + broker connectivity status |
| API: data query endpoints | OHLCV + feature retrieval via REST; OpenAPI schema published |
| Feature store benchmark | < 500ms for 60-period lookback across 5 indicators |

**Client Milestones (DL-004 — thin client each stage):**

| Deliverable | Acceptance Criteria |
|---|---|
| Health/status page | Displays system health, DB status, broker connectivity, data freshness per instrument |
| Data viewer | View recent candles and indicator values per instrument/interval |

**Exit Criteria:** Verified 3-year data for both instruments. Feature store populated and benchmarked. Health endpoint operational. Client health page functional. All Stage 1 tests pass. All gate checks from §14.3 pass.

---

#### Stage 2: Event Detection & Bayesian Engine

**Duration:** 3-4 weeks.

**Server Milestones:**

| Deliverable | Acceptance Criteria |
|---|---|
| Event detection engine | Configurable per instrument; detects events matching hand-calculated expectations on known price series |
| Token generator + classifier | Per-instrument token vocabularies producing correct tokens for known indicator values |
| Token selection (MI ranking, redundancy filter) | On synthetic data: informative token selected, noise token excluded |
| Bayesian scorer + isotonic calibration | Calibrated probabilities with < 5pp deviation per decile on out-of-fold data |
| Signal endpoint (`/api/v1/signal/{instrument}`) | Returns current signal with score, confidence, regime, and metadata |
| Backfill events + tokens (3 years both instruments) | Events and tokens computed for all historical data |

**Client Milestones:**

| Deliverable | Acceptance Criteria |
|---|---|
| Signal viewer | Displays current signal per instrument with score and metadata |
| Event/token explorer | Browse detected events and active tokens for recent candles |

**Exit Criteria:** Bayesian scores produced for both instruments. Calibration within bounds. Client signal viewer functional. All gate checks pass.

---

#### Stage 3: ML Model Integration

**Duration:** 3-4 weeks.

**Server Milestones:**

| Deliverable | Acceptance Criteria |
|---|---|
| Feature engineering pipeline | Rolling windows, returns, feature vectors built from feature store |
| XGBoost training with Optuna | Walk-forward evaluation per instrument; AUC > 0.55 (or fallback documented) |
| CNN-LSTM (conditional) | Available if XGBoost AUC < 0.55 for any instrument |
| Model artifact storage + versioning | Models saved with hash, metadata, version; integrity verified on load |
| Meta-learner (logistic regression) | Combined calibrated signal per instrument; calibration < 5pp |

**Client Milestones:**

| Deliverable | Acceptance Criteria |
|---|---|
| Model status page | Shows model version, last training date, AUC, feature importance per instrument |
| Combined signal display | Updated signal viewer shows combined (meta-learner) score |

**Exit Criteria:** ML model AUC > 0.55 per instrument (or Bayesian-only fallback documented). Meta-learner producing calibrated output. Client model status page functional. All gate checks pass.

---

#### Stage 4: Trading Engine & Risk Management

**Duration:** 3-4 weeks.

**Server Milestones:**

| Deliverable | Acceptance Criteria |
|---|---|
| Signal interpretation + thresholds | Signal → action mapping per instrument per strategy config |
| Broker adapters (Oanda spot + Binance spot) | Both adapters passing integration tests with paper/testnet accounts |
| Order execution (market orders + stops) | Paper orders placed successfully on both brokers with stop-loss |
| Position lifecycle management | Open, modify stop, close working per broker |
| Risk engine (Kelly, circuit breakers, per-strategy config) | All pre-trade and in-trade checks functional; validation rejects unsafe overrides |
| Reconciliation loop | Per-broker reconciliation running every 60s; mismatch detection verified |
| Kill switch | Closes all positions on all brokers within 30 seconds |
| Regime detection | Regime labels computed per instrument using §5.7.3 formula |
| Trading API endpoints | All trading operations available via API |

**Client Milestones:**

| Deliverable | Acceptance Criteria |
|---|---|
| Trading status panel | Shows open positions, regime, circuit breaker status per instrument |
| Kill switch button | Functional with confirmation dialog |
| Risk configuration UI | View/edit risk parameters per instrument with validation feedback |

**Exit Criteria:** Complete signal-to-trade pipeline running on paper/testnet. All circuit breakers tested. Reconciliation tested. Kill switch tested. Client trading panel functional. All gate checks pass.

---

#### Stage 5: Backtesting Engine

**Duration:** 2-3 weeks.

**Server Milestones:**

| Deliverable | Acceptance Criteria |
|---|---|
| Walk-forward framework | Per-instrument backtesting with configurable windows; minimum 4 folds |
| Purged K-fold (robustness check) | Secondary validation available; K=5 with 48h purge |
| Performance metrics calculation | All metrics from §9 computed correctly |
| Pessimistic mode | 2× slippage/spread testing available |
| Regime-aware reporting | Per-regime performance breakdown; low-sample flagging |
| Backtest API endpoints | Run backtest, get results via API |

**Client Milestones:**

| Deliverable | Acceptance Criteria |
|---|---|
| Backtest runner | Select instrument, strategy, date range, pessimistic mode; submit and track progress |
| Results viewer | Equity curve, trade list, all metrics, calibration plot, regime overlay |
| Trade overlay charts | Candlestick chart with entry/exit markers, stop-loss lines, regime bands; interactive (zoom, pan, tooltip) |
| Backtest comparison | Side-by-side comparison of two runs |

**Exit Criteria:** Backtest results meet minimum metric bars per instrument. Client backtest UI fully functional. Pessimistic mode available. All gate checks pass.

---

#### Stage 6: Integration, Full UI & Documentation

**Duration:** 3-4 weeks.

**Server Milestones:**

| Deliverable | Acceptance Criteria |
|---|---|
| OpenAPI docs auto-generation | Published at `/api/v1/docs`; schema passes validation |
| In-app help content API | `GET /api/v1/docs/{section}` returns markdown help content |
| End-to-end integration tests | Full pipeline tested: data → analysis → signal → risk check → order |

**Client Milestones:**

| Deliverable | Acceptance Criteria |
|---|---|
| Dashboard (full) | Portfolio equity, instrument status, health, alerts, kill switch — per §10.2 |
| Strategy management | Full CRUD, version history, comparison, approval workflow — per §10.3 |
| Live trading monitor | Positions, signals, trade history, reconciliation, circuit breakers — per §10.5 |
| System configuration | Risk params, alerts, regime overrides, trading mode — per §10.6 |
| Reports | Daily/weekly/monthly reports, PDF export — per §10.7 |
| In-app help | Help content per major section — per §10.8 |

**Documentation Milestones:**

| Deliverable | Acceptance Criteria |
|---|---|
| Developer docs | Architecture, module APIs, setup guide in `docs/dev/` |
| Operator docs | Deployment, configuration, monitoring, runbooks in `docs/ops/` |
| User docs | UI workflows, strategy guide, FAQ in `docs/user/` |

**Exit Criteria:** Full UI functional per §10. In-app help available. All documentation deliverables complete. All gate checks pass.

---

#### Stage 7: Paper Trading

**Duration:** 3 months minimum.

**Server Milestones:**

| Deliverable | Acceptance Criteria |
|---|---|
| Oanda practice account integration | Real-time paper trading for EUR/USD |
| Binance testnet integration | Real-time paper trading for BTC/USDT spot |
| WebSocket price monitoring | Real-time position management |
| Real-time signal generation | Signals on live candle closes |
| Telegram alerting | Trade alerts flowing |

**Client Milestones:**

| Deliverable | Acceptance Criteria |
|---|---|
| Real-time dashboard | Live equity curve, positions, signals updating in real-time |
| Paper trading performance tracking | All metrics tracked and displayed live |

**Go/No-Go Criteria (per instrument, all hard-gate metrics must be met):**

- Sharpe > 0.8 (or per-strategy override).
- Profit Factor > 1.3 (or per-strategy override).
- Max drawdown < 15% (or per-strategy override).
- Backtest-to-paper Sharpe deviation < 20%.
- ≥ 50 trades executed.
- No CRITICAL reconciliation mismatches unresolved.
- No kill-switch activations due to bugs.
- Calibration error < 5pp.
- **If criteria not met:** Do not go live. Diagnose, fix, reset paper trading timer.

---

#### Stage 8: Live Trading

**Duration:** Ongoing.

**Milestones:**

| Deliverable | Acceptance Criteria |
|---|---|
| Live broker account setup | Accounts funded, API keys configured with appropriate permissions |
| Micro-sizing phase (first 30 trades per instrument) | 0.5% equity per trade; all trades logged and reconciled |
| Kelly sizing enablement | After 30 trades with positive metrics per instrument |
| Monthly review process | Full analysis against paper baseline; documented |

**Instruments may go live independently.** If EUR/USD meets criteria but BTC/USD does not, EUR/USD can go live while BTC/USD continues paper trading.

---

## 16. Open Questions

| # | Question | Impact | Owner | Resolution Path |
|---|---|---|---|---|
| OQ-1 | Optimal lookback for ML input sequences per instrument | ML performance | BJ | Hyperparameter search in Stage 3. Start with 24. |
| OQ-2 | Optimal token count per instrument | Signal quality | BJ | Evaluate MI curve in Stage 2. Start with 20. |
| OQ-3 | Should SELL signals open short positions? | Revenue potential | BJ | v1: close longs only. Evaluate in backtest. Decision for v1.1. |
| OQ-4 | Multi-timeframe confirmation weighting | Signal quality | BJ | Deferred to v1.1. |
| OQ-5 | Break-even trade frequency per instrument | Viability | BJ | Calculate in Stage 5. |
| OQ-6 | GPU needed for XGBoost inference? | Deployment | BJ | XGBoost is CPU-only. CNN-LSTM may need GPU. |
| OQ-7 | BTC/USD success criteria adjustments | Go/no-go | BJ | Evaluate during Stage 5 backtesting. Decide before paper trading. Configure via performance_overrides. |
| OQ-8 | Correlation target between EUR/USD and BTC/USD returns | Portfolio construction | BJ | Measure in Stage 5 backtesting. < 0.5 desired. |

---

## 17. Decision Log

| # | Decision | Date | Rationale |
|---|---|---|---|
| D-1 | TimescaleDB as database | Pre-dev | Good fit for time-series data. |
| D-2 | EUR/USD via Oanda (spot) | Pre-dev | Liquidity, spread, data quality. |
| D-3 | BTC/USDT via Binance (spot) | FINAL | Multi-instrument from day one; crypto diversification. Spot for v1 simplicity. |
| D-4 | Token format: `{INSTRUMENT}_PREFIX_PARAM_DATAPOINT_TYPE_VALUE` | v3 spec | Instrument-aware, structured, parseable. |
| D-5 | Monolith architecture for v1 | v2 spec | Solo developer, single machine. |
| D-6 | XGBoost before CNN-LSTM | v2 spec | Faster iteration, easier debugging. |
| D-7 | Meta-learner over fixed weights | v2 spec | Calibrated, data-driven. |
| D-8 | Broker-side stops mandatory | v2 spec | Non-negotiable safety. |
| D-9 | Daily loss limit: 2% | v2 spec | Conservative for unproven system. |
| D-10 | Micro-sizing for first 30 trades | v2 spec | Protect capital during learning. |
| D-11 | Feature store (long-format) over fixed columns | v3 spec | Scalable, extensible, multi-instrument native. |
| D-12 | API-first client/server separation | v3 spec | Replaceable UI, testable contracts. |
| D-13 | React SPA over Streamlit | v3 spec | Better interactivity, proper separation. |
| D-14 | Zero-code baseline (corrected project status) | v3 spec | Accurate status. |
| D-15 | Spot-only for v1 (no futures) | FINAL (DL-002) | Simplicity; no funding rates, no margin complexity. Architecture supports future derivatives. |
| D-16 | Spec/docs in `spec/` subfolder | FINAL (DL-001) | Clean organization, versioned artifacts. |
| D-17 | Thin client each stage | FINAL (DL-004) | Progressive delivery; both server and client progress per stage. |
| D-18 | Localhost/SSH-tunnel only for v1 UI | FINAL (DL-008) | Adequate for solo/controlled use. Upgrade path defined. |
| D-19 | Risk params configurable per strategy | FINAL (R-01) | Instrument-specific tuning with safe defaults and validation. |
| D-20 | Performance metrics configurable per strategy | FINAL (R-02) | Different instruments have different performance profiles. |
| D-21 | Feature provider extensibility | FINAL (R-03) | Add indicators without schema changes or disruptive refactor. |

---

## 18. Alternatives Considered

| Decision | Options | Choice | Rationale |
|---|---|---|---|
| Architecture | Microservices vs. Monolith | Monolith (v1) | Single developer, single machine. Extract when needed. |
| ML Model | CNN-LSTM vs. XGBoost vs. Bayesian-only | XGBoost first, CNN-LSTM conditional | Faster iteration, easier debugging, feature importance. |
| Signal Combination | Fixed weights vs. Meta-learner | Meta-learner (logistic regression) | Calibrated output, data-driven weighting. |
| Database | TimescaleDB vs. ClickHouse vs. Parquet | TimescaleDB | Good SQL + time-series. Single-server simplicity. |
| Instruments | EUR/USD only vs. multi-instrument | Multi-instrument from v1 | Forces robust architecture; diversification. |
| Indicator storage | Fixed columns vs. JSONB vs. Feature store | Feature store (long-format) | Scalable, no-migration additions, namespace isolation. |
| Order Type | Market vs. Limit | Market (v1) | Guaranteed fill. Track savings for v2. |
| Stop-Loss | System-side vs. Broker-side | Broker-side | System crash cannot lose the stop. Non-negotiable. |
| Validation | Walk-forward only vs. + Purged K-fold | Both | Walk-forward primary, K-fold for robustness. |
| Client/Server | Tight coupling vs. API-first | API-first with strict separation | Replaceable UI, testable contracts. |
| UI Framework | Streamlit vs. React SPA | React SPA (or equivalent) | Better interactivity, charts, proper separation. |
| BTC venue | Futures vs. Spot | Spot (v1) | Simpler execution, no funding rates, no leverage risk. |
| Client delivery | Deferred until late stages vs. Thin client each stage | Thin client each stage | Progressive delivery, early feedback. |

---

## 19. Appendices

### Appendix A: Configuration Files Reference

#### `config/system.json`

```json
{
  "instruments": ["EUR_USD", "BTC_USD"],
  "signal_interval": "1h",
  "db_url": "ENV:DATABASE_URL",
  "telegram_bot_token": "ENV:TELEGRAM_BOT_TOKEN",
  "telegram_chat_id": "ENV:TELEGRAM_CHAT_ID",
  "api_version": "v1",
  "api_port": 8000,
  "log_level": "INFO"
}
```

#### `config/risk.json`

See §7.2 for full contents.

#### `config/instruments/EUR_USD.json`

See §3.4 for full contents.

#### `config/instruments/BTC_USD.json`

See §3.4 for full contents.

#### `config/feature_providers.json`

```json
{
  "providers": [
    {
      "name": "technical",
      "class": "newton.data.indicators.TechnicalIndicatorProvider",
      "namespace": "technical",
      "enabled": true,
      "config": {
        "indicators": [
          {"key": "rsi", "params": {"period": 14}},
          {"key": "macd", "params": {"fast": 12, "slow": 26, "signal": 9}},
          {"key": "bb", "params": {"period": 20, "std": 2.0}},
          {"key": "obv", "params": {}},
          {"key": "atr", "params": {"period": 14}}
        ]
      }
    }
  ]
}
```

### Appendix B: Functional Requirements Traceability

| ID | Requirement | Acceptance Test | Spec Section |
|---|---|---|---|
| FR-01 | Fetch and store historical OHLCV data for EUR/USD (Oanda) and BTC/USDT (Binance spot) across 1m, 5m, 1h, 4h, 1d | Given a date range per instrument, verify row count matches expected candles ±1% | §4.1 |
| FR-02 | Detect and backfill data gaps automatically per instrument | Insert a known gap; verify system detects and fills it within one pipeline cycle | §4.4 |
| FR-03 | Calculate and store extensible technical indicators (initial: RSI(14), MACD(12,26,9), BB(20,2.0), OBV, ATR(14)) per instrument via feature provider interface | Compare output against a reference library (TA-Lib) for 100 random candles per instrument; max deviation < 0.01% | §4.3 |
| FR-04 | Define events in configuration per instrument and detect them in historical data | For a known price series, verify event labels match hand-calculated expectations | §4.6 |
| FR-05 | Generate tokens from indicator states using configured classification rules per instrument | Given indicator values, verify token output matches expected strings | §5.2 |
| FR-06 | Calculate Bayesian posterior P(Event \| Tokens) with calibration | Verify calibration: for predicted probabilities in [0.5, 0.6], observed frequency is 50-60% on held-out data | §5.4 |
| FR-07 | Train and serve ML model (XGBoost or CNN-LSTM) per instrument for event probability | Model achieves out-of-sample AUC-ROC > 0.55 per instrument | §5.5 |
| FR-08 | Combine Bayesian and ML scores via meta-learner to produce calibrated signal per instrument | Calibration plot deviation < 5 pp per decile on out-of-sample data | §5.6 |
| FR-09 | Execute market orders via Oanda (EUR/USD spot) and Binance (BTC/USDT spot) with broker-side stop-loss | Place a paper trade on each broker; verify order and stop appear in respective accounts | §6.1 |
| FR-10 | Manage position lifecycle (open, update stop, close) per instrument | Open position, update trailing stop, close; verify each state in broker account | §7.4 |
| FR-11 | Enforce pre-trade risk checks (Kelly sizing, max exposure) per instrument and portfolio with configurable parameters | Attempt to exceed limits; verify rejection. Verify per-strategy overrides take precedence. | §7.3 |
| FR-12 | Enforce circuit breakers (daily loss, max drawdown) per instrument and portfolio with configurable thresholds | Simulate 2% daily loss; verify system halts new entries | §7.5 |
| FR-13 | Reconcile internal state with broker state every 60 seconds per broker | Introduce a mismatch; verify alert fires within 2 minutes | §6.4 |
| FR-14 | Provide kill switch that closes all positions across all brokers and halts trading | Activate kill switch; verify all positions closed within 30 seconds | §7.5 |
| FR-15 | Detect market regime using deterministic formula and track regime transitions per instrument | On synthetic data transitioning regimes, verify detection, labeling, and confidence scores | §5.7 |
| FR-16 | Provide regime-aware reporting showing active regime and switch events | Verify reports show regime labels, confidence, and transition timestamps | §5.7.6 |
| FR-17 | Expose all server functionality through versioned REST API | API schema validation passes; no direct DB access from client | §3.2 |
| FR-18 | Web UI: strategy management (add, edit, view, compare configurations) with risk/performance override editing | User can perform full CRUD on strategy configs via UI; invalid overrides rejected | §10.3 |
| FR-19 | Web UI: backtest execution and result visualization with trade overlays on charts | Run backtest from UI; verify chart with entry/exit markers renders | §10.4 |
| FR-20 | Web UI: detailed backtest reports with all metrics from §9 | Verify report contains all specified metrics | §10.4 |
| FR-21 | Web UI: system configuration management including per-strategy risk/performance overrides | Modify risk parameters via UI; verify server applies changes and logs audit entry | §10.6 |
| FR-22 | In-app usage documentation accessible from UI | Verify help content loads for each major UI section | §10.8 |
| FR-23 | Feature provider extensibility: new indicators addable without schema migration | Add a test indicator via provider interface; verify features stored and retrievable | §3.6, §4.3 |
| FR-24 | Risk parameter audit logging for all changes | Change a risk parameter; verify entry in config_changes table | §7.1 |

### Appendix C: Non-Functional Requirements

| ID | Requirement | Measurement | Spec Section |
|---|---|---|---|
| NFR-01 | Signal generation latency < 5 seconds from candle close confirmation | Measure p99 latency in paper trading over 1000 candles per instrument | §1.6 |
| NFR-02 | System availability > 99.5% | Percentage of 1-minute intervals where `/health` returns 200 | §1.6 |
| NFR-03 | All timestamps in UTC | Code review; no timezone-naive datetime objects allowed; lint rule enforced | §4.5 |
| NFR-04 | Structured JSON logging to stdout | Log format validation in CI | §11.1 |
| NFR-05 | Prometheus-format `/metrics` endpoint | Scrape test in CI | §11.2 |
| NFR-06 | Secrets loaded from environment variables only | No secrets in code or config files; CI secret scan | §11.5 |
| NFR-07 | Recovery from crash: system resumes within 60 seconds and reconciles state | Kill process during paper trading; measure recovery time | §3.5 |
| NFR-08 | API response time < 200ms for read endpoints (p95) | Load test in CI | §3.2 |

### Appendix D: Project Layout

```
newton/
├── spec/                             # Canonical spec location (DL-001)
│   ├── docs/spec/SPEC_DRAFT.md       # This document
│   ├── SPEC.v3.md                    # Previous version (archived)
│   ├── SPEC.v2.md                    # Previous version (archived)
│   ├── SPEC_NOTES.md                 # Iteration notes (archived)
│   ├── SPEC_DECISIONS_LOCK.md        # Decision locks (archived)
│   ├── SPEC_REVISIONS.md             # Revision instructions (archived)
│   ├── deviations/                   # Spec deviation records
│   │   └── DEV-001.md               # Example deviation
│   └── decisions/                    # Architecture Decision Records
│       └── ADR-001-feature-store.md  # Example ADR
├── docs/
│   ├── dev/                          # Developer documentation
│   ├── ops/                          # Operator documentation
│   └── user/                         # User documentation (also served in-app)
├── config/
│   ├── system.json
│   ├── risk.json
│   ├── feature_providers.json
│   ├── instruments/
│   │   ├── EUR_USD.json
│   │   └── BTC_USD.json
│   ├── strategies/
│   │   ├── EUR_USD_strategy.json
│   │   └── BTC_USD_strategy.json
│   └── classifications/
│       ├── EUR_USD_classifications.json
│       └── BTC_USD_classifications.json
├── src/
│   ├── __init__.py
│   ├── app.py                        # FastAPI entry point
│   ├── api/
│   │   ├── __init__.py
│   │   ├── v1/
│   │   │   ├── __init__.py
│   │   │   ├── data.py
│   │   │   ├── signals.py
│   │   │   ├── trading.py
│   │   │   ├── backtest.py
│   │   │   ├── config.py
│   │   │   ├── regime.py
│   │   │   └── docs.py
│   │   └── schemas.py
│   ├── data/
│   │   ├── __init__.py
│   │   ├── database.py
│   │   ├── fetcher_oanda.py
│   │   ├── fetcher_binance.py
│   │   ├── fetcher_base.py
│   │   ├── indicators.py
│   │   ├── feature_store.py
│   │   ├── feature_provider.py
│   │   ├── pipeline.py
│   │   ├── schema.py
│   │   └── verifier.py
│   ├── analysis/
│   │   ├── __init__.py
│   │   ├── events.py
│   │   ├── tokenizer.py
│   │   ├── token_selection.py
│   │   ├── bayesian.py
│   │   ├── ml_model.py
│   │   └── meta_learner.py
│   ├── trading/
│   │   ├── __init__.py
│   │   ├── signal.py
│   │   ├── risk.py
│   │   ├── executor.py
│   │   ├── broker_base.py
│   │   ├── broker_oanda.py
│   │   ├── broker_binance.py
│   │   ├── reconciler.py
│   │   └── circuit_breaker.py
│   ├── backtest/
│   │   ├── __init__.py
│   │   ├── engine.py
│   │   ├── simulator.py
│   │   ├── metrics.py
│   │   └── report.py
│   └── regime/
│       ├── __init__.py
│       └── detector.py
├── client/                           # Web UI (separate build)
│   ├── src/
│   ├── public/
│   ├── package.json
│   └── README.md
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── scenarios/
│   └── fixtures/
├── models/                           # Trained model artifacts
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── .env.example
└── README.md
```

### Appendix E: Testing Strategy

**Unit Tests:**
- Overall: ≥ 80% line coverage.
- Critical modules (risk engine, order execution, reconciliation, circuit breakers): 100% branch coverage.
- Property-based testing (Hypothesis) for risk calculations.

**Integration Tests:**
- Test complete signal pipeline per instrument.
- Test order lifecycle per broker adapter (Oanda and Binance spot).
- Test reconciliation per broker.
- Test cross-instrument risk checks (portfolio exposure limits).
- Test risk parameter override precedence.

**Scenario Tests:**
- Multi-instrument: Simultaneous signals on both instruments; verify independent execution.
- Single broker outage: Binance down while Oanda healthy; verify EUR/USD continues, BTC/USD halts.
- Regime transition: Verify system detects regime change, adjusts behavior, logs transition.
- Kill switch multi-broker: Verify all positions on all brokers closed.
- Circuit breaker cascade: Trigger per-instrument and portfolio breakers; verify correct scope.
- Risk override validation: Attempt invalid overrides; verify rejection.

**Definition of Done:**
- All tests pass.
- Coverage thresholds met.
- API endpoint has OpenAPI schema and passes schema validation in CI.
- UI component has corresponding acceptance test.
- No timezone-naive datetimes.
- Secret scan clean.

### Appendix F: Break-Even Analysis (Placeholder)

**To be completed in Stage 5 after initial backtest results.**

Estimated monthly costs:
- Server/VM: ~$0 (existing infrastructure)
- Oanda data: $0 (included with account)
- Binance data: $0 (public API)
- Oanda spread cost: ~$X per trade
- Binance spot commission: 0.10% taker per trade
- Infrastructure (electricity, internet): ~$Z/month

Required monthly return to break even per instrument: *TBD.*

### Appendix G: v2 Red-Team Findings Status

All CRITICAL, HIGH, MEDIUM, and LOW findings from SPEC.v2.md are incorporated in this specification:

| Finding | Status | Section |
|---|---|---|
| CRITICAL-1: Naïve Bayes independence | Addressed — calibration + correlation checks | §5.4 |
| CRITICAL-2: No regime-change detection | Addressed — full regime subsystem with deterministic formula | §5.7 |
| CRITICAL-3: Hybrid score weighting arbitrary | Addressed — meta-learner | §5.6 |
| CRITICAL-4: Stop-loss under-specified | Addressed — broker-side stops, per-broker specifics, spot-specific | §6.1, §7.4 |
| CRITICAL-5: No reconciliation loop | Addressed — per-broker reconciliation | §6.4 |
| CRITICAL-6: Backtest fill model optimistic | Addressed — per-instrument slippage/spread + pessimistic mode (spot) | §6.2 |
| HIGH-1: Kelly inputs circular | Addressed — rolling window + micro-sizing | §7.3 |
| HIGH-2: Signal thresholds arbitrary | Addressed — walk-forward optimization | §5.6 |
| HIGH-3: No data staleness detection | Addressed — watchdog per instrument | §4.4 |
| HIGH-4: NN overfitting guardrails | Addressed — regularization + acceptance criteria | §5.5 |
| HIGH-5: Indicator JSONB performance | Superseded — feature store model | §4.3 |
| HIGH-6: Event success ambiguity | Addressed — precise close-to-close definition | §4.6 |
| HIGH-7: Daily loss threshold inconsistency | Addressed — 2% standardized | §7.5 |
| MEDIUM-1: REST polling latency | Addressed — internal modules (monolith) | §3.1 |
| MEDIUM-2: Redis missing | Addressed — deferred, documented | §3.8 |
| MEDIUM-3: Walk-forward under-specified | Addressed — full specification | §8.1 |
| MEDIUM-4: Token selection unspecified | Addressed — MI ranking + redundancy filter | §5.3 |
| MEDIUM-5: 99.9% uptime unsubstantiated | Addressed — restated as 99.5% with measurement | §1.6, NFR-02 |
| MEDIUM-6: Candle-close sync | Addressed — complete candle confirmation | §4.1 |
| MEDIUM-7: Test coverage insufficient | Addressed — critical paths 100% branch | Appendix E |
| LOW-1: Hypertable typo | Fixed | §4.2 |
| LOW-2: Multi-timeframe deferred | Deferred to v1.1 | §2.2 |
| LOW-3: No cost analysis | Placeholder in Appendix F | Appendix F |
| LOW-4: Docker not specified | In project layout | Appendix D |
| LOW-5: UI no auth | HTTP basic auth | §11.5 |

### Appendix H: Decision Lock Resolutions

All decision locks from `SPEC_DECISIONS_LOCK.md` resolved in this document:

| ID | Decision | Resolution | Section |
|---|---|---|---|
| DL-001 | Canonical spec/docs location | `projects/newton/spec/` is canonical | Appendix D |
| DL-002 | BTC venue/scope | Spot (BTCUSDT), no futures in v1 | §1.3, §6.1 |
| DL-003 | Event catalog | Explicit per-instrument events defined | §4.6 |
| DL-004 | Client progress by stage | Thin client each stage | §15 (all stages) |
| DL-005 | Regime confidence | Deterministic formula with numeric bands | §5.7.3 |
| DL-006 | Backtest realism model | Locked spot assumptions and formulas | §6.2 |
| DL-007 | Strategy approval/rollback | Explicit governance with evidence and triggers | §13.2 |
| DL-008 | Exposure policy | Localhost/SSH-tunnel only for v1 | §11.5 |
| DL-009 | Retention/compression | Policy defined per table with backup cadence | §4.7 |
| DL-010 | Stage exit gates | Explicit checklist with CI and manual checks | §14.3 |

### Appendix I: Revision Mandate Compliance

All mandatory revisions from `SPEC_REVISIONS.md` addressed:

| Requirement | Status | Section |
|---|---|---|
| R-01: Risk management strategy-configurable | ✅ Full precedence model, validation, audit | §7.1 |
| R-02: Performance metrics strategy-configurable | ✅ Default + override + gate classification | §9.1 |
| R-03: Feature/indicator extensibility | ✅ FeatureProvider interface, add-without-refactor process | §3.6, §4.3 |
| R-04: No shorthand references to prior specs | ✅ All content fully inlined | Throughout |
| Output Rule 1: Self-contained SPEC_DRAFT.md | ✅ | This document |
| Output Rule 2: No "unchanged from v2/v3" | ✅ All sections restated completely | Throughout |
| Output Rule 3: Explicit acceptance criteria | ✅ Per requirement and per stage | §15, Appendix B |
| Content corrections: spot-only v1 | ✅ All futures references removed/replaced | Throughout |
| Content corrections: zero-code baseline | ✅ | §1.2 |
| Content corrections: server+client per stage | ✅ | §15 |

---

**End of SPEC_DRAFT.md**

*This specification is self-contained and implementation-ready. It incorporates all content from SPEC.v3.md, resolves all decision locks from SPEC_DECISIONS_LOCK.md, and implements all mandatory revisions from SPEC_REVISIONS.md. No prior spec versions need to be consulted for implementation.*
