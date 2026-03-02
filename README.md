# Newton

A fully automated financial markets trading system with event detection, Bayesian signal scoring, and risk-managed execution.

## Overview

Newton is a multi-stage trading system built with:

- **Data Pipeline** (Stage 1): Oanda + Binance data fetchers, TimescaleDB storage, technical indicators
- **Event Detection** (Stage 2): Configurable event detection, token generation, Bayesian scoring
- **ML Pipeline** (Stage 3): Feature engineering, XGBoost training, model evaluation
- **Trading Engine** (Stage 4): Risk management, broker adapters, circuit breakers
- **Backtesting** (Stage 5): Historical simulation, performance metrics
- **Client** (Stage 6): Web UI for monitoring and control
- **Paper/Live Trading** (Stage 7-8): Deployment stages

Current status: **Stage 1 complete, Stage 2 queued** → See [TASKS](./TASKS.md) and [CHANGELOG](./CHANGELOG.md)

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         Client                               │
│  (Health panel → Data viewer → Signal display → ...)        │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                       API Layer                              │
│  (FastAPI: /api/v1/health, /ohlcv, /features, /signal)      │
└─────────────────────────────────────────────────────────────┘
                              │
          ┌───────────────────┼───────────────────┐
          ▼                   ▼                   ▼
   ┌────────────┐     ┌────────────┐     ┌────────────┐
   │  Data      │     │  Event     │     │  Trading   │
   │  Pipeline  │     │  Detection │     │  Engine    │
   │            │     │            │     │            │
   │ - Fetchers │     │ - Events   │     │ - Risk     │
   │ - Indicators│     │ - Tokens  │     │ - Executor │
   │ - Verifier │     │ - Bayesian│     │ - Brokers  │
   └────────────┘     └────────────┘     └────────────┘
          │
          ▼
   ┌────────────────────────────────────────────────┐
   │              TimescaleDB (PostgreSQL)          │
   │  - ohlcv, features, events, tokens, config    │
   └────────────────────────────────────────────────┘
```

## Prerequisites

- Python 3.11+
- PostgreSQL 15+ with TimescaleDB extension
- Node.js 18+ (for client)
- Docker & Docker Compose (for database)

## Quick Start

### 1. Clone and setup

```bash
git clone https://github.com/rusty-oc/newton.git
cd newton
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

> Notes on TA-Lib dependency:
> - `ta-lib` is included in `requirements.txt` as the canonical technical indicator engine.
> - Most Linux/macOS/Windows Python 3.11 environments receive prebuilt wheels.
> - If wheel install is unavailable in your environment, install system TA-Lib C library first, then rerun `pip install -r requirements.txt`.

### 2. Database (Docker)

```bash
docker compose up -d
```

This starts TimescaleDB on `localhost:5432`. Configure `DATABASE_URL` in your environment.

### 3. Bootstrap database

```bash
python scripts/db_bootstrap.py
python scripts/db_status.py
```

### 4. Run API server

```bash
./scripts/run_api.sh
# or: uvicorn src.app:app --reload --port 8000
```

API available at `http://localhost:8000` (docs at `/api/docs`).

### 5. Run client (optional)

Build static assets:

```bash
cd client
npm install
npm run build
```

Run options:

- **Integrated mode (recommended):** run API via `./scripts/run_api.sh` and open `http://localhost:8000/`
- **Standalone static mode:**
  ```bash
  cd client
  npm start
  ```
  Opens on `http://localhost:4173` and proxies API calls to `http://127.0.0.1:8000` in client JS, so API server must still be running.

## Configuration

Configuration files in `config/` directory:

| File | Purpose |
|------|---------|
| `system.json` | Global system settings |
| `risk.json` | Risk parameters (position limits, stops) |
| `instruments/*.json` | Instrument definitions |
| `strategies/*.json` | Strategy configurations |
| `feature_providers.json` | Indicator definitions |

Environment variables (see `.env.example`):

- `DATABASE_URL` — PostgreSQL connection string
- `OANDA_API_KEY` — Oanda account key
- `BINANCE_API_KEY` / `BINANCE_API_SECRET` — Binance credentials

## Development

### Quality checks

```bash
ruff check .
mypy src
pytest -q
```

### Running tests

```bash
pytest -q                    # all tests
pytest -q tests/unit         # unit only
pytest -q tests/integration  # integration only
```

### Feature branches

```bash
git checkout -b stage/{N}-{name}
# e.g., git checkout -b stage/2-event-detection
```

## Deployment

### Production considerations

1. **Database**: Use managed TimescaleDB (Timescale Cloud, AWS RDS, etc.)
2. **API**: Run behind reverse proxy (nginx, Caddy) with TLS
3. **Secrets**: Never commit `.env` — use secret management (HashiCorp Vault, AWS Secrets Manager)
4. **Monitoring**: Enable health endpoint monitoring (`/api/v1/health`)
5. **Backups**: Configure TimescaleDB automated backups

### Docker production deploy

```bash
docker build -t newton-api:latest .
docker run -d \
  --name newton-api \
  -p 8000:8000 \
  -e DATABASE_URL="${DATABASE_URL}" \
  -e OANDA_API_KEY="${OANDA_API_KEY}" \
  newton-api:latest
```

## Documentation

- [SPEC](./SPEC.md) — Standalone consolidated build specification (implementation-agnostic)
- [SPEC_DRAFT](./docs/spec/SPEC_DRAFT.md) — Canonical full specification draft
- [DECISIONS](./DECISIONS.md) — Accepted architecture/product decisions
- [docs/dev](./docs/dev/) — Developer documentation
- [docs/ops](./docs/ops/) — Operations runbooks
- [docs/user](./docs/user/) — User guides

## Versioning

Newton uses `0.{STAGE}.{TASK}` versioning:

- `0.1.10` = Stage 1, task 10 (Stage 1 complete)
- `0.2.1` = Stage 2, task 1
- Fix releases: `0.1.2-fix1` = Stage 1, task 2, fix 1

See [CHANGELOG](./CHANGELOG.md) for release history.

## License

Private — All rights reserved.