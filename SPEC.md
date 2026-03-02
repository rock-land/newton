# Newton Trading System — Complete Specification

**Document:** `SPEC.md`  
**Date:** 2026-02-19  
**Status:** Canonical standalone specification for building Newton from scratch.  
**Decision Precedence:** Where sources conflict, DECISIONS.md overrides prior spec revisions, which override `docs/spec/SPEC_DRAFT.md`. Conflicts are resolved conservatively (the safer/simpler option wins). All conflicts are noted inline.

---

## Table of Contents

1. [Scope & Objectives](#1-scope--objectives)
2. [Goals & Non-Goals](#2-goals--non-goals)
3. [Architecture](#3-architecture)
4. [Data Model](#4-data-model)
5. [Execution Flows](#5-execution-flows)
6. [Risk Controls](#6-risk-controls)
7. [Configuration](#7-configuration)
8. [APIs & Interfaces](#8-apis--interfaces)
9. [Testing & Backtesting](#9-testing--backtesting)
10. [Observability](#10-observability)
11. [Deployment & Operations](#11-deployment--operations)
12. [Acceptance Criteria](#12-acceptance-criteria)

---

## 1. Scope & Objectives

### 1.1 System Objective

Newton is a fully automated multi-instrument trading system that generates sustainable income using a hybrid machine-learning approach to identify and execute trades across forex and cryptocurrency markets.

### 1.2 Target Markets (v1)

| Instrument | Broker / Exchange | Market Type | Contract Type | Trading Hours |
|---|---|---|---|---|
| EUR/USD | Oanda (v20 REST API) | Forex (Spot) | Spot FX | 24/5 (Sun 17:00 – Fri 17:00 ET) |
| BTC/USD | Binance (REST + WebSocket API) | Cryptocurrency (Spot) | Spot (BTCUSDT pair) | 24/7 |

**v1 is spot-only.** No futures, no leverage, no funding rates. The architecture supports derivatives in future versions without major refactoring. BTC/USD uses the Binance spot BTCUSDT pair with no leverage. Including two fundamentally different instruments forces a true multi-instrument, multi-market architecture from day one.

### 1.3 Timeframes

- **Signal generation:** 1h candles (primary). 4h confirmation deferred to v1.1.
- **Execution horizon:** Intra-day to swing (hours to days, max 48 hours).
- BTC/USD may require instrument-specific holding period tuning due to higher volatility.

### 1.4 Strategy Class

Hybrid model: event-based Bayesian analysis for interpretability and risk framework, combined with a supervised ML model (initially XGBoost; CNN-LSTM evaluated conditionally) for pattern recognition. Each instrument uses a **strategy configuration tailored to its behavior** while sharing common infrastructure. Signal generation is delivered through a **swappable signal generator architecture** (see §5.2).

### 1.5 Success Criteria (Measurable)

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

BTC/USD success criteria may require adjustment (e.g., wider drawdown tolerance) given higher baseline volatility. This is evaluated during backtesting and explicitly decided before paper trading begins. Any adjustments must be configured via per-strategy overrides (see §7.4).

### 1.6 Key Assumptions

| ID | Assumption |
|---|---|
| A1 | Success targets are achievable for medium-frequency strategies on these instruments. If paper trading shows Sharpe < 0.5, revisit strategy hypothesis rather than tuning. |
| A2 | Hybrid Bayesian + ML model is the desired approach. |
| A3 | Multi-instrument from v1: EUR/USD (Oanda spot) + BTC/USD (Binance spot). |
| A4 | Python 3.11+ is the implementation language. |
| A5 | RTX 5060ti 16GB available on host for GPU-accelerated training. |
| A6 | Developer is solo; system must be maintainable by one person. |
| A7 | Each instrument may exhibit different market microstructure requiring per-instrument strategy tuning. |
| A8 | v1 is spot-only. No futures, leverage, or margin trading. |

---

## 2. Goals & Non-Goals

### 2.1 In Scope (v1)

- Data ingestion from **Oanda** (EUR/USD spot) and **Binance** (BTC/USD spot, BTCUSDT pair) across 1m, 5m, 1h, 4h, 1d timeframes.
- Historical data backfill (minimum 3 years: 2023-01-01 to present) and validation for both instruments.
- Extensible feature/indicator computation: initial set includes RSI(14), MACD(12,26,9), Bollinger Bands(20,2.0), OBV, ATR(14). New indicators addable via the FeatureProvider interface without schema changes.
- **Prefer mature, well-tested industry-standard libraries** (e.g., TA-Lib) over bespoke implementations when available. Custom implementations require explicit justification and parity tests.
- Bayesian inference engine for generating trade signals based on tokenized indicator events.
- Supervised ML model (XGBoost as default; CNN-LSTM as optional alternative) for complementary probability scoring.
- Stacking meta-learner to combine Bayesian and ML signals into a calibrated probability.
- **Swappable signal generator architecture** enabling independent development, testing, and routing of different signal generation approaches per instrument.
- Backtesting engine with walk-forward validation and purged K-fold cross-validation.
- Paper trading module via Oanda practice account (EUR/USD) and Binance testnet (BTC/USD spot).
- Risk management: broker-side stops, Kelly-based position sizing, drawdown circuit breakers — all configurable per strategy with global defaults.
- Performance metrics: configurable per strategy with global defaults.
- Operational monitoring: structured logging, Prometheus metrics, Telegram alerts.
- Position reconciliation loop (per-broker).
- Regime detection subsystem with deterministic classification and strategy-aware behavior.
- Instrument-specific strategy configurations sharing common infrastructure.
- Client application (web UI styled with **Tailwind CSS, dark mode default**) with strict separation from server, progressing each stage.
- Developer documentation, user/operator documentation, and in-app help.

### 2.2 Explicitly Out of Scope (v1)

- HFT (sub-second).
- Futures, leverage, margin trading, funding rates — v1 is spot-only.
- Instruments beyond EUR/USD and BTC/USD (v2+).
- Non-technical data sources (sentiment, news, order book) — architecture supports future addition via FeatureProvider interface.
- Short selling (v1 is long-only; SELL signal closes existing longs).
- Multi-timeframe confirmation logic (deferred to v1.1).
- Online/incremental learning (v2).
- Dynamic strategy generation beyond static configs (v1 uses static configs; see §5.7 for roadmap).
- Redis caching (deferred to v1.1; current throughput doesn't justify it).

---

## 3. Architecture

### 3.1 High-Level Architecture

```
+==============================================================+
|                    Newton Server (Single Process)              |
|  +------------------+  +-------------------+  +-------------+ |
|  |  Data Module     |  | Signal Generator  |  | Trading     | |
|  |  data/           |  | Registry          |  | Module      | |
|  |  - fetcher_oanda |->| - bayesian_v1     |->| trading/    | |
|  |  - fetcher_      |  | - ml_v1           |  | - signal    | |
|  |    binance       |  | - ensemble_v1     |  | - risk      | |
|  |  - indicators    |  | - [custom_n]      |  | - executor  | |
|  |  - pipeline      |  |                   |  |   _oanda    | |
|  |  - feature_store |  | (config-driven    |  |   _binance  | |
|  |  - verifier      |  |  per-instrument   |  | - reconciler| |
|  |  - db            |  |  routing)          |  |             | |
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
5. **Spot-first, derivatives-ready** — v1 uses spot execution only. Broker adapter interface and order model designed so adding futures/margin requires implementing new adapter methods, not restructuring the core.
6. **Swappable signal generation** — signal generators are pluggable modules registered at boot time, routed per-instrument via configuration. The data and trading layers are decoupled from signal generation internals.

### 3.2 Client/Server Boundary

**Rules:**

1. The server exposes a **versioned REST API** (prefix: `/api/v1/`) and optional WebSocket channels as the sole interface for all clients.
2. The client **never** accesses the database, file system, or model artifacts directly.
3. API contracts (OpenAPI 3.1 schema) are the **source of truth** for client/server interaction.
4. The client validates server behavior: all API responses include checksums, timestamps, and status codes that the client can verify and surface discrepancies.
5. The UI is **replaceable**: any conforming client can substitute the default web UI without server modification.

**API Versioning Strategy:**

- URL-path versioning: `/api/v1/`, `/api/v2/`, etc.
- Breaking changes require a version bump. Non-breaking additions (new optional fields) are allowed within a version.
- Deprecated endpoints marked with `Sunset` header and removed no sooner than 2 minor releases later.
- OpenAPI schema auto-generated from server code and published as a build artifact.

**Client-Side Health Panel:**

- API connectivity, response latency (p50/p95), schema validation errors, data freshness.
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

### 3.4 Instrument Configuration

Each instrument has an independent configuration specifying behavior across all system layers:

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
| Signal generator failure | Error in generate() | Fall back to `routing.<instrument>.fallback` generator. If fallback fails, emit NEUTRAL with confidence=0. | Log fallback event. Alert. |

### 3.6 Extension Points for Future Data Sources

The architecture allows non-technical data (sentiment, news, order book) to be added in future versions without major refactor.

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
- `TechnicalIndicatorProvider` — RSI, MACD, BB, OBV, ATR, and any additional technical indicators.

**Future providers (interface exists, not implemented in v1):**
- `SentimentProvider`, `OrderBookProvider`, `NewsProvider`.

**Adding a new indicator or feature provider:**

1. Implement the `FeatureProvider` protocol (or for technical indicators, extend `TechnicalIndicatorProvider`).
2. Register the provider in `config/feature_providers.json`.
3. The provider's features automatically flow into the feature store with its declared namespace.
4. The tokenizer and ML feature engineering stages query all registered providers.
5. No changes to core pipeline code, database schema, or existing providers are required.

**Testing requirements for new indicators:**
- Unit tests verifying calculation accuracy against a reference implementation (TA-Lib or equivalent).
- Integration test confirming features are stored and retrievable from the feature store.
- Backtest run demonstrating no regression to existing strategy performance.

---

## 4. Data Model

### 4.1 Data Sources

| Source | Instrument | API | Candle Confirmation | Auth |
|---|---|---|---|---|
| Oanda v20 | EUR/USD | REST + WebSocket | `complete: true` flag | API key (env var) |
| Binance | BTC/USDT (spot) | REST + WebSocket | Kline close event | API key + secret (env vars) |

**Fetch Schedule:** Poll every 10 seconds after expected candle close; accept only confirmed/complete candles.

**Binance-Specific Considerations (Spot):**

- BTC/USDT trades 24/7; no market close gaps.
- Volume normalized to quote currency (USDT).
- Rate limiter: 1200 requests/min weight. Track weight per request.
- Use Binance spot kline/candlestick endpoints for historical and real-time data.

### 4.2 Database Schema (TimescaleDB)

```sql
-- OHLCV data (hypertable partitioned by time)
CREATE TABLE ohlcv (
    time        TIMESTAMPTZ NOT NULL,
    instrument  TEXT NOT NULL,
    interval    TEXT NOT NULL,
    open        DOUBLE PRECISION NOT NULL,
    high        DOUBLE PRECISION NOT NULL,
    low         DOUBLE PRECISION NOT NULL,
    close       DOUBLE PRECISION NOT NULL,
    volume      DOUBLE PRECISION NOT NULL,
    spread_avg  DOUBLE PRECISION,
    verified    BOOLEAN DEFAULT FALSE,
    source      TEXT NOT NULL,
    PRIMARY KEY (time, instrument, interval)
);
SELECT create_hypertable('ohlcv', 'time');

-- Feature store (long-format, extensible)
CREATE TABLE features (
    time        TIMESTAMPTZ NOT NULL,
    instrument  TEXT NOT NULL,
    interval    TEXT NOT NULL,
    namespace   TEXT NOT NULL,
    feature_key TEXT NOT NULL,
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
    params          JSONB,
    provider        TEXT NOT NULL,
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
    broker              TEXT NOT NULL,
    direction           TEXT NOT NULL CHECK (direction IN ('BUY', 'SELL')),
    signal_score        DOUBLE PRECISION NOT NULL,
    signal_type         TEXT NOT NULL,
    signal_generator_id TEXT,
    regime_label        TEXT,
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

-- Regime log
CREATE TABLE regime_log (
    id              BIGSERIAL PRIMARY KEY,
    time            TIMESTAMPTZ NOT NULL,
    instrument      TEXT NOT NULL,
    regime_label    TEXT NOT NULL,
    confidence      DOUBLE PRECISION,
    vol_30d         DOUBLE PRECISION,
    adx_14          DOUBLE PRECISION,
    trigger         TEXT NOT NULL,
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
    created_by      TEXT NOT NULL,
    approved        BOOLEAN DEFAULT FALSE,
    approved_at     TIMESTAMPTZ,
    approval_evidence JSONB,
    notes           TEXT,
    UNIQUE (instrument, version)
);

-- Spec deviation log
CREATE TABLE spec_deviations (
    id              BIGSERIAL PRIMARY KEY,
    deviation_id    TEXT UNIQUE NOT NULL,
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
    section         TEXT NOT NULL,
    instrument      TEXT,
    old_value       JSONB,
    new_value       JSONB NOT NULL,
    reason          TEXT
);
```

### 4.3 Feature Store Approach

**Problem:** Column naming like `rsi_14` is rigid. Adding new indicators requires schema migration.

**Selected approach:** Long-format feature store with performance mitigations.

**Rationale:**
- Adding new indicators requires zero schema changes.
- Self-describing via `feature_metadata` table.
- Namespace isolation (`technical`, `sentiment`, `orderbook`) prevents collisions.
- Multi-instrument native.

**Feature Key Format:**
```
{indicator}:{param1}={value1},{param2}={value2}:{component}
```

Examples:
- `rsi:period=14`
- `macd:fast=12,slow=26,signal=9:line`
- `bb:period=20,std=2.0:upper`
- `obv:`
- `atr:period=14`

**Performance Mitigations:**
1. Composite index on `(instrument, interval, namespace, feature_key, time DESC)`.
2. Materialized views for hot query patterns.
3. Batch insert using `COPY` or `execute_values`.
4. TimescaleDB compression on older partitions (> 30 days).
5. **Benchmark requirement:** < 500ms for a full feature vector retrieval (60-period lookback × 5 indicators).

### 4.4 Data Quality Checks

| Check | Frequency | Action on Failure |
|---|---|---|
| Gap detection (missing candles) | Every pipeline run, per instrument | Auto-backfill; flag `verified = false` until filled |
| Duplicate check | Every pipeline run | Deduplicate (keep latest) |
| OHLC logic (high ≥ open, close, low; low ≤ all) | Every pipeline run | Flag row as suspect; exclude from signal generation |
| Stale data (no new candle within 2× expected interval) | Continuous (watchdog), per instrument | Alert; halt new signals for that instrument |
| Outlier detection (candle range > 10× ATR(14)) | Every pipeline run | Flag; do not auto-exclude but alert for manual review |

### 4.5 Timezone Policy

- All timestamps stored and processed in UTC.
- No timezone-naive `datetime` objects anywhere. Enforced via linting rule.

### 4.6 Event Definition

An event `{INSTRUMENT}_UP_X_PCT_N_PERIODS` is defined as:

> At candle T (signal candle), the event is TRUE if:
> `(close[T + N] - close[T]) / close[T] >= X / 100`

This is a **close-to-close forward return** measurement. NOT a high-watermark measurement.

**v1 Event Catalog:**

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

**Acceptance criteria:** Given a known price series, event labels must match hand-calculated expectations with zero discrepancy. If an event has fewer than `min_occurrences` in the 3-year dataset, alert and log.

### 4.7 Data Retention and Compression

| Table | Retention | Compression |
|---|---|---|
| `ohlcv` | Indefinite | TimescaleDB compression after 90 days |
| `features` | Indefinite | TimescaleDB compression after 30 days |
| `events` | Indefinite | TimescaleDB compression after 90 days |
| `tokens` | Indefinite | TimescaleDB compression after 90 days |
| `trades` | Indefinite | None (small table) |
| `reconciliation_log` | 1 year | Archive older |
| `regime_log` | Indefinite | None |
| `strategy_versions` | Indefinite | None |
| `config_changes` | Indefinite | None |
| `spec_deviations` | Indefinite | None |

**Backup Policy:**
- Daily automated backup (pg_dump) to local storage + weekly offsite copy.
- Keep daily backups for 30 days; weekly backups for 1 year.
- Monthly restore-test to a temporary database, verifying row counts and data integrity.

---

## 5. Execution Flows

### 5.1 Per-Instrument Strategy Configuration

Each instrument has a strategy configuration file:

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

### 5.2 Swappable Signal Generator Architecture

Signal generation is delivered through a pluggable module system.

#### 5.2.1 Signal Generator Interface

Every signal generator must implement:

```python
@dataclass
class Signal:
    """Output from any signal generator."""
    instrument: str
    action: Literal["STRONG_BUY", "BUY", "SELL", "NEUTRAL"]
    probability: float        # calibrated probability [0.0, 1.0]
    confidence: float         # confidence [0.0, 1.0]
    component_scores: dict[str, float]
    metadata: dict[str, Any]
    generated_at: datetime
    generator_id: str

@dataclass
class FeatureSnapshot:
    """Typed feature payload passed into signal generators."""
    instrument: str
    interval: str
    time: datetime
    values: dict[str, float]
    metadata: dict[str, Any]

@runtime_checkable
class SignalGenerator(Protocol):
    """Abstract interface for all signal generators."""

    @property
    def id(self) -> str: ...

    @property
    def version(self) -> str: ...

    def generate(self, instrument: str, features: FeatureSnapshot,
                 config: GeneratorConfig) -> Signal: ...

    def generate_batch(self, instrument: str,
                       historical_features: list[FeatureSnapshot],
                       config: GeneratorConfig) -> list[tuple[datetime, Signal]]: ...

    def validate_config(self, config: dict[str, Any]) -> bool: ...
```

#### 5.2.2 Generator Registry

A central registry maps generator IDs to implementations.

**Safety requirement:** Registry mutation is allowed only at process startup. Runtime writes are disallowed (read-only after boot).

```python
class GeneratorRegistry:
    """Central registry for signal generators (boot-time write, runtime read-only)."""

    @classmethod
    def register(cls, generator_id: str, generator_class: type[SignalGenerator]): ...

    @classmethod
    def get(cls, generator_id: str) -> type[SignalGenerator]: ...

    @classmethod
    def list_generators(cls) -> list[str]: ...

    @classmethod
    def create_instance(cls, generator_id: str,
                        config: GeneratorConfig) -> SignalGenerator: ...
```

#### 5.2.3 Configuration-Driven Routing

Signal generator selection is per-instrument configurable:

```json
{
  "signals": {
    "generators": {
      "bayesian_v1": {
        "enabled": true,
        "parameters": { "event_threshold": 0.7, "calibration_window": 100 }
      },
      "ml_v1": {
        "enabled": false,
        "parameters": { "model_path": "./models/ml_v1.xgb", "threshold": 0.65 }
      },
      "ensemble_v1": {
        "enabled": true,
        "parameters": { "components": ["bayesian_v1", "ml_v1"], "weights": [0.6, 0.4] }
      }
    },
    "routing": {
      "EUR_USD": { "primary": "bayesian_v1", "fallback": "ensemble_v1" },
      "BTC_USD": { "primary": "ensemble_v1", "fallback": "bayesian_v1" }
    }
  }
}
```

**Routing and Fallback Semantics:**

1. Resolve `routing.<instrument>.primary`.
2. If primary is disabled, missing, or raises recoverable error, attempt `routing.<instrument>.fallback`.
3. If fallback also fails, emit `NEUTRAL` signal with `confidence=0` and structured `metadata.error`; halt execution decisions for that cycle.
4. Every fallback event logged as `signal_generator_fallback` with instrument, primary, fallback, and reason.

**Config Governance:**
- No unattended activation of new generator routes.
- All config changes logged with actor, timestamp, before/after payload.
- Dry-run validation endpoint before applying changes.
- Immediate rollback to previous known-good config snapshot supported.

#### 5.2.4 Historical Signal Generation Contract

`generate_batch()` is an input producer for backtesting, NOT a backtest engine itself. Requirements:
1. **Deterministic** — same input produces same output.
2. **No look-ahead** — can only use features available at each timestamp.
3. **Timestamp tracking** — each signal tagged with generation time.
4. Backtest performance simulation remains in the dedicated Backtest engine (§9).

#### 5.2.5 Built-in Generators

| Generator | Type | Inputs | Stage |
|---|---|---|---|
| `bayesian_v1` | Event-based Bayesian analysis | Tokenized indicator events | Stage 2 |
| `ml_v1` | Supervised ML (XGBoost) | Raw indicator features | Stage 3 |
| `ensemble_v1` | Meta-learner combination | Outputs from bayesian_v1 + ml_v1 | Stage 3 |

Custom generators can be added by implementing `SignalGenerator`, registering with the registry, and adding a config entry.

### 5.3 Tokenization

**Format:** `{INSTRUMENT}_{PREFIX}_{PARAM}_{DATAPOINT}_{TYPE}_{VALUE}`

Examples:
- `EURUSD_RSI14_CL_BLW_30` — EUR/USD RSI(14) on Close is Below 30
- `BTCUSD_MACD12269_CL_XABV_0` — BTC/USD MACD(12,26,9) crosses Above 0

Token vocabularies are defined per instrument in `config/classifications/{INSTRUMENT}_classifications.json`.

### 5.4 Token Selection

1. For each event type (per instrument), calculate mutual information `I(Token; Event)` for all tokens.
2. Rank tokens by mutual information.
3. Filter redundant tokens: if Jaccard similarity > 0.85, keep only the higher-MI token.
4. Select top N tokens (configurable per instrument, default N=20, max N=50).
5. Log selected token set, MI scores, and correlation matrix.

### 5.5 Bayesian Engine

**Method:** Naïve Bayes with calibration.

**Process:**
1. Calculate prior: `P(Event) = count(Event=TRUE) / count(all)`.
2. Calculate likelihood with Laplace smoothing (alpha=1, configurable per strategy).
3. Calculate posterior using log-odds form (numerically stable):
   ```
   log_odds = log(P(Event) / P(~Event))
   for each token_i in active_tokens:
       log_odds += log(P(Token_i | Event) / P(Token_i | ~Event))
   posterior = sigmoid(log_odds)
   ```
4. **Calibration:** Apply isotonic regression fitted on out-of-fold predictions.
5. **Cap:** Maximum posterior capped at 0.90 (configurable per instrument strategy).

**Known Limitation:** Naïve Bayes assumes token independence, which is violated. Calibration partially mitigates this.

**Inter-token Correlation Check:** At training time, compute pairwise phi coefficients. If |phi| > 0.7 between any pair, log warning. If > 3 pairs exceed threshold, alert and recommend reducing token set.

### 5.6 ML Model

**Default: XGBoost (v1).**

**Input Features:** Last N periods (configurable, default 24) of: OHLCV returns (not raw prices), indicator features from feature store, token presence flags.

**Training:** Walk-forward: train on rolling 2-year window, validate on next 6 months. Hyperparameter search via Optuna. Early stopping on validation loss.

**Acceptance Criteria:** Out-of-sample AUC-ROC > 0.55 per instrument. If AUC < 0.55: disable ML component for that instrument; fall back to Bayesian-only mode.

**Optional: CNN-LSTM** — evaluated if XGBoost fails to meet AUC threshold. Requires GPU (RTX 5060ti). Regularization: dropout (0.2-0.5), early stopping, weight decay. Max parameter budget: 1M parameters.

**Library preference:** Use mature, well-tested industry-standard libraries (e.g., TA-Lib for indicator computation) over bespoke implementations when available. Custom implementations require explicit justification and maintained parity tests in CI.

### 5.7 Meta-Learner (Signal Combination)

**Method:** Logistic regression stacking.

**Inputs:** Bayesian posterior, ML probability, current regime confidence. Trained on out-of-fold predictions from walk-forward.

**Signal Interpretation:**

| Combined Probability | Signal | Action |
|---|---|---|
| > threshold_strong_buy (per strategy) | STRONG_BUY | Open long position (if no existing position) |
| > threshold_buy (per strategy) | BUY | Open long position (smaller size) |
| < threshold_sell (per strategy) | SELL | Close any open long position |
| else | NEUTRAL | No action |

Thresholds are per-instrument, defined in strategy configuration, derived from walk-forward backtest.

### 5.8 Regime Detection Subsystem

#### 5.8.1 Purpose

Detect when market conditions shift, enabling strategy adaptation or protective halting. Operates independently per instrument.

#### 5.8.2 Regime Model

**Inputs (per instrument):**
1. **vol_30d:** Rolling 30-day annualized realized volatility (close-to-close returns, σ × √252 for forex, σ × √365 for crypto).
2. **ADX_14:** Rolling 14-day Average Directional Index.
3. **Hurst exponent:** Deferred to v1.1.

**Regime Classification:**

| Regime Label | Condition |
|---|---|
| `LOW_VOL_TRENDING` | vol_30d < vol_median AND ADX_14 > 25 |
| `LOW_VOL_RANGING` | vol_30d < vol_median AND ADX_14 ≤ 25 |
| `HIGH_VOL_TRENDING` | vol_30d ≥ vol_median AND ADX_14 > 25 |
| `HIGH_VOL_RANGING` | vol_30d ≥ vol_median AND ADX_14 ≤ 25 |

**vol_median** is calculated over a 2-year rolling window, recalculated monthly (first day of each month at 00:00 UTC).

#### 5.8.3 Regime Confidence — Deterministic Formula

```
d_vol = |vol_30d - vol_median| / vol_median
d_adx = |ADX_14 - 25| / 25
d_vol_clamped = min(d_vol, 1.0)
d_adx_clamped = min(d_adx, 1.0)
confidence = sqrt(d_vol_clamped × d_adx_clamped)
```

**Confidence Bands:**

| Band | Range | Behavior |
|---|---|---|
| HIGH | ≥ 0.5 | Normal trading |
| MEDIUM | 0.2 – 0.5 | Normal trading; log regime as "soft" |
| LOW | < 0.2 | Reduce position size by 50%; widen stops by 50% |

**Recompute Cadence:** Every new 1h candle close, per instrument.

#### 5.8.4 Regime-Aware Behavior

| State | System Behavior |
|---|---|
| High confidence, any regime | Normal trading with current strategy config |
| Medium confidence | Normal trading; regime logged as "soft" |
| Low confidence (transitioning) | Reduce position size by 50%; widen stops by 50% |
| Model degradation (rolling 30-trade Sharpe < 0) | Halt new entries for that instrument |
| Manual override active | Use operator-specified regime until override cleared |

#### 5.8.5 Manual Override

- API endpoint: `PUT /api/v1/regime/{instrument}/override`
- Body includes: `regime_label`, `reason`, `expires_at`.
- Auto-expires or manually cleared via `DELETE`.
- All overrides logged to `regime_log` with `trigger = 'manual_override'`.
- Automatic regime detection continues to run and log but does not control behavior during override.

#### 5.8.6 Regime in Reporting

- Every trade record includes `regime_label` at signal time.
- Reports include: performance breakdown by regime, regime timeline chart on equity curve, regime duration statistics.
- Charts display regime as colored background bands.

### 5.9 Order Routing

- All orders are **market orders** sent via the instrument's broker adapter.
- v1 is **spot-only**.
- Every order includes broker-side stop-loss:
  - **Oanda:** `stopLossOnFill` parameter on the order.
  - **Binance Spot:** OCO order placed immediately after entry fill. If OCO placement fails: close position immediately and alert.
- Every order has a unique `client_order_id`: `NEWTON-{instrument}-{timestamp_ms}`.

**Binance Spot-Specific:**
- Minimum notional and lot size rules validated pre-submission.
- Commission deducted from received asset; account for this in position sizing.

### 5.10 Slippage and Spread Modeling (Backtest)

| Parameter | EUR/USD (Oanda Spot) | BTC/USDT (Binance Spot) |
|---|---|---|
| Default spread | 1.5 pips | 0.05% of price |
| Default slippage | 1.0 pip | 0.02% of price |
| Pessimistic multiplier | 2× (spread + slippage) | 2× |
| Commission | Spread-inclusive | 0.10% per trade (taker) |
| Funding rate | N/A (spot) | N/A (spot) |
| Latency assumption | 100ms order-to-fill | 200ms order-to-fill |
| Fill model | Full fill at modeled price | Full fill at modeled price |
| Partial fill / reject | Not simulated in v1 | Not simulated in v1 |

**Fill price (backtest):** `open[T+1] + slippage + spread/2` for buys; `open[T+1] - slippage - spread/2` for sells.

### 5.11 Retry and Idempotency

- Orders submitted with `client_order_id` for idempotency.
- Retry up to 3× on 5xx/timeout errors.
- Before retry, check for existing order with same `client_order_id`.
- No retry on 4xx (log and alert).
- All retry attempts logged.

### 5.12 Reconciliation Loop

**Frequency:** Every 60 seconds, per broker.

**Process:**
1. Fetch all open positions from broker API.
2. Compare with internal `trades` table (status = 'OPEN').
3. Classify:

| State | Meaning | Action |
|---|---|---|
| MATCH | Agreement | Log OK |
| SYSTEM_EXTRA | System thinks open, broker does not | Alert (CRITICAL). Mark as CLOSED with `exit_reason = 'RECONCILIATION'`. |
| BROKER_EXTRA | Broker has position system doesn't know about | Alert (CRITICAL). Halt entries for that instrument. Create internal record. Require manual review. |

4. Log to `reconciliation_log`.
5. Expose as Prometheus metric per broker.

### 5.13 Dynamic Strategy Generation Roadmap

| Stage | Capability | Version |
|---|---|---|
| 1 | Static configs — manually edited JSON, validated via backtest | v1 |
| 2 | Assisted parameter search — offline sweep, results presented to operator | v1.1+ |
| 3 | Server-side generation — automated pipeline with approval gate | v2+ |

**Governance Gates (all stages):** Proposal → Backtest validation → Operator review → Explicit approval → Activation → Post-activation monitoring.

---

## 6. Risk Controls

### 6.1 Configuration Architecture

All risk parameters are **configurable per strategy**, defaulting to global spec defaults.

**Configuration Precedence (highest to lowest):**
1. **Instrument override** (in `config/instruments/{INSTRUMENT}.json` → `risk_overrides`)
2. **Strategy override** (in `config/strategies/{INSTRUMENT}_strategy.json` → `risk_overrides`)
3. **Global default** (in `config/risk.json` → `defaults`)

When multiple levels specify the same parameter, highest-precedence non-null value wins.

**Validation Constraints (preventing unsafe overrides):**

| Parameter | Minimum | Maximum |
|---|---|---|
| `hard_stop_pct` | 0.5% | 10% |
| `max_risk_per_trade_pct` | 0.1% | 5% |
| `max_position_pct` | 0.5% | 20% |
| `daily_loss_limit_pct` | 0.5% | 5% |
| `max_drawdown_pct` | 5% | 30% |
| `kelly_fraction` | 0.10 | 0.50 |
| `time_stop_hours` | 1 | 168 (7 days) |

Any override outside these bounds is rejected at load time. The system will not start with invalid risk configuration.

**Audit Logging:** Every change to risk parameters is logged to `config_changes` table with timestamp, who, section, old value, new value, and reason.

### 6.2 Global Risk Defaults

```json
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

> **Resolved conflict (daily loss limit):** Source documents listed both 2% and 3%. This spec uses **2%** (more conservative, appropriate for unproven system).

### 6.3 Pre-Trade Checks

| Check | Rule | On Failure |
|---|---|---|
| Position limit | Max 1 open position per instrument | Reject |
| Portfolio exposure | Max `portfolio.max_total_exposure_pct` across all instruments | Reject |
| Position sizing | Kelly ¼, minimum of: Kelly result, max_position_pct, max_risk_per_trade_pct | Use smallest |
| Circuit breaker | Check daily loss and drawdown flags | Reject |
| Data freshness | Last verified candle < 2× interval ago | Reject |
| Model freshness | Days since last retrain < 30 | Alert (warning, not blocking) |
| Regime confidence | LOW (< 0.2) | Reduce position size by 50% |

**Kelly Criterion:**
- Rolling window of last `kelly_window` trades (default 60) per instrument.
- First `kelly_min_trades` trades (default 30): fixed `micro_size_pct` (default 0.5% of equity).
- Hard cap: never risk > `max_risk_per_trade_pct`, never exceed `max_position_pct`.
- Formula: `f* = kelly_fraction × (p × b - q) / b`

### 6.4 In-Trade Controls

| Control | Specification |
|---|---|
| Hard stop-loss | `hard_stop_pct` below entry (default -2%, BTC -3%). Broker-side at entry. |
| Trailing stop activation | Profit reaches `trailing_activation_pct` (+1%) → move stop to entry (breakeven). |
| Trailing stop advance | Profit reaches `trailing_breakeven_pct` (+2%) → move stop to +1% above entry. |
| Time stop | Open > `time_stop_hours` (default 48h) → market close. |
| Volatility check | ATR(14) > `volatility_threshold_multiplier` × 30-day avg → reduce size by 50%, widen stop. |

> **Resolved conflict (trailing stop):** Sources disagreed on trail parameters. This spec uses: activation at +1%, breakeven at +2% (more conservative version).

**Stop Update Frequency:** Every new candle close AND on WebSocket tick updates for positions with profit > 0.5%.

**Gap Risk Mitigation:** Size assuming worst-case gap of `gap_risk_multiplier` × stop distance (default 2×).

### 6.5 Circuit Breakers

| Breaker | Trigger | Scope | Action | Reset |
|---|---|---|---|---|
| Daily loss | Equity drops `daily_loss_limit_pct` from day-open (default 2%) | Per instrument + portfolio | Close positions; halt entries | Automatic at 00:00 UTC |
| Max drawdown | Equity drops `max_drawdown_pct` from ATH (default 20%) | Per instrument + portfolio | Close all; halt all | Manual intervention |
| Consecutive losses | `consecutive_loss_halt` losers (default 5) | Per instrument | Halt entries for `consecutive_loss_halt_hours` (24h) | Automatic after timeout |
| Model degradation | Rolling 30-trade Sharpe < 0 | Per instrument | Halt entries | When Sharpe ≥ 0 |
| Kill switch | Manual activation | System-wide | Close ALL positions on ALL brokers | Manual reset |

**Kill Switch:**
- Available via UI button AND `POST /api/v1/kill`.
- On activation: close all positions, cancel all pending, set `kill_switch_active = true`.
- Reset: manual only via `DELETE /api/v1/kill` (requires confirmation).
- Activation and reset logged to `config_changes`.

---

## 7. Configuration

### 7.1 System Configuration

```json
// config/system.json
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

### 7.2 Feature Provider Configuration

```json
// config/feature_providers.json
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

### 7.3 Secrets

All secrets loaded from environment variables. Never in code or config files. Enforced via CI secret scan.

| Secret | Env Var | Permissions |
|---|---|---|
| Oanda API key | `OANDA_API_KEY` | Trade-only |
| Binance API key | `BINANCE_API_KEY` | Spot-trade-only (no withdrawal/transfer/futures) |
| Binance API secret | `BINANCE_API_SECRET` | (same) |
| UI username | `NEWTON_UI_USER` | — |
| UI password | `NEWTON_UI_PASS` | — |

**Binance IP whitelist:** API keys restricted to server IP.

### 7.4 Per-Strategy Override Schema

The `risk_overrides` and `performance_overrides` objects in strategy configuration accept any key from global defaults. Only specified keys override; unspecified fall back.

```json
{
  "risk_overrides": {
    "hard_stop_pct": 0.03,
    "high_volatility_stop_pct": 0.05,
    "max_drawdown_pct": 0.25,
    "daily_loss_limit_pct": 0.03
  },
  "performance_overrides": {
    "max_drawdown_pct": 0.25,
    "sharpe_ratio_min": 0.6,
    "win_rate_min": 0.40
  }
}
```

---

## 8. APIs & Interfaces

### 8.1 REST API (Versioned: `/api/v1/`)

**Data Endpoints:**
- `GET /api/v1/health` — system health (DB, brokers, instruments, kill switch status)
- `GET /api/v1/data/ohlcv/{instrument}` — OHLCV retrieval
- `GET /api/v1/data/features/{instrument}` — feature store retrieval

**Signal Endpoints:**
- `GET /api/v1/signals/generators` — list all registered signal generators and their status
- `GET /api/v1/signals/{instrument}` — current signal with score, confidence, regime, generator metadata. Optional `?generator=` parameter for override.
- `POST /api/v1/signals/config` — update signal generator configuration (governance-controlled)

**Trading Endpoints:**
- `GET /api/v1/trades` — trade history
- `POST /api/v1/kill` — activate kill switch
- `DELETE /api/v1/kill` — deactivate kill switch (requires confirmation)

**Regime Endpoints:**
- `GET /api/v1/regime/{instrument}` — current regime
- `PUT /api/v1/regime/{instrument}/override` — set manual override
- `DELETE /api/v1/regime/{instrument}/override` — clear override

**Strategy Endpoints:**
- `GET /api/v1/strategy/{instrument}` — current strategy
- `GET /api/v1/strategy/{instrument}/versions` — version history
- `PUT /api/v1/strategy/{instrument}/activate` — activate a version

**Config Endpoints:**
- `GET /api/v1/config/risk` — current risk config
- `PUT /api/v1/config/risk` — update risk config (with validation)

**Backtest Endpoints:**
- `POST /api/v1/backtest` — run backtest
- `GET /api/v1/backtest/{id}` — get results

**Documentation:**
- `GET /api/v1/docs` — OpenAPI auto-generated docs
- `GET /api/v1/docs/{section}` — in-app help content (markdown)

### 8.2 WebSocket Channels

- Portfolio equity curve (real-time updates)
- Position P&L updates
- Signal events
- Alert stream

### 8.3 Client UI

**Framework:** React (or equivalent SPA) with **Tailwind CSS, dark mode default**. Communicates exclusively via REST API and WebSocket.

**Authentication:** HTTP basic auth (env var credentials). Accessible on localhost or via SSH tunnel only for v1. If external access needed in future, upgrade to OIDC/JWT or VPN.

**Progressive delivery:** Each implementation stage includes thin client milestones.

**Core Screens:**

1. **Dashboard:** Portfolio equity curve, per-instrument status (position, P&L, regime, circuit breakers), system health, recent alerts, kill switch button.
2. **Strategy Management:** CRUD for strategy configs, version history, comparison, approval workflow.
3. **Backtest Interface:** Run backtests (instrument, strategy, date range, pessimistic mode), equity curve, trade list, metrics, calibration plot, regime overlay, trade overlay on charts, backtest comparison.
4. **Live Trading Monitor:** Open positions with real-time P&L, signal log, trade history, reconciliation status, manual position close, pause/resume per instrument.
5. **System Configuration:** Risk parameters, performance thresholds, alert preferences, regime overrides, trading mode (paper/live).
6. **Reports:** Daily/weekly/monthly, exportable as PDF.
7. **In-App Help:** Contextual help per section, stored as markdown served via API.

**Not configurable via UI (require config file edit):** DB connection strings, API keys, core architecture settings, validation constraint bounds.

---

## 9. Testing & Backtesting

### 9.1 Backtesting Methodology

**Primary: Walk-Forward Testing.**
- Minimum train window: 2 years.
- Test window: 6 months.
- Step: 6 months.
- Embargo: 48 hours.
- Minimum 4 folds.
- Runs independently per instrument.

**Secondary: Purged K-Fold.**
- K = 5, with 48-hour purge zones.
- Robustness check; not primary validation.
- Runs independently per instrument.

### 9.2 Simulation Model

Per-instrument fill model:

- **EUR/USD:** Fill at `open[T+1] ± (1.0 pip slippage + 0.75 pip half-spread)`. No separate commission.
- **BTC/USDT:** Fill at `open[T+1] ± (0.02% slippage + 0.025% half-spread)`. Plus 0.10% taker commission.
- **Pessimistic mode:** 2× multiplier on slippage and spread. Commission unchanged.

No partial fills, no rejects in v1.

### 9.3 Bias Controls

| Bias | Mitigation |
|---|---|
| Look-ahead | Walk-forward with 48h embargo; events use only past data |
| Overfitting | Walk-forward + purged K-fold; minimum trade count per fold |
| Survivorship | Flagged for BTC/USDT |
| Selection | Fixed event catalog and token methodology |
| Data snooping | Hyperparameter search within training windows only |

### 9.4 Regime-Aware Backtest Reporting

- Per-regime performance breakdown (Sharpe, PF, win rate per regime per instrument).
- Regime transition timeline overlaid on equity curve.
- Regime-adjusted metrics weighted by time-in-regime.
- Low-sample flagging: if regime has < 20 trades in any fold, its performance estimate flagged and excluded from go/no-go.

### 9.5 Performance Metrics

**Default Metric Thresholds (global):**

| Metric | Default Bar | Gate Type |
|---|---|---|
| Sharpe Ratio | > 0.8 | Hard (go/no-go) |
| Profit Factor | > 1.3 | Hard (go/no-go) |
| Max Drawdown | < 15% | Hard (stop if breached) |
| Expectancy | > 0 | Hard (must be positive) |
| Trade Count | > 30 per fold | Hard (minimum sample) |
| Calibration Error | < 5 pp per decile | Hard (retrain trigger) |
| Win Rate | > 45% | Informational |
| Calmar Ratio | > 0.5 | Informational |

Changing a metric from informational to hard gate requires a spec deviation record.

**Metric Definitions:**

| Metric | Formula |
|---|---|
| Sharpe Ratio | `(mean_return - risk_free_rate) / std_return × √252` (use √365 for crypto-only) |
| Profit Factor | `sum(winning_pnl) / abs(sum(losing_pnl))` |
| Max Drawdown | `max(peak - trough) / peak` |
| Win Rate | `winning_trades / all_trades` |
| Calmar Ratio | `annualized_return / max_drawdown` |
| Expectancy | `(win_rate × avg_win) - (loss_rate × avg_loss)` |
| Calibration Error | `max(abs(predicted_prob - observed_freq))` per decile bin |

**Portfolio-Level Metrics (not overridable):**
- Portfolio Sharpe (correlation-adjusted).
- Maximum portfolio drawdown (< 20%).
- Correlation between instrument returns (target: < 0.5).

### 9.6 Testing Strategy

**Unit Tests:**
- Overall: ≥ 80% line coverage.
- Critical modules (risk engine, order execution, reconciliation, circuit breakers): **100% branch coverage**.
- Property-based testing (Hypothesis) for risk calculations.

**Integration Tests:**
- Complete signal pipeline per instrument.
- Order lifecycle per broker adapter.
- Reconciliation per broker.
- Cross-instrument risk checks (portfolio exposure limits).
- Risk parameter override precedence.

**Scenario Tests:**
- Multi-instrument simultaneous signals: verify independent execution.
- Single broker outage: verify unaffected instrument continues.
- Regime transition: verify detection, adjustment, logging.
- Kill switch multi-broker: verify all positions closed.
- Circuit breaker cascade: per-instrument and portfolio.
- Risk override validation: invalid overrides rejected.

**CI Gate Checks (every stage merge):**

| Check | Tool | Threshold |
|---|---|---|
| Unit tests | pytest | All pass |
| Integration tests | pytest | All pass |
| Type checking | mypy (strict) | Zero errors |
| Linting | ruff | Zero errors |
| Secret scan | gitleaks or truffleHog | Zero findings |
| Code coverage (global) | pytest-cov | ≥ 80% |
| Code coverage (critical) | pytest-cov | 100% branch on: risk, execution, reconciliation, circuit breakers |
| API schema validation | openapi-spec-validator | Pass |
| No timezone-naive datetimes | custom lint rule | Zero violations |

---

## 10. Observability

### 10.1 Logging

- Structured JSON to stdout.
- Every entry: `timestamp` (UTC), `level`, `module`, `instrument`, `broker`, `message`, `extra`.
- Levels: DEBUG, INFO, WARNING, ERROR, CRITICAL.
- No secrets in log output. Enforced via code review.

### 10.2 Metrics (Prometheus)

| Metric | Type | Labels |
|---|---|---|
| `newton_health` | Gauge | `module` |
| `newton_signal_latency_seconds` | Histogram | `instrument` |
| `newton_trades_total` | Counter | `instrument, direction, result` |
| `newton_pnl_current` | Gauge | `instrument` |
| `newton_equity` | Gauge | `scope` |
| `newton_drawdown_pct` | Gauge | `scope` |
| `newton_reconciliation_status` | Gauge | `broker, result` |
| `newton_model_rolling_sharpe` | Gauge | `instrument` |
| `newton_model_rolling_accuracy` | Gauge | `instrument` |
| `newton_data_staleness_seconds` | Gauge | `instrument, interval` |
| `newton_circuit_breaker_active` | Gauge | `instrument, type` |
| `newton_regime_current` | Gauge | `instrument, regime_label` |
| `newton_regime_confidence` | Gauge | `instrument` |
| `newton_api_request_duration_seconds` | Histogram | `endpoint, method` |

### 10.3 Alerts (Telegram)

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

### 10.4 Health Endpoint

`GET /api/v1/health` returns:

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

---

## 11. Deployment & Operations

### 11.1 Deployment Model

- Single-process monolith server (Python 3.11+ / FastAPI).
- TimescaleDB (PostgreSQL) on same host or local network.
- Docker Compose for development and deployment.
- systemd or Docker restart policy for process supervision.

### 11.2 Git Workflow

- `main` — protected baseline. Always deployable. No direct commits.
- `stage/{N}-{name}` — development branch per stage.
- On each task completion: commit + push to current stage branch, report commit hash.
- Merge to `main` only at stage completion (unless explicitly approved otherwise).
- Squash merge preferred for clean history.

### 11.3 Stage-by-Stage Implementation Plan

#### Stage 1: Data Pipeline (3-4 weeks)

| Deliverable | Acceptance Criteria |
|---|---|
| Oanda data fetcher (EUR/USD) | Historical + real-time ingestion; row count ±1% for 3-year backfill |
| Binance spot data fetcher (BTC/USDT) | Historical + real-time ingestion; row count ±1% for 3-year backfill |
| TimescaleDB schema | All tables, hypertables, indexes per §4.2 |
| Feature store (technical indicators) | RSI, MACD, BB, OBV, ATR for both instruments; output matches TA-Lib < 0.01% deviation on 100 random candles |
| Data quality checks | Gap detection, OHLC verification, staleness watchdog |
| Health endpoint | `/api/v1/health` returns DB + broker connectivity |
| API: data query endpoints | OHLCV + feature retrieval; OpenAPI schema published |
| Feature store benchmark | < 500ms for 60-period lookback across 5 indicators |
| **Client:** Health/status page | System health, DB status, broker connectivity, data freshness |
| **Client:** Data viewer | Recent candles and indicator values per instrument/interval |

#### Stage 2: Event Detection & Bayesian Engine (3-4 weeks)

| Deliverable | Acceptance Criteria |
|---|---|
| SignalGenerator interface + registry | Abstract base, registry, config-driven routing |
| Event detection engine | Per-instrument; matches hand-calculated expectations |
| Token generator + classifier | Per-instrument vocabularies producing correct tokens |
| Token selection (MI ranking, redundancy filter) | Informative token selected, noise excluded on synthetic data |
| Bayesian scorer (bayesian_v1) + calibration | Implements SignalGenerator; < 5pp calibration deviation per decile |
| Signal endpoint | `/api/v1/signals/{instrument}` with generator metadata |
| Backfill events + tokens (3 years) | Computed for all historical data |
| **Client:** Signal viewer | Current signal per instrument with score and metadata |
| **Client:** Event/token explorer | Browse events and tokens for recent candles |

#### Stage 3: ML Model Integration (3-4 weeks)

| Deliverable | Acceptance Criteria |
|---|---|
| Feature engineering pipeline | Rolling windows, returns, feature vectors from feature store |
| XGBoost training (ml_v1) | Implements SignalGenerator; walk-forward AUC > 0.55 per instrument |
| CNN-LSTM (conditional) | Available if XGBoost AUC < 0.55 |
| Model artifact storage + versioning | Hash, metadata, version; integrity verified on load |
| Meta-learner / ensemble_v1 | Combines bayesian_v1 + ml_v1; calibration < 5pp |
| **Client:** Model status page | Model version, training date, AUC, feature importance |
| **Client:** Combined signal display | Shows meta-learner score |

#### Stage 4: Trading Engine & Risk Management (3-4 weeks)

| Deliverable | Acceptance Criteria |
|---|---|
| Broker adapters (Oanda spot + Binance spot) | Integration tests with paper/testnet |
| Order execution + stops | Paper orders on both brokers with stop-loss |
| Risk engine | All pre-trade/in-trade checks; validation rejects unsafe overrides |
| Reconciliation loop | Per-broker every 60s; mismatch detection verified |
| Kill switch | Closes all positions within 30 seconds |
| Regime detection | Per-instrument using deterministic formula |
| **Client:** Trading status panel | Positions, regime, circuit breakers |
| **Client:** Kill switch button | Functional with confirmation |
| **Client:** Risk configuration UI | View/edit with validation |

#### Stage 5: Backtesting Engine (2-3 weeks)

| Deliverable | Acceptance Criteria |
|---|---|
| Walk-forward framework | Per-instrument, minimum 4 folds |
| Purged K-fold | K=5, 48h purge |
| All performance metrics | Computed correctly per §9.5 |
| Pessimistic mode | 2× slippage/spread available |
| Regime-aware reporting | Per-regime breakdown; low-sample flagging |
| **Client:** Backtest runner | Select instrument, strategy, date range, pessimistic mode |
| **Client:** Results viewer | Equity curve, trade list, metrics, calibration, regime overlay |
| **Client:** Trade overlay charts | Interactive candlestick with entry/exit/stop/regime |
| **Client:** Backtest comparison | Side-by-side two runs |

#### Stage 6: Integration, Full UI & Documentation (3-4 weeks)

| Deliverable | Acceptance Criteria |
|---|---|
| OpenAPI auto-generation | Published at `/api/v1/docs` |
| In-app help content API | Markdown help per section |
| End-to-end integration tests | Full pipeline: data → signal → risk → order |
| Full dashboard, strategy management, live monitor, config, reports, in-app help | Per §8.3 specs |
| Developer, operator, user documentation | Complete in `docs/dev/`, `docs/ops/`, `docs/user/` |

#### Stage 7: Paper Trading (3 months minimum)

| Deliverable | Acceptance Criteria |
|---|---|
| Oanda practice + Binance testnet | Real-time paper trading |
| WebSocket price monitoring | Real-time position management |
| Telegram alerting | Trade alerts flowing |
| **Go/No-Go** per instrument | Sharpe > 0.8, PF > 1.3, drawdown < 15%, backtest deviation < 20%, ≥ 50 trades, no unresolved CRITICAL mismatches, calibration < 5pp |

If criteria not met: do not go live. Diagnose, fix, reset paper trading timer.

#### Stage 8: Live Trading (ongoing)

| Deliverable | Acceptance Criteria |
|---|---|
| Live broker accounts | Funded, API keys configured |
| Micro-sizing phase | First 30 trades per instrument at 0.5% equity |
| Kelly sizing enablement | After 30 trades with positive metrics |
| Monthly review process | Full analysis vs. paper baseline |

Instruments may go live independently.

### 11.4 Security

- v1 is localhost/SSH-tunnel only. No public internet exposure.
- Database accessible only from localhost.
- HTTP basic auth for UI.
- No secrets in code or config files.
- CI secret scan enforced.

### 11.5 Runbooks

Maintained in `docs/ops/runbooks.md`:
1. Broker API outage
2. Database failure
3. Reconciliation mismatch
4. Kill switch activation
5. Model retraining
6. Binance-specific (rate limits, IP whitelist, key rotation)
7. Data gap recovery

### 11.6 Documentation Strategy

| Type | Audience | Location |
|---|---|---|
| Developer docs | Developer | `docs/dev/` |
| Operator docs | Operator | `docs/ops/` |
| User docs | UI user | `docs/user/`, served via API for in-app help |
| API docs | Client developer | Auto-generated at `/api/v1/docs` |

### 11.7 Governance

**Spec Deviation Protocol:**
1. Developer identifies better solution than spec prescribes.
2. Document deviation: affected section, proposed change, justification, impact, risk.
3. Self-review checklist: safety compromise? Risk profile change? Cascading impacts?
4. Approve or reject with reasoning.
5. Reference deviation ID in code and commits.

**Strategy Approval:**
- Sole approval authority: operator (BJ).
- No automated system may activate a strategy without explicit human approval.
- Required evidence: walk-forward results, pessimistic mode results, per-regime breakdown, comparison to current strategy, evidence bundle.

**Rollback Triggers:**
- Live Sharpe deviation > 50% below backtest.
- Circuit breaker triggered but not in backtesting.
- Two consecutive negative P&L weeks not seen in backtest.
- Manual operator decision at any time.

---

## 12. Acceptance Criteria

### 12.1 Functional Requirements Traceability

| ID | Requirement | Acceptance Test |
|---|---|---|
| FR-01 | Fetch and store OHLCV for both instruments across 5 timeframes | Row count matches expected ±1% for 3-year backfill |
| FR-02 | Detect and backfill data gaps per instrument | Insert known gap; verify auto-fill within one pipeline cycle |
| FR-03 | Extensible technical indicators via FeatureProvider | Output matches TA-Lib < 0.01% on 100 random candles per instrument |
| FR-04 | Configurable event detection per instrument | Known price series → events match hand-calculated expectations |
| FR-05 | Token generation from indicator states per instrument | Given indicator values → correct token strings |
| FR-06 | Bayesian posterior with calibration | Predicted [0.5, 0.6] → observed 50-60% on held-out data |
| FR-07 | ML model per instrument | AUC-ROC > 0.55 per instrument (or fallback documented) |
| FR-08 | Meta-learner calibrated signal | Calibration < 5pp per decile |
| FR-09 | Market orders via both brokers with stop-loss | Paper trade placed successfully on each broker |
| FR-10 | Position lifecycle management | Open, modify stop, close verified per broker |
| FR-11 | Pre-trade risk checks (configurable per strategy) | Attempt to exceed limits → rejection; overrides take precedence |
| FR-12 | Circuit breakers (configurable thresholds) | Simulate 2% daily loss → system halts new entries |
| FR-13 | Reconciliation every 60s per broker | Introduce mismatch → alert within 2 minutes |
| FR-14 | Kill switch closes all positions | All positions closed within 30 seconds |
| FR-15 | Regime detection (deterministic formula) | Synthetic data transitions → correct detection, labels, confidence |
| FR-16 | Regime-aware reporting | Reports show regime labels, confidence, transitions |
| FR-17 | Versioned REST API as sole client interface | Schema validation passes; no direct DB access |
| FR-18 | Strategy management UI with risk/performance overrides | Full CRUD via UI; invalid overrides rejected |
| FR-19 | Backtest UI with trade overlays | Run from UI; chart with markers renders |
| FR-20 | Backtest reports with all metrics | All §9.5 metrics present |
| FR-21 | Config management UI with per-strategy overrides | Modify risk params → server applies and logs audit |
| FR-22 | In-app help documentation | Help loads for each major UI section |
| FR-23 | FeatureProvider extensibility | Add test indicator → stored and retrievable without schema change |
| FR-24 | Risk parameter audit logging | Change param → entry in config_changes |
| FR-25 | Swappable signal generator architecture | Multiple generators registered; per-instrument routing works; fallback triggers correctly |

### 12.2 Non-Functional Requirements

| ID | Requirement | Measurement |
|---|---|---|
| NFR-01 | Signal generation latency < 5s from candle close | p99 over 1000 candles per instrument |
| NFR-02 | System availability > 99.5% | % of 1-min intervals where `/health` returns 200 |
| NFR-03 | All timestamps in UTC | Lint rule; zero timezone-naive datetimes |
| NFR-04 | Structured JSON logging | Format validation in CI |
| NFR-05 | Prometheus `/metrics` endpoint | Scrape test in CI |
| NFR-06 | Secrets from env vars only | CI secret scan |
| NFR-07 | Crash recovery within 60s with reconciliation | Kill during paper trading; measure |
| NFR-08 | API response < 200ms p95 for reads | Load test |

### 12.3 Resolved Contradictions Summary

| # | Contradiction | Resolution |
|---|---|---|
| 1 | Daily loss limit: 3% vs. 2% | **2%** (more conservative) |
| 2 | Order type: limit vs. market | **Market** for v1 (simpler, guaranteed fill) |
| 3 | Redis: mentioned vs. omitted | **Deferred** to v1.1 |
| 4 | Binance: futures vs. spot | **Spot only** for v1 |
| 5 | Indicator schema: JSONB vs. relational | **Feature store** (long-format) |
| 6 | Trailing stop parameters | **Activation +1%, breakeven +2%** (more conservative) |
| 7 | Phase 1 status assumed implemented | **Zero-code baseline** corrected |

### 12.4 Open Questions

| # | Question | Resolution Path |
|---|---|---|
| OQ-1 | Optimal ML lookback per instrument | Hyperparameter search in Stage 3. Start with 24. |
| OQ-2 | Optimal token count per instrument | Evaluate MI curve in Stage 2. Start with 20. |
| OQ-3 | Should SELL signals open short positions? | v1: close longs only. Evaluate for v1.1. |
| OQ-4 | Multi-timeframe confirmation weighting | Deferred to v1.1. |
| OQ-5 | Break-even trade frequency per instrument | Calculate in Stage 5. |
| OQ-6 | GPU needed for XGBoost inference? | XGBoost is CPU-only. CNN-LSTM may need GPU. |
| OQ-7 | BTC/USD success criteria adjustments | Evaluate during Stage 5; decide before paper trading. |
| OQ-8 | Correlation target between instruments | Measure in Stage 5. < 0.5 desired. |
| OQ-9 | Should signal generators support hot-reload? | To be decided; v1 uses boot-time registration only. |
| OQ-10 | Shadow mode for testing new generators live? | To be decided post-v1. |

---

**End of SPEC.md**

*This is a self-contained, implementation-agnostic specification for building Newton from scratch. It synthesizes all decisions and design intent from the project's specification history into a single canonical document.*
