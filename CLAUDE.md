# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Newton is a fully automated multi-instrument trading system that generates sustainable income using a hybrid machine-learning approach (Bayesian + XGBoost) to identify and execute trades across forex (EUR/USD via Oanda) and cryptocurrency (BTC/USD via Binance spot) markets. The canonical specification is `SPEC.md`. Decision precedence: `DECISIONS.md` > `SPEC.md`.

**Current status:** Stage 6 complete (v0.6.12). Stage 7 queued.

## Commands

```bash
# Quality checks (run before committing)
ruff check .                    # Linting
mypy src                        # Type checking
pytest -q                       # All tests
pytest --cov=src -q             # Tests with coverage

# Development server
./scripts/run_api.sh
# or: uvicorn src.app:app --reload --port 8000

# Database
docker compose up -d            # Start TimescaleDB
python scripts/db_bootstrap.py  # Apply migrations
python scripts/db_status.py     # Check DB status

# Client
cd client && npm install && npm run build && npm start
```

## Code Quality Configuration

- **Linter:** ruff — line-length 100, target Python 3.11 (`.ruff.toml`)
- **Type checker:** mypy — strict mode, ignore_missing_imports (`mypy.ini`)
- **Test runner:** pytest — testpaths=tests, pythonpath=src (`pytest.ini`)
- **Coverage targets:** >=80% global; 100% branch on critical modules (data pipeline, signal routing, risk management)

## Architecture

**Stack:** Python 3.11+ / FastAPI / TimescaleDB (PostgreSQL 16) / Pydantic v2 / TA-Lib / React+TypeScript (client) / Tailwind CSS (dark mode)

### Key abstractions

| Protocol / Interface | Location | Purpose |
|---|---|---|
| `FeatureProvider` | `src/data/feature_provider.py` | Pluggable feature sources (technical indicators, future: sentiment, order book) |
| `SignalGenerator` | `src/analysis/signal_contract.py` | Swappable signal generation strategies (Bayesian, ML, Ensemble) |
| `OandaHTTPClient` | `src/data/fetcher_oanda.py` | Oanda REST API abstraction for testability |
| `BinanceHTTPClient` | `src/data/fetcher_binance.py` | Binance REST API abstraction for testability |
| `RecentFetcher` | `src/data/pipeline.py` | Fetcher abstraction for ingestion orchestration |
| `BrokerAdapter` | `src/trading/broker_base.py` | Multi-broker order/position interface (Oanda, Binance) |

### Design patterns

- **Protocol pattern:** Runtime-checkable protocols for all abstractions (no inheritance)
- **Registry pattern:** `GeneratorRegistry` in `src/trading/signal.py` for signal generators
- **Fallback chain:** Primary → fallback → neutral fail-safe for signal generation
- **Immutable domain models:** All data transfer objects use `@dataclass(frozen=True)`
- **Config-driven design:** All parameters externalized to JSON configs with Pydantic validation

### Configuration-driven design

| File | Purpose |
|---|---|
| `config/system.json` | Global settings (instruments, intervals, API config, log level) |
| `config/risk.json` | Risk parameters (position limits, Kelly fraction, stops, drawdown) |
| `config/instruments/EUR_USD.json` | EUR/USD instrument definition (Oanda, forex, pip-based) |
| `config/instruments/BTC_USD.json` | BTC/USD instrument definition (Binance, crypto, %-based) |
| `config/strategies/*.json` | Per-instrument strategy configurations |
| `config/feature_providers.json` | Indicator/feature provider definitions |
| `config/classifications/*.json` | Event classification rules per instrument |

Precedence: per-instrument `risk_overrides` > `config/risk.json` defaults.

### API structure

- Prefix: `/api/v1/`
- Docs: `/api/docs` (Swagger), `/api/redoc` (ReDoc)
- OpenAPI schema: `/api/v1/openapi.json`
- Implemented endpoints: `GET /health`, `GET /ohlcv/{instrument}`, `GET /features/metadata`, `GET /features/{instrument}`, `GET /signals/generators`, `GET /signals/{instrument}`
- All responses include checksums and timestamps for client-side validation

### Directory structure

```
src/
  app.py                    # FastAPI entry point
  data/                     # Data pipeline (fetchers, indicators, storage, verification)
  analysis/                 # Signal generation (events, tokenizer, bayesian, ML, meta-learner)
  trading/                  # Trading engine (signal routing, brokers, risk, execution)
  backtest/                 # Backtesting engine (simulation, metrics, reports)
  regime/                   # Regime detection
  api/                      # REST API routes (v1/)
tests/
  unit/                     # Isolated unit tests (mocked dependencies)
  integration/              # Tests with real DB/services
  scenarios/                # End-to-end workflow scenarios
config/                     # All configuration JSON files
client/                     # Web UI (React + TypeScript + Tailwind)
scripts/                    # Utility scripts (db_bootstrap, db_status, run_api)
docs/                       # Developer, ops, and user documentation
```

## Key Decisions

- **DEC-001:** `SPEC.md` is the canonical specification. Decision precedence: `DECISIONS.md` > `SPEC.md`.
- **DEC-002:** Git workflow enforces stage branches with push on each task completion.
- **DEC-003:** Python 3.11+ monolith with FastAPI. Single-developer system; modules separated by directory and interface.
- **DEC-004:** TimescaleDB (PostgreSQL 16) for time-series storage. Hypertables on `ohlcv` and `features`.
- **DEC-005:** Protocol-based abstractions over inheritance for testability and swappability.
- **DEC-006:** TA-Lib as canonical indicator engine with pure Python fallback for environments without the C library.
- **DEC-007:** Configuration-driven design with Pydantic v2 validation and cross-field constraints.
- **DEC-008:** Dual-broker architecture: Oanda (EUR/USD forex spot) + Binance (BTC/USD crypto spot).
- **DEC-009:** Staged scaffold pattern — empty module files retained to lock API naming across stages.
- **DEC-010:** Immutable frozen dataclasses for all domain models.
- **DEC-011:** Signal generator registry with fallback chains (primary → fallback → neutral fail-safe).

## Git Workflow

- `main` branch: always deployable
- Stage branches: `stage/{N}-{name}` (e.g., `stage/1-remediation`)
- Commit + push to stage branch on task completion; merge to `main` at stage completion only

## Versioning

Format: `0.{STAGE}.{TASK}` (current: 0.1.0). Version tracked in `VERSION` file.

## Task ID Scheme

- Stage 1 tasks: `T-101`, `T-102`, ... `T-1nn`
- Stage 2 tasks: `T-201`, `T-202`, ... `T-2nn`
- Stage gate tasks: `T-1G` (Stage 1 gate), `T-2G` (Stage 2 gate), etc.
- Remediation/fix tasks: `T-1nn-FIX1`, `T-1nn-FIX2`, etc. (appended to end of relevant stage)

## Dev Journal

Every slash command invocation and every free-form user prompt (except system commands like `/clear`, `/compact`, `/context`, `/status`) MUST be logged to `JOURNAL.md`. Format:

```
| YYYY-MM-DD HH:MM | Stage N / T-xxx | /command | One-sentence summary |
```

Entries are sorted descending (most recent at top). Log the entry at the START of command execution so it captures what was attempted.

## Missing CLI Tools

**NEVER** write workaround scripts, shims, or inline alternatives when a required command-line tool is not installed. If a command is not found:

1. **STOP** — do not attempt to work around the missing tool
2. **Tell the user** which tool is missing and what it's needed for
3. **Ask the user** whether they want to install it, use an alternative, or cancel
4. This applies to all commands: build tools, linters, formatters, database CLIs, package managers, etc.
