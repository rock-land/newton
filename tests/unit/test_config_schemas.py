from pathlib import Path

import pytest
from pydantic import ValidationError

from src.data.schema import InstrumentConfig, RiskDefaults, SystemConfig, load_instrument_config


BASE_DIR = Path(__file__).resolve().parents[2]


def test_system_config_rejects_invalid_port() -> None:
    with pytest.raises(ValidationError):
        SystemConfig(
            instruments=["EUR_USD"],
            signal_interval="1h",
            db_url="ENV:DATABASE_URL",
            telegram_bot_token="ENV:TELEGRAM_BOT_TOKEN",
            telegram_chat_id="ENV:TELEGRAM_CHAT_ID",
            api_version="v1",
            api_port=70000,
            log_level="INFO",
        )


def test_risk_defaults_enforce_spec_bounds() -> None:
    with pytest.raises(ValidationError):
        RiskDefaults(
            max_position_pct=0.30,
            max_risk_per_trade_pct=0.02,
            kelly_fraction=0.25,
            kelly_min_trades=30,
            kelly_window=60,
            micro_size_pct=0.005,
            hard_stop_pct=0.02,
            trailing_activation_pct=0.01,
            trailing_breakeven_pct=0.02,
            time_stop_hours=48,
            daily_loss_limit_pct=0.02,
            max_drawdown_pct=0.20,
            consecutive_loss_halt=5,
            consecutive_loss_halt_hours=24,
            gap_risk_multiplier=2.0,
            volatility_threshold_multiplier=2.0,
            high_volatility_size_reduction=0.5,
            high_volatility_stop_pct=0.03,
        )


def test_instrument_config_requires_binance_symbol() -> None:
    data = {
        "instrument_id": "BTC_USD",
        "broker": "binance",
        "display_name": "BTC/USDT",
        "asset_class": "crypto",
        "market_type": "spot",
        "base_currency": "BTC",
        "quote_currency": "USDT",
        "pip_size": 0.01,
        "min_trade_size": 0.00001,
        "max_trade_size": 100,
        "trading_hours": "24/7",
        "intervals": ["1m", "5m", "1h", "4h", "1d"],
        "signal_interval": "1h",
        "typical_spread_pct": 0.05,
        "default_slippage_pct": 0.02,
        "strategy_config": "config/strategies/BTC_USD_strategy.json",
        "risk_overrides": {},
    }

    with pytest.raises(ValidationError):
        InstrumentConfig.model_validate(data)


def test_load_instrument_config_accepts_existing_file() -> None:
    cfg = load_instrument_config(BASE_DIR / "config/instruments/EUR_USD.json")
    assert cfg.instrument_id == "EUR_USD"
