-- Newton Stage 1 bootstrap schema per FINAL_SPEC §4.2

CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE IF NOT EXISTS ohlcv (
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
SELECT create_hypertable('ohlcv', 'time', if_not_exists => TRUE, migrate_data => TRUE);

CREATE TABLE IF NOT EXISTS features (
    time        TIMESTAMPTZ NOT NULL,
    instrument  TEXT NOT NULL,
    interval    TEXT NOT NULL,
    namespace   TEXT NOT NULL,
    feature_key TEXT NOT NULL,
    value       DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (time, instrument, interval, namespace, feature_key)
);
SELECT create_hypertable('features', 'time', if_not_exists => TRUE, migrate_data => TRUE);
CREATE INDEX IF NOT EXISTS idx_features_lookup
    ON features (instrument, interval, namespace, feature_key, time DESC);

CREATE TABLE IF NOT EXISTS feature_metadata (
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

CREATE TABLE IF NOT EXISTS events (
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
CREATE INDEX IF NOT EXISTS idx_events_lookup ON events (instrument, interval, event_name, time);

CREATE TABLE IF NOT EXISTS tokens (
    time        TIMESTAMPTZ NOT NULL,
    instrument  TEXT NOT NULL,
    interval    TEXT NOT NULL,
    tokens      TEXT[] NOT NULL,
    PRIMARY KEY (time, instrument, interval)
);

CREATE TABLE IF NOT EXISTS trades (
    id                  BIGSERIAL PRIMARY KEY,
    client_order_id     TEXT UNIQUE NOT NULL,
    broker_order_id     TEXT,
    instrument          TEXT NOT NULL,
    broker              TEXT NOT NULL,
    direction           TEXT NOT NULL CHECK (direction IN ('BUY', 'SELL')),
    signal_score        DOUBLE PRECISION NOT NULL,
    signal_type         TEXT NOT NULL,
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

CREATE TABLE IF NOT EXISTS reconciliation_log (
    id          BIGSERIAL PRIMARY KEY,
    checked_at  TIMESTAMPTZ DEFAULT NOW(),
    broker      TEXT NOT NULL,
    status      TEXT NOT NULL CHECK (status IN ('MATCH', 'SYSTEM_EXTRA', 'BROKER_EXTRA')),
    details     JSONB,
    resolved    BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS regime_log (
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
CREATE INDEX IF NOT EXISTS idx_regime_lookup ON regime_log (instrument, time DESC);

CREATE TABLE IF NOT EXISTS strategy_versions (
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

CREATE TABLE IF NOT EXISTS spec_deviations (
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

CREATE TABLE IF NOT EXISTS config_changes (
    id              BIGSERIAL PRIMARY KEY,
    changed_at      TIMESTAMPTZ DEFAULT NOW(),
    changed_by      TEXT NOT NULL,
    section         TEXT NOT NULL,
    instrument      TEXT,
    old_value       JSONB,
    new_value       JSONB NOT NULL,
    reason          TEXT
);
