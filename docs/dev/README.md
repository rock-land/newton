# Developer Docs

## Local environment

```bash
cd /home/bj/.openclaw/workspace/projects/newton
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

## Required checks before task completion

Run from project root with venv active:

```bash
ruff check .
mypy src
pytest -q
```

## Focused test runs

```bash
# Unit
pytest -q tests/unit

# Integration
pytest -q tests/integration

# Scenarios
pytest -q tests/scenarios
```

## DB helper scripts

```bash
# apply pending migrations
python scripts/db_bootstrap.py

# inspect extension/tables/applied migrations
python scripts/db_status.py
```

## Notes

- `pytest` config lives in `pytest.ini`.
- Type-check target is `src/`.
- If a task touches client code, include run instructions in task report.
- Oanda EUR/USD ingestion implementation is in `src/data/fetcher_oanda.py`; focused tests are in `tests/unit/test_oanda_fetcher.py`.
- Binance BTC/USDT spot ingestion implementation is in `src/data/fetcher_binance.py`; focused tests are in `tests/unit/test_binance_fetcher.py`.
- Technical indicator provider v1 is implemented in `src/data/indicators.py`; focused tests are in `tests/unit/test_indicators_provider.py`.
- Indicator engine uses TA-Lib as canonical implementation (`ta-lib` package). If pip cannot find a wheel for your platform, install the TA-Lib system library first and reinstall requirements.
- Feature provider protocol + metadata model are in `src/data/feature_provider.py`.
- Feature store DB layer (write/read + metadata registry query path) is in `src/data/feature_store.py`; focused tests are in `tests/unit/test_feature_store.py`.
