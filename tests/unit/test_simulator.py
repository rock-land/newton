"""Tests for backtest trade simulation engine (T-601, SPEC §9.2)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from src.backtest.simulator import (
    FillConfig,
    SimulatedFill,
    build_fill_config,
    simulate_fill,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_T0 = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
_T1 = _T0 + timedelta(hours=1)


def _eur_config(pessimistic: bool = False) -> FillConfig:
    """EUR/USD fill config per SPEC §9.2."""
    return FillConfig(
        instrument="EUR_USD",
        asset_class="forex",
        slippage=1.0,          # pips
        half_spread=0.75,      # pips
        pip_size=0.0001,
        commission_pct=0.0,
        pessimistic=pessimistic,
    )


def _btc_config(pessimistic: bool = False) -> FillConfig:
    """BTC/USD fill config per SPEC §9.2."""
    return FillConfig(
        instrument="BTC_USD",
        asset_class="crypto",
        slippage=0.0002,       # 0.02%
        half_spread=0.00025,   # 0.025%
        pip_size=0.01,
        commission_pct=0.001,  # 0.10%
        pessimistic=pessimistic,
    )


# ---------------------------------------------------------------------------
# FillConfig frozen immutability
# ---------------------------------------------------------------------------


class TestFillConfigImmutability:
    def test_frozen(self) -> None:
        cfg = _eur_config()
        with pytest.raises(AttributeError):
            cfg.slippage = 2.0  # type: ignore[misc]


# ---------------------------------------------------------------------------
# SimulatedFill frozen immutability
# ---------------------------------------------------------------------------


class TestSimulatedFillImmutability:
    def test_frozen(self) -> None:
        fill = SimulatedFill(
            instrument="EUR_USD",
            direction="BUY",
            fill_price=1.1000,
            raw_price=1.1000,
            slippage_cost=0.0001,
            spread_cost=0.000075,
            commission_cost=0.0,
            total_cost=0.000175,
            fill_time=_T1,
            pessimistic=False,
        )
        with pytest.raises(AttributeError):
            fill.fill_price = 1.2  # type: ignore[misc]


# ---------------------------------------------------------------------------
# EUR/USD fill price math
# ---------------------------------------------------------------------------


class TestEurUsdFills:
    """SPEC §9.2: Fill at open[T+1] ± (1.0 pip slippage + 0.75 pip half-spread)."""

    def test_buy_normal(self) -> None:
        """BUY gets worse (higher) price."""
        cfg = _eur_config()
        next_open = 1.10000
        fill = simulate_fill(
            direction="BUY",
            next_bar_open=next_open,
            fill_time=_T1,
            config=cfg,
        )
        # cost = (1.0 + 0.75) * 0.0001 = 0.000175
        expected_price = next_open + 0.000175
        assert fill.fill_price == pytest.approx(expected_price, abs=1e-10)
        assert fill.raw_price == next_open
        assert fill.slippage_cost == pytest.approx(1.0 * 0.0001, abs=1e-10)
        assert fill.spread_cost == pytest.approx(0.75 * 0.0001, abs=1e-10)
        assert fill.commission_cost == 0.0
        assert fill.total_cost == pytest.approx(0.000175, abs=1e-10)
        assert fill.direction == "BUY"
        assert fill.pessimistic is False

    def test_sell_normal(self) -> None:
        """SELL gets worse (lower) price."""
        cfg = _eur_config()
        next_open = 1.10000
        fill = simulate_fill(
            direction="SELL",
            next_bar_open=next_open,
            fill_time=_T1,
            config=cfg,
        )
        expected_price = next_open - 0.000175
        assert fill.fill_price == pytest.approx(expected_price, abs=1e-10)
        assert fill.total_cost == pytest.approx(0.000175, abs=1e-10)

    def test_buy_pessimistic(self) -> None:
        """Pessimistic mode: 2× slippage and spread."""
        cfg = _eur_config(pessimistic=True)
        next_open = 1.10000
        fill = simulate_fill(
            direction="BUY",
            next_bar_open=next_open,
            fill_time=_T1,
            config=cfg,
        )
        # cost = (1.0*2 + 0.75*2) * 0.0001 = 0.000350
        expected_price = next_open + 0.000350
        assert fill.fill_price == pytest.approx(expected_price, abs=1e-10)
        assert fill.slippage_cost == pytest.approx(2.0 * 0.0001, abs=1e-10)
        assert fill.spread_cost == pytest.approx(1.5 * 0.0001, abs=1e-10)
        assert fill.total_cost == pytest.approx(0.000350, abs=1e-10)
        assert fill.pessimistic is True

    def test_sell_pessimistic(self) -> None:
        """Pessimistic SELL: price moves down further."""
        cfg = _eur_config(pessimistic=True)
        next_open = 1.10000
        fill = simulate_fill(
            direction="SELL",
            next_bar_open=next_open,
            fill_time=_T1,
            config=cfg,
        )
        expected_price = next_open - 0.000350
        assert fill.fill_price == pytest.approx(expected_price, abs=1e-10)

    def test_no_commission_for_forex(self) -> None:
        """EUR/USD has no separate commission per SPEC §9.2."""
        cfg = _eur_config()
        fill = simulate_fill(
            direction="BUY",
            next_bar_open=1.10000,
            fill_time=_T1,
            config=cfg,
        )
        assert fill.commission_cost == 0.0


# ---------------------------------------------------------------------------
# BTC/USD fill price math
# ---------------------------------------------------------------------------


class TestBtcUsdFills:
    """SPEC §9.2: Fill at open[T+1] ± (0.02% slippage + 0.025% half-spread).
    Plus 0.10% taker commission."""

    def test_buy_normal(self) -> None:
        """BUY gets worse (higher) price + commission."""
        cfg = _btc_config()
        next_open = 50000.0
        fill = simulate_fill(
            direction="BUY",
            next_bar_open=next_open,
            fill_time=_T1,
            config=cfg,
        )
        # slippage = 50000 * 0.0002 = 10.0
        # spread   = 50000 * 0.00025 = 12.5
        # fill_price = 50000 + 10 + 12.5 = 50022.5
        # commission = 50022.5 * 0.001 = 50.0225 (per unit cost)
        # total_cost = 10 + 12.5 + 50.0225 = 72.5225
        expected_slippage = 50000.0 * 0.0002
        expected_spread = 50000.0 * 0.00025
        expected_fill = next_open + expected_slippage + expected_spread
        expected_commission = expected_fill * 0.001

        assert fill.fill_price == pytest.approx(expected_fill, abs=1e-6)
        assert fill.slippage_cost == pytest.approx(expected_slippage, abs=1e-6)
        assert fill.spread_cost == pytest.approx(expected_spread, abs=1e-6)
        assert fill.commission_cost == pytest.approx(expected_commission, abs=1e-6)
        assert fill.total_cost == pytest.approx(
            expected_slippage + expected_spread + expected_commission, abs=1e-6
        )

    def test_sell_normal(self) -> None:
        """SELL gets worse (lower) price + commission."""
        cfg = _btc_config()
        next_open = 50000.0
        fill = simulate_fill(
            direction="SELL",
            next_bar_open=next_open,
            fill_time=_T1,
            config=cfg,
        )
        expected_slippage = 50000.0 * 0.0002
        expected_spread = 50000.0 * 0.00025
        expected_fill = next_open - expected_slippage - expected_spread
        expected_commission = expected_fill * 0.001

        assert fill.fill_price == pytest.approx(expected_fill, abs=1e-6)
        assert fill.commission_cost == pytest.approx(expected_commission, abs=1e-6)

    def test_buy_pessimistic(self) -> None:
        """Pessimistic: 2× slippage/spread, commission unchanged."""
        cfg = _btc_config(pessimistic=True)
        next_open = 50000.0
        fill = simulate_fill(
            direction="BUY",
            next_bar_open=next_open,
            fill_time=_T1,
            config=cfg,
        )
        # slippage = 50000 * 0.0004 = 20.0
        # spread   = 50000 * 0.0005 = 25.0
        # fill_price = 50000 + 20 + 25 = 50045.0
        # commission = 50045.0 * 0.001 = 50.045
        expected_slippage = 50000.0 * 0.0004
        expected_spread = 50000.0 * 0.0005
        expected_fill = next_open + expected_slippage + expected_spread
        expected_commission = expected_fill * 0.001

        assert fill.fill_price == pytest.approx(expected_fill, abs=1e-6)
        assert fill.slippage_cost == pytest.approx(expected_slippage, abs=1e-6)
        assert fill.spread_cost == pytest.approx(expected_spread, abs=1e-6)
        assert fill.commission_cost == pytest.approx(expected_commission, abs=1e-6)
        assert fill.pessimistic is True

    def test_sell_pessimistic(self) -> None:
        """Pessimistic SELL."""
        cfg = _btc_config(pessimistic=True)
        next_open = 50000.0
        fill = simulate_fill(
            direction="SELL",
            next_bar_open=next_open,
            fill_time=_T1,
            config=cfg,
        )
        expected_slippage = 50000.0 * 0.0004
        expected_spread = 50000.0 * 0.0005
        expected_fill = next_open - expected_slippage - expected_spread

        assert fill.fill_price == pytest.approx(expected_fill, abs=1e-6)

    def test_commission_unchanged_in_pessimistic(self) -> None:
        """SPEC §9.2: Commission unchanged in pessimistic mode."""
        normal_cfg = _btc_config(pessimistic=False)
        pessimistic_cfg = _btc_config(pessimistic=True)

        # Same commission rate
        assert normal_cfg.commission_pct == pessimistic_cfg.commission_pct


# ---------------------------------------------------------------------------
# build_fill_config from instrument config dicts
# ---------------------------------------------------------------------------


class TestBuildFillConfig:
    def test_eur_usd_normal(self) -> None:
        """Build config from EUR/USD instrument definition."""
        instrument_cfg = {
            "instrument_id": "EUR_USD",
            "asset_class": "forex",
            "pip_size": 0.0001,
            "default_slippage_pips": 1.0,
            "typical_spread_pips": 1.5,
        }
        cfg = build_fill_config(instrument_cfg, pessimistic=False)
        assert cfg.instrument == "EUR_USD"
        assert cfg.asset_class == "forex"
        assert cfg.slippage == 1.0
        assert cfg.half_spread == pytest.approx(0.75)  # half of typical_spread
        assert cfg.pip_size == 0.0001
        assert cfg.commission_pct == 0.0
        assert cfg.pessimistic is False

    def test_eur_usd_pessimistic(self) -> None:
        instrument_cfg = {
            "instrument_id": "EUR_USD",
            "asset_class": "forex",
            "pip_size": 0.0001,
            "default_slippage_pips": 1.0,
            "typical_spread_pips": 1.5,
        }
        cfg = build_fill_config(instrument_cfg, pessimistic=True)
        assert cfg.pessimistic is True
        # Slippage/spread values stored at base; multiplier applied at fill time
        assert cfg.slippage == 1.0
        assert cfg.half_spread == pytest.approx(0.75)

    def test_btc_usd_normal(self) -> None:
        """Build config from BTC/USD instrument definition."""
        instrument_cfg = {
            "instrument_id": "BTC_USD",
            "asset_class": "crypto",
            "pip_size": 0.01,
            "default_slippage_pct": 0.02,
            "typical_spread_pct": 0.05,
        }
        cfg = build_fill_config(instrument_cfg, pessimistic=False)
        assert cfg.instrument == "BTC_USD"
        assert cfg.asset_class == "crypto"
        assert cfg.slippage == pytest.approx(0.0002)   # 0.02% as fraction
        assert cfg.half_spread == pytest.approx(0.00025)  # half of 0.05% as fraction
        assert cfg.pip_size == 0.01
        assert cfg.commission_pct == pytest.approx(0.001)  # 0.10%
        assert cfg.pessimistic is False

    def test_btc_usd_pessimistic(self) -> None:
        instrument_cfg = {
            "instrument_id": "BTC_USD",
            "asset_class": "crypto",
            "pip_size": 0.01,
            "default_slippage_pct": 0.02,
            "typical_spread_pct": 0.05,
        }
        cfg = build_fill_config(instrument_cfg, pessimistic=True)
        assert cfg.pessimistic is True


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_fill_time_propagated(self) -> None:
        """Fill time matches the provided timestamp."""
        cfg = _eur_config()
        fill = simulate_fill(
            direction="BUY",
            next_bar_open=1.10000,
            fill_time=_T1,
            config=cfg,
        )
        assert fill.fill_time == _T1

    def test_instrument_propagated(self) -> None:
        """Instrument is carried through to the fill."""
        cfg = _btc_config()
        fill = simulate_fill(
            direction="SELL",
            next_bar_open=50000.0,
            fill_time=_T1,
            config=cfg,
        )
        assert fill.instrument == "BTC_USD"

    def test_very_low_price(self) -> None:
        """Fill math works at very low price levels."""
        cfg = _eur_config()
        fill = simulate_fill(
            direction="BUY",
            next_bar_open=0.50000,
            fill_time=_T1,
            config=cfg,
        )
        assert fill.fill_price == pytest.approx(0.50000 + 0.000175, abs=1e-10)

    def test_very_high_price(self) -> None:
        """Fill math works at very high price levels."""
        cfg = _btc_config()
        fill = simulate_fill(
            direction="BUY",
            next_bar_open=100000.0,
            fill_time=_T1,
            config=cfg,
        )
        expected_slip = 100000.0 * 0.0002
        expected_spread = 100000.0 * 0.00025
        expected_fill = 100000.0 + expected_slip + expected_spread
        assert fill.fill_price == pytest.approx(expected_fill, abs=1e-4)
