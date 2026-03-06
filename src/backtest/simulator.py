"""Trade simulation engine for backtesting (T-601, SPEC §9.2).

Provides per-instrument fill models that simulate realistic trade execution
costs including slippage, bid-ask spread, and commission.

Fill model per SPEC §9.2:
- EUR/USD: Fill at open[T+1] ± (1.0 pip slippage + 0.75 pip half-spread).
           No separate commission.
- BTC/USD: Fill at open[T+1] ± (0.02% slippage + 0.025% half-spread).
           Plus 0.10% taker commission.
- Pessimistic mode: 2× multiplier on slippage and spread. Commission unchanged.
- No partial fills, no rejects in v1.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal


@dataclass(frozen=True)
class FillConfig:
    """Per-instrument fill model parameters.

    For forex: slippage and half_spread are in pips (multiply by pip_size
    for absolute price adjustment).
    For crypto: slippage and half_spread are fractions (e.g. 0.0002 = 0.02%).
    """

    instrument: str
    asset_class: Literal["forex", "crypto"]
    slippage: float
    half_spread: float
    pip_size: float
    commission_pct: float
    pessimistic: bool


@dataclass(frozen=True)
class SimulatedFill:
    """Result of a simulated trade fill."""

    instrument: str
    direction: Literal["BUY", "SELL"]
    fill_price: float
    raw_price: float
    slippage_cost: float
    spread_cost: float
    commission_cost: float
    total_cost: float
    fill_time: datetime
    pessimistic: bool


def build_fill_config(
    instrument_cfg: dict[str, object],
    *,
    pessimistic: bool = False,
) -> FillConfig:
    """Build a FillConfig from an instrument configuration dict.

    Args:
        instrument_cfg: Instrument definition (from config/instruments/*.json).
        pessimistic: Whether to enable pessimistic mode (2× slippage/spread).

    Returns:
        FillConfig with per-instrument fill parameters.
    """
    asset_class = str(instrument_cfg["asset_class"])
    pip_size = float(instrument_cfg["pip_size"])  # type: ignore[arg-type]

    if asset_class == "forex":
        slippage = float(instrument_cfg["default_slippage_pips"])  # type: ignore[arg-type]
        half_spread = float(instrument_cfg["typical_spread_pips"]) / 2.0  # type: ignore[arg-type]
        commission_pct = 0.0
    else:
        # Crypto: convert from percentage to fraction
        slippage = float(instrument_cfg["default_slippage_pct"]) / 100.0  # type: ignore[arg-type]
        half_spread = float(instrument_cfg["typical_spread_pct"]) / 100.0 / 2.0  # type: ignore[arg-type]
        commission_pct = 0.001  # 0.10% taker per SPEC §9.2

    return FillConfig(
        instrument=str(instrument_cfg["instrument_id"]),
        asset_class=asset_class,  # type: ignore[arg-type]
        slippage=slippage,
        half_spread=half_spread,
        pip_size=pip_size,
        commission_pct=commission_pct,
        pessimistic=pessimistic,
    )


def simulate_fill(
    *,
    direction: Literal["BUY", "SELL"],
    next_bar_open: float,
    fill_time: datetime,
    config: FillConfig,
) -> SimulatedFill:
    """Simulate a trade fill at the next bar's open price.

    SPEC §9.2: Fill at open[T+1] with slippage and spread adjustments.
    BUY fills at a higher (worse) price; SELL fills at a lower (worse) price.

    Args:
        direction: Trade direction.
        next_bar_open: The open price of the bar following the signal (T+1).
        fill_time: Timestamp of the T+1 bar.
        config: Fill model parameters.

    Returns:
        SimulatedFill with effective fill price and cost breakdown.
    """
    multiplier = 2.0 if config.pessimistic else 1.0

    if config.asset_class == "forex":
        slippage_cost = config.slippage * multiplier * config.pip_size
        spread_cost = config.half_spread * multiplier * config.pip_size
    else:
        slippage_cost = next_bar_open * config.slippage * multiplier
        spread_cost = next_bar_open * config.half_spread * multiplier

    sign = 1.0 if direction == "BUY" else -1.0
    fill_price = next_bar_open + sign * (slippage_cost + spread_cost)

    commission_cost = fill_price * config.commission_pct
    total_cost = slippage_cost + spread_cost + commission_cost

    return SimulatedFill(
        instrument=config.instrument,
        direction=direction,
        fill_price=fill_price,
        raw_price=next_bar_open,
        slippage_cost=slippage_cost,
        spread_cost=spread_cost,
        commission_cost=commission_cost,
        total_cost=total_cost,
        fill_time=fill_time,
        pessimistic=config.pessimistic,
    )
