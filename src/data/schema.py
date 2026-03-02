"""Configuration schemas for system, risk, and instruments (FINAL_SPEC Stage 1)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


Interval = Literal["1m", "5m", "1h", "4h", "1d"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


class SystemConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instruments: list[str] = Field(min_length=1)
    signal_interval: Interval
    db_url: str = Field(min_length=1)
    telegram_bot_token: str = Field(min_length=1)
    telegram_chat_id: str = Field(min_length=1)
    api_version: str = Field(pattern=r"^v\d+$")
    api_port: int = Field(ge=1, le=65535)
    log_level: LogLevel

    @field_validator("instruments")
    @classmethod
    def unique_instruments(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            msg = "instruments must be unique"
            raise ValueError(msg)
        return value


class RiskDefaults(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_position_pct: float = Field(ge=0.005, le=0.20)
    max_risk_per_trade_pct: float = Field(ge=0.001, le=0.05)
    kelly_fraction: float = Field(ge=0.10, le=0.50)
    kelly_min_trades: int = Field(ge=1)
    kelly_window: int = Field(ge=1)
    micro_size_pct: float = Field(gt=0)
    hard_stop_pct: float = Field(ge=0.005, le=0.10)
    trailing_activation_pct: float = Field(gt=0)
    trailing_breakeven_pct: float = Field(gt=0)
    time_stop_hours: int = Field(ge=1, le=168)
    daily_loss_limit_pct: float = Field(ge=0.005, le=0.05)
    max_drawdown_pct: float = Field(ge=0.05, le=0.30)
    consecutive_loss_halt: int = Field(ge=1)
    consecutive_loss_halt_hours: int = Field(ge=1)
    gap_risk_multiplier: float = Field(gt=0)
    volatility_threshold_multiplier: float = Field(gt=0)
    high_volatility_size_reduction: float = Field(gt=0, le=1)
    high_volatility_stop_pct: float = Field(gt=0)


class RiskOverrides(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_position_pct: float | None = Field(default=None, ge=0.005, le=0.20)
    max_risk_per_trade_pct: float | None = Field(default=None, ge=0.001, le=0.05)
    kelly_fraction: float | None = Field(default=None, ge=0.10, le=0.50)
    kelly_min_trades: int | None = Field(default=None, ge=1)
    kelly_window: int | None = Field(default=None, ge=1)
    micro_size_pct: float | None = Field(default=None, gt=0)
    hard_stop_pct: float | None = Field(default=None, ge=0.005, le=0.10)
    trailing_activation_pct: float | None = Field(default=None, gt=0)
    trailing_breakeven_pct: float | None = Field(default=None, gt=0)
    time_stop_hours: int | None = Field(default=None, ge=1, le=168)
    daily_loss_limit_pct: float | None = Field(default=None, ge=0.005, le=0.05)
    max_drawdown_pct: float | None = Field(default=None, ge=0.05, le=0.30)
    consecutive_loss_halt: int | None = Field(default=None, ge=1)
    consecutive_loss_halt_hours: int | None = Field(default=None, ge=1)
    gap_risk_multiplier: float | None = Field(default=None, gt=0)
    volatility_threshold_multiplier: float | None = Field(default=None, gt=0)
    high_volatility_size_reduction: float | None = Field(default=None, gt=0, le=1)
    high_volatility_stop_pct: float | None = Field(default=None, gt=0)


class RiskPortfolio(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_total_exposure_pct: float = Field(gt=0, le=1)
    max_portfolio_drawdown_pct: float = Field(gt=0, le=1)


class RiskConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    defaults: RiskDefaults
    portfolio: RiskPortfolio


class InstrumentConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instrument_id: str = Field(pattern=r"^[A-Z0-9_]+$")
    broker: Literal["oanda", "binance"]
    display_name: str = Field(min_length=1)
    asset_class: Literal["forex", "crypto"]
    market_type: Literal["spot"]
    base_currency: str = Field(pattern=r"^[A-Z]{3,5}$")
    quote_currency: str = Field(pattern=r"^[A-Z]{3,5}$")
    symbol: str | None = None
    pip_size: float = Field(gt=0)
    min_trade_size: float = Field(gt=0)
    max_trade_size: float = Field(gt=0)
    trading_hours: Literal["24/5", "24/7"]
    intervals: list[Interval] = Field(min_length=1)
    signal_interval: Interval
    typical_spread_pips: float | None = Field(default=None, gt=0)
    default_slippage_pips: float | None = Field(default=None, gt=0)
    typical_spread_pct: float | None = Field(default=None, gt=0)
    default_slippage_pct: float | None = Field(default=None, gt=0)
    strategy_config: str = Field(pattern=r"^config/strategies/.+\.json$")
    risk_overrides: RiskOverrides = Field(default_factory=RiskOverrides)

    @field_validator("intervals")
    @classmethod
    def unique_intervals(cls, value: list[Interval]) -> list[Interval]:
        if len(set(value)) != len(value):
            msg = "intervals must be unique"
            raise ValueError(msg)
        return value

    @model_validator(mode="after")
    def check_cross_field_constraints(self) -> InstrumentConfig:
        if self.max_trade_size <= self.min_trade_size:
            msg = "max_trade_size must be greater than min_trade_size"
            raise ValueError(msg)

        if self.signal_interval not in self.intervals:
            msg = "signal_interval must be included in intervals"
            raise ValueError(msg)

        if self.broker == "oanda":
            if self.symbol is not None:
                msg = "symbol must be omitted for oanda instruments"
                raise ValueError(msg)
            if self.typical_spread_pips is None or self.default_slippage_pips is None:
                msg = "oanda instruments require pips spread/slippage fields"
                raise ValueError(msg)
            if self.typical_spread_pct is not None or self.default_slippage_pct is not None:
                msg = "oanda instruments must not define pct spread/slippage fields"
                raise ValueError(msg)

        if self.broker == "binance":
            if self.symbol is None:
                msg = "binance instruments require symbol"
                raise ValueError(msg)
            if self.typical_spread_pct is None or self.default_slippage_pct is None:
                msg = "binance instruments require pct spread/slippage fields"
                raise ValueError(msg)
            if self.typical_spread_pips is not None or self.default_slippage_pips is not None:
                msg = "binance instruments must not define pips spread/slippage fields"
                raise ValueError(msg)

        return self


def _load_json(path: Path | str) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        msg = "config root must be a JSON object"
        raise ValueError(msg)
    return data


def load_system_config(path: Path | str) -> SystemConfig:
    return SystemConfig.model_validate(_load_json(path))


def load_risk_config(path: Path | str) -> RiskConfig:
    return RiskConfig.model_validate(_load_json(path))


def load_instrument_config(path: Path | str) -> InstrumentConfig:
    return InstrumentConfig.model_validate(_load_json(path))
