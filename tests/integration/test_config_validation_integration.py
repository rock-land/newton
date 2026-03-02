from pathlib import Path

from src.data.schema import (
    load_instrument_config,
    load_risk_config,
    load_system_config,
)


BASE_DIR = Path(__file__).resolve().parents[2]


def test_existing_config_files_validate_against_schemas() -> None:
    system = load_system_config(BASE_DIR / "config/system.json")
    risk = load_risk_config(BASE_DIR / "config/risk.json")
    eur = load_instrument_config(BASE_DIR / "config/instruments/EUR_USD.json")
    btc = load_instrument_config(BASE_DIR / "config/instruments/BTC_USD.json")

    assert system.api_version == "v1"
    assert risk.defaults.max_drawdown_pct == 0.2
    assert eur.broker == "oanda"
    assert btc.broker == "binance"
