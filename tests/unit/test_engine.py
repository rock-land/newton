"""Tests for backtest engine (T-602, SPEC §9.1–9.4)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from src.analysis.signal_contract import (
    FeatureSnapshot,
    GeneratorConfig,
    Signal,
)
from src.backtest.engine import (
    BacktestConfig,
    BacktestResult,
    BacktestTrade,
    run_backtest,
)
from src.backtest.simulator import FillConfig
from src.data.fetcher_base import CandleRecord
from src.trading.risk import ResolvedRiskConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BASE_TIME = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)


def _make_candle(
    idx: int,
    *,
    open_: float,
    high: float,
    low: float,
    close: float,
    volume: float = 1000.0,
    instrument: str = "EUR_USD",
    interval: str = "1h",
) -> CandleRecord:
    return CandleRecord(
        time=_BASE_TIME + timedelta(hours=idx),
        instrument=instrument,
        interval=interval,
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
        spread_avg=None,
        verified=True,
        source="test",
    )


def _rising_candles(n: int, start_price: float = 1.1000, step: float = 0.0010) -> list[CandleRecord]:
    """Generate n candles with a steady uptrend."""
    candles = []
    for i in range(n):
        o = start_price + i * step
        c = o + step * 0.8
        h = max(o, c) + step * 0.2
        low = min(o, c) - step * 0.1
        candles.append(_make_candle(i, open_=o, high=h, low=low, close=c))
    return candles


def _flat_candles(n: int, price: float = 1.1000) -> list[CandleRecord]:
    """Generate n flat candles at a fixed price."""
    return [
        _make_candle(
            i,
            open_=price,
            high=price + 0.0001,
            low=price - 0.0001,
            close=price,
        )
        for i in range(n)
    ]


def _dropping_candles(
    n: int, start_price: float = 1.1000, step: float = 0.0050,
) -> list[CandleRecord]:
    """Generate n candles with a steep downtrend (for stop-loss tests)."""
    candles = []
    for i in range(n):
        o = start_price - i * step
        c = o - step * 0.8
        h = o + step * 0.1
        low = c - step * 0.2
        candles.append(_make_candle(i, open_=o, high=h, low=low, close=c))
    return candles


def _default_risk_config() -> ResolvedRiskConfig:
    return ResolvedRiskConfig(
        max_position_pct=0.05,
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


def _eur_fill_config(pessimistic: bool = False) -> FillConfig:
    return FillConfig(
        instrument="EUR_USD",
        asset_class="forex",
        slippage=1.0,
        half_spread=0.75,
        pip_size=0.0001,
        commission_pct=0.0,
        pessimistic=pessimistic,
    )


def _default_generator_config() -> GeneratorConfig:
    return GeneratorConfig(enabled=True, parameters={})


class _AlwaysBuyGenerator:
    """Mock generator that always returns BUY."""

    @property
    def id(self) -> str:
        return "test_always_buy"

    @property
    def version(self) -> str:
        return "1.0"

    def generate(
        self, instrument: str, features: FeatureSnapshot, config: GeneratorConfig,
    ) -> Signal:
        return Signal(
            instrument=instrument,
            action="BUY",
            probability=0.7,
            confidence=0.6,
            component_scores={"test": 0.7},
            metadata={},
            generated_at=features.time,
            generator_id=self.id,
        )

    def generate_batch(
        self,
        instrument: str,
        historical_features: list[FeatureSnapshot],
        config: GeneratorConfig,
    ) -> list[tuple[datetime, Signal]]:
        return [(f.time, self.generate(instrument, f, config)) for f in historical_features]

    def validate_config(self, config: dict[str, Any]) -> bool:
        return True


class _NeutralGenerator:
    """Mock generator that always returns NEUTRAL."""

    @property
    def id(self) -> str:
        return "test_neutral"

    @property
    def version(self) -> str:
        return "1.0"

    def generate(
        self, instrument: str, features: FeatureSnapshot, config: GeneratorConfig,
    ) -> Signal:
        return Signal(
            instrument=instrument,
            action="NEUTRAL",
            probability=0.5,
            confidence=0.3,
            component_scores={"test": 0.5},
            metadata={},
            generated_at=features.time,
            generator_id=self.id,
        )

    def generate_batch(
        self,
        instrument: str,
        historical_features: list[FeatureSnapshot],
        config: GeneratorConfig,
    ) -> list[tuple[datetime, Signal]]:
        return [(f.time, self.generate(instrument, f, config)) for f in historical_features]

    def validate_config(self, config: dict[str, Any]) -> bool:
        return True


class _AlwaysSellGenerator:
    """Mock generator that always returns SELL."""

    @property
    def id(self) -> str:
        return "test_always_sell"

    @property
    def version(self) -> str:
        return "1.0"

    def generate(
        self, instrument: str, features: FeatureSnapshot, config: GeneratorConfig,
    ) -> Signal:
        return Signal(
            instrument=instrument,
            action="SELL",
            probability=0.7,
            confidence=0.6,
            component_scores={"test": 0.7},
            metadata={},
            generated_at=features.time,
            generator_id=self.id,
        )

    def generate_batch(
        self,
        instrument: str,
        historical_features: list[FeatureSnapshot],
        config: GeneratorConfig,
    ) -> list[tuple[datetime, Signal]]:
        return [(f.time, self.generate(instrument, f, config)) for f in historical_features]

    def validate_config(self, config: dict[str, Any]) -> bool:
        return True


# ---------------------------------------------------------------------------
# BacktestConfig / BacktestTrade / BacktestResult immutability
# ---------------------------------------------------------------------------


class TestDataclassImmutability:
    def test_backtest_config_frozen(self) -> None:
        cfg = BacktestConfig(
            instrument="EUR_USD",
            interval="1h",
            start_date=_BASE_TIME,
            end_date=_BASE_TIME + timedelta(days=30),
            initial_equity=100_000.0,
            pessimistic=False,
        )
        with pytest.raises(AttributeError):
            cfg.instrument = "BTC_USD"  # type: ignore[misc]

    def test_backtest_trade_frozen(self) -> None:
        trade = BacktestTrade(
            entry_time=_BASE_TIME,
            entry_price=1.1000,
            exit_time=_BASE_TIME + timedelta(hours=5),
            exit_price=1.1050,
            direction="BUY",
            quantity=1000.0,
            pnl=5.0,
            commission=0.0,
            slippage_cost=0.0001,
            spread_cost=0.000075,
            exit_reason="signal",
            regime_label="LOW_VOL_TRENDING",
        )
        with pytest.raises(AttributeError):
            trade.pnl = 10.0  # type: ignore[misc]

    def test_backtest_result_frozen(self) -> None:
        result = BacktestResult(
            config=BacktestConfig(
                instrument="EUR_USD",
                interval="1h",
                start_date=_BASE_TIME,
                end_date=_BASE_TIME + timedelta(days=1),
                initial_equity=100_000.0,
                pessimistic=False,
            ),
            equity_curve=[],
            trades=[],
            initial_equity=100_000.0,
            final_equity=100_000.0,
            total_return=0.0,
            trade_count=0,
        )
        with pytest.raises(AttributeError):
            result.final_equity = 200_000.0  # type: ignore[misc]


# ---------------------------------------------------------------------------
# No-trade scenario
# ---------------------------------------------------------------------------


class TestNoTrades:
    def test_neutral_signals_no_trades(self) -> None:
        """Generator returns NEUTRAL — no trades, equity unchanged."""
        candles = _flat_candles(50)
        cfg = BacktestConfig(
            instrument="EUR_USD",
            interval="1h",
            start_date=candles[0].time,
            end_date=candles[-1].time,
            initial_equity=100_000.0,
            pessimistic=False,
        )
        result = run_backtest(
            candles=candles,
            signal_generator=_NeutralGenerator(),
            generator_config=_default_generator_config(),
            fill_config=_eur_fill_config(),
            risk_config=_default_risk_config(),
            config=cfg,
        )
        assert result.trade_count == 0
        assert len(result.trades) == 0
        assert result.final_equity == result.initial_equity
        assert result.total_return == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Full lifecycle: entry → exit
# ---------------------------------------------------------------------------


class TestFullLifecycle:
    def test_buy_trade_opens_and_closes(self) -> None:
        """BUY signal → trade opens at T+1 open → eventually closes."""
        candles = _rising_candles(50)
        cfg = BacktestConfig(
            instrument="EUR_USD",
            interval="1h",
            start_date=candles[0].time,
            end_date=candles[-1].time,
            initial_equity=100_000.0,
            pessimistic=False,
        )
        result = run_backtest(
            candles=candles,
            signal_generator=_AlwaysBuyGenerator(),
            generator_config=_default_generator_config(),
            fill_config=_eur_fill_config(),
            risk_config=_default_risk_config(),
            config=cfg,
        )
        # Should have at least one trade
        assert result.trade_count >= 1
        assert len(result.trades) == result.trade_count
        # First trade should be a BUY
        assert result.trades[0].direction == "BUY"
        # Trade should have entry and exit times
        assert result.trades[0].entry_time is not None
        assert result.trades[0].exit_time is not None

    def test_sell_trade_opens_and_closes(self) -> None:
        """SELL signal → trade opens and closes."""
        candles = _dropping_candles(50)
        cfg = BacktestConfig(
            instrument="EUR_USD",
            interval="1h",
            start_date=candles[0].time,
            end_date=candles[-1].time,
            initial_equity=100_000.0,
            pessimistic=False,
        )
        result = run_backtest(
            candles=candles,
            signal_generator=_AlwaysSellGenerator(),
            generator_config=_default_generator_config(),
            fill_config=_eur_fill_config(),
            risk_config=_default_risk_config(),
            config=cfg,
        )
        assert result.trade_count >= 1
        assert result.trades[0].direction == "SELL"


# ---------------------------------------------------------------------------
# Stop-loss hit
# ---------------------------------------------------------------------------


class TestStopLoss:
    def test_hard_stop_triggers_on_drop(self) -> None:
        """BUY entry → price drops below hard stop → trade closed."""
        # Start with a couple flat candles, then sharp drop
        candles = _flat_candles(5, price=1.1000) + _dropping_candles(
            10, start_price=1.1000, step=0.0050,
        )
        # Re-index times
        reindexed = []
        for i, c in enumerate(candles):
            reindexed.append(_make_candle(
                i, open_=c.open, high=c.high, low=c.low, close=c.close,
            ))
        cfg = BacktestConfig(
            instrument="EUR_USD",
            interval="1h",
            start_date=reindexed[0].time,
            end_date=reindexed[-1].time,
            initial_equity=100_000.0,
            pessimistic=False,
        )
        result = run_backtest(
            candles=reindexed,
            signal_generator=_AlwaysBuyGenerator(),
            generator_config=_default_generator_config(),
            fill_config=_eur_fill_config(),
            risk_config=_default_risk_config(),
            config=cfg,
        )
        # Should have at least one trade that hit stop loss
        stopped = [t for t in result.trades if t.exit_reason == "hard_stop"]
        assert len(stopped) >= 1
        # Stopped trade should have negative PnL
        assert stopped[0].pnl < 0


# ---------------------------------------------------------------------------
# Time stop
# ---------------------------------------------------------------------------


class TestTimeStop:
    def test_time_stop_closes_position(self) -> None:
        """Position open > time_stop_hours → force closed."""
        # Use a short time stop for testing
        risk_cfg = ResolvedRiskConfig(
            max_position_pct=0.05,
            max_risk_per_trade_pct=0.02,
            kelly_fraction=0.25,
            kelly_min_trades=30,
            kelly_window=60,
            micro_size_pct=0.005,
            hard_stop_pct=0.10,  # wide stop so it doesn't trigger
            trailing_activation_pct=0.50,  # high so trailing doesn't trigger
            trailing_breakeven_pct=0.60,
            time_stop_hours=5,  # 5 hours
            daily_loss_limit_pct=0.02,
            max_drawdown_pct=0.20,
            consecutive_loss_halt=5,
            consecutive_loss_halt_hours=24,
            gap_risk_multiplier=2.0,
            volatility_threshold_multiplier=2.0,
            high_volatility_size_reduction=0.5,
            high_volatility_stop_pct=0.03,
        )
        candles = _flat_candles(20, price=1.1000)
        cfg = BacktestConfig(
            instrument="EUR_USD",
            interval="1h",
            start_date=candles[0].time,
            end_date=candles[-1].time,
            initial_equity=100_000.0,
            pessimistic=False,
        )
        result = run_backtest(
            candles=candles,
            signal_generator=_AlwaysBuyGenerator(),
            generator_config=_default_generator_config(),
            fill_config=_eur_fill_config(),
            risk_config=risk_cfg,
            config=cfg,
        )
        time_stopped = [t for t in result.trades if t.exit_reason == "time_stop"]
        assert len(time_stopped) >= 1


# ---------------------------------------------------------------------------
# Position limit enforcement
# ---------------------------------------------------------------------------


class TestPositionLimit:
    def test_only_one_position_at_a_time(self) -> None:
        """Max 1 position per instrument — second signal rejected while open."""
        candles = _flat_candles(50, price=1.1000)
        cfg = BacktestConfig(
            instrument="EUR_USD",
            interval="1h",
            start_date=candles[0].time,
            end_date=candles[-1].time,
            initial_equity=100_000.0,
            pessimistic=False,
        )
        # With wide stops, a flat market, and always-buy, there should
        # never be overlapping positions
        risk_cfg = _default_risk_config()
        result = run_backtest(
            candles=candles,
            signal_generator=_AlwaysBuyGenerator(),
            generator_config=_default_generator_config(),
            fill_config=_eur_fill_config(),
            risk_config=risk_cfg,
            config=cfg,
        )
        # Verify no two trades overlap in time
        for i in range(len(result.trades) - 1):
            t1 = result.trades[i]
            t2 = result.trades[i + 1]
            assert t1.exit_time is not None
            assert t1.exit_time <= t2.entry_time


# ---------------------------------------------------------------------------
# End-of-data close
# ---------------------------------------------------------------------------


class TestEndOfData:
    def test_open_position_closed_at_end(self) -> None:
        """Open position force-closed at end of data."""
        # Wide stops, short data set → position stays open until end
        risk_cfg = ResolvedRiskConfig(
            max_position_pct=0.05,
            max_risk_per_trade_pct=0.02,
            kelly_fraction=0.25,
            kelly_min_trades=30,
            kelly_window=60,
            micro_size_pct=0.005,
            hard_stop_pct=0.10,  # wide
            trailing_activation_pct=0.50,
            trailing_breakeven_pct=0.60,
            time_stop_hours=999,  # won't trigger
            daily_loss_limit_pct=0.02,
            max_drawdown_pct=0.20,
            consecutive_loss_halt=5,
            consecutive_loss_halt_hours=24,
            gap_risk_multiplier=2.0,
            volatility_threshold_multiplier=2.0,
            high_volatility_size_reduction=0.5,
            high_volatility_stop_pct=0.03,
        )
        candles = _flat_candles(10, price=1.1000)
        cfg = BacktestConfig(
            instrument="EUR_USD",
            interval="1h",
            start_date=candles[0].time,
            end_date=candles[-1].time,
            initial_equity=100_000.0,
            pessimistic=False,
        )
        result = run_backtest(
            candles=candles,
            signal_generator=_AlwaysBuyGenerator(),
            generator_config=_default_generator_config(),
            fill_config=_eur_fill_config(),
            risk_config=risk_cfg,
            config=cfg,
        )
        # All trades should be closed
        for trade in result.trades:
            assert trade.exit_time is not None
            assert trade.exit_price is not None
        # Last trade should be closed with end_of_data reason
        end_trades = [t for t in result.trades if t.exit_reason == "end_of_data"]
        assert len(end_trades) >= 1


# ---------------------------------------------------------------------------
# Equity curve
# ---------------------------------------------------------------------------


class TestEquityCurve:
    def test_equity_curve_length_matches_candles(self) -> None:
        """Equity curve has one entry per bar."""
        candles = _flat_candles(20)
        cfg = BacktestConfig(
            instrument="EUR_USD",
            interval="1h",
            start_date=candles[0].time,
            end_date=candles[-1].time,
            initial_equity=100_000.0,
            pessimistic=False,
        )
        result = run_backtest(
            candles=candles,
            signal_generator=_NeutralGenerator(),
            generator_config=_default_generator_config(),
            fill_config=_eur_fill_config(),
            risk_config=_default_risk_config(),
            config=cfg,
        )
        assert len(result.equity_curve) == len(candles)

    def test_equity_curve_starts_at_initial(self) -> None:
        """First equity value is initial equity."""
        candles = _flat_candles(20)
        cfg = BacktestConfig(
            instrument="EUR_USD",
            interval="1h",
            start_date=candles[0].time,
            end_date=candles[-1].time,
            initial_equity=100_000.0,
            pessimistic=False,
        )
        result = run_backtest(
            candles=candles,
            signal_generator=_NeutralGenerator(),
            generator_config=_default_generator_config(),
            fill_config=_eur_fill_config(),
            risk_config=_default_risk_config(),
            config=cfg,
        )
        assert result.equity_curve[0][1] == pytest.approx(100_000.0)


# ---------------------------------------------------------------------------
# Commission and slippage tracking
# ---------------------------------------------------------------------------


class TestCostTracking:
    def test_trade_records_costs(self) -> None:
        """Trades carry slippage and spread costs from SimulatedFill."""
        candles = _rising_candles(50)
        cfg = BacktestConfig(
            instrument="EUR_USD",
            interval="1h",
            start_date=candles[0].time,
            end_date=candles[-1].time,
            initial_equity=100_000.0,
            pessimistic=False,
        )
        result = run_backtest(
            candles=candles,
            signal_generator=_AlwaysBuyGenerator(),
            generator_config=_default_generator_config(),
            fill_config=_eur_fill_config(),
            risk_config=_default_risk_config(),
            config=cfg,
        )
        assert result.trade_count >= 1
        trade = result.trades[0]
        # EUR/USD has non-zero slippage and spread costs
        assert trade.slippage_cost >= 0
        assert trade.spread_cost >= 0


# ---------------------------------------------------------------------------
# Pessimistic mode
# ---------------------------------------------------------------------------


class TestPessimisticMode:
    def test_pessimistic_flag_propagated(self) -> None:
        """Pessimistic mode results in higher costs."""
        candles = _rising_candles(50)
        normal_cfg = BacktestConfig(
            instrument="EUR_USD",
            interval="1h",
            start_date=candles[0].time,
            end_date=candles[-1].time,
            initial_equity=100_000.0,
            pessimistic=False,
        )
        pessimistic_cfg = BacktestConfig(
            instrument="EUR_USD",
            interval="1h",
            start_date=candles[0].time,
            end_date=candles[-1].time,
            initial_equity=100_000.0,
            pessimistic=True,
        )
        normal_result = run_backtest(
            candles=candles,
            signal_generator=_AlwaysBuyGenerator(),
            generator_config=_default_generator_config(),
            fill_config=_eur_fill_config(pessimistic=False),
            risk_config=_default_risk_config(),
            config=normal_cfg,
        )
        pessimistic_result = run_backtest(
            candles=candles,
            signal_generator=_AlwaysBuyGenerator(),
            generator_config=_default_generator_config(),
            fill_config=_eur_fill_config(pessimistic=True),
            risk_config=_default_risk_config(),
            config=pessimistic_cfg,
        )
        # Both should have trades
        assert normal_result.trade_count >= 1
        assert pessimistic_result.trade_count >= 1
        # Pessimistic should have higher entry costs on first trade
        n_cost = normal_result.trades[0].slippage_cost + normal_result.trades[0].spread_cost
        p_cost = (
            pessimistic_result.trades[0].slippage_cost
            + pessimistic_result.trades[0].spread_cost
        )
        assert p_cost > n_cost
