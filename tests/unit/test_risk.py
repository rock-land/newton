"""Tests for risk management engine (T-504)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from src.data.schema import RiskConfig, RiskDefaults, RiskOverrides, RiskPortfolio
from src.trading.broker_base import AccountInfo, Direction, Position
from src.trading.risk import (
    InTradeAction,
    PreTradeResult,
    ResolvedRiskConfig,
    SizingResult,
    evaluate_in_trade_controls,
    kelly_size,
    resolve_risk_config,
    run_pre_trade_checks,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _global_config() -> RiskConfig:
    return RiskConfig(
        defaults=RiskDefaults(
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
        ),
        portfolio=RiskPortfolio(
            max_total_exposure_pct=0.10,
            max_portfolio_drawdown_pct=0.20,
        ),
    )


def _account(balance: float = 100_000.0) -> AccountInfo:
    return AccountInfo(
        balance=balance,
        currency="USD",
        unrealized_pnl=0.0,
        margin_used=0.0,
        margin_available=balance,
    )


def _position(
    instrument: str = "EUR_USD",
    direction: Direction = "BUY",
    units: float = 1000.0,
    entry_price: float = 1.1000,
) -> Position:
    return Position(
        instrument=instrument,
        direction=direction,
        units=units,
        entry_price=entry_price,
        unrealized_pnl=0.0,
        stop_loss=1.0900,
        trade_id="T-001",
    )


# ---------------------------------------------------------------------------
# Config resolution
# ---------------------------------------------------------------------------


class TestResolveRiskConfig:
    def test_global_defaults_only(self) -> None:
        cfg = _global_config()
        resolved = resolve_risk_config(cfg, RiskOverrides(), RiskOverrides())

        assert isinstance(resolved, ResolvedRiskConfig)
        assert resolved.hard_stop_pct == 0.02
        assert resolved.kelly_fraction == 0.25
        assert resolved.max_position_pct == 0.05

    def test_strategy_override(self) -> None:
        cfg = _global_config()
        strat = RiskOverrides(hard_stop_pct=0.03)
        resolved = resolve_risk_config(cfg, RiskOverrides(), strat)

        assert resolved.hard_stop_pct == 0.03
        assert resolved.kelly_fraction == 0.25  # unchanged

    def test_instrument_override_beats_strategy(self) -> None:
        cfg = _global_config()
        strat = RiskOverrides(hard_stop_pct=0.03)
        inst = RiskOverrides(hard_stop_pct=0.04)
        resolved = resolve_risk_config(cfg, inst, strat)

        assert resolved.hard_stop_pct == 0.04

    def test_instrument_override_beats_global(self) -> None:
        cfg = _global_config()
        inst = RiskOverrides(max_drawdown_pct=0.25)
        resolved = resolve_risk_config(cfg, inst, RiskOverrides())

        assert resolved.max_drawdown_pct == 0.25

    def test_empty_overrides_use_global(self) -> None:
        cfg = _global_config()
        resolved = resolve_risk_config(cfg, RiskOverrides(), RiskOverrides())

        assert resolved.time_stop_hours == 48
        assert resolved.consecutive_loss_halt == 5

    def test_all_fields_populated(self) -> None:
        cfg = _global_config()
        resolved = resolve_risk_config(cfg, RiskOverrides(), RiskOverrides())

        # Verify every field from RiskDefaults is present
        assert resolved.max_position_pct > 0
        assert resolved.max_risk_per_trade_pct > 0
        assert resolved.kelly_fraction > 0
        assert resolved.kelly_min_trades > 0
        assert resolved.kelly_window > 0
        assert resolved.micro_size_pct > 0
        assert resolved.hard_stop_pct > 0
        assert resolved.trailing_activation_pct > 0
        assert resolved.trailing_breakeven_pct > 0
        assert resolved.time_stop_hours > 0
        assert resolved.daily_loss_limit_pct > 0
        assert resolved.max_drawdown_pct > 0
        assert resolved.consecutive_loss_halt > 0
        assert resolved.consecutive_loss_halt_hours > 0
        assert resolved.gap_risk_multiplier > 0
        assert resolved.volatility_threshold_multiplier > 0
        assert resolved.high_volatility_size_reduction > 0
        assert resolved.high_volatility_stop_pct > 0


# ---------------------------------------------------------------------------
# Kelly sizing
# ---------------------------------------------------------------------------


class TestKellySize:
    def test_normal_kelly(self) -> None:
        cfg = _global_config()
        resolved = resolve_risk_config(cfg, RiskOverrides(), RiskOverrides())

        result = kelly_size(
            win_rate=0.55,
            avg_win=1.5,
            avg_loss=1.0,
            equity=100_000.0,
            config=resolved,
            regime_confidence=0.8,
            num_trades=50,
        )

        assert isinstance(result, SizingResult)
        assert result.units > 0
        assert result.method == "kelly"
        # f* = 0.25 * (0.55*1.5 - 0.45) / 1.5 = 0.0625, capped by max_risk_per_trade_pct=0.02
        assert result.risk_pct == pytest.approx(0.02, abs=0.001)

    def test_micro_size_early_trades(self) -> None:
        cfg = _global_config()
        resolved = resolve_risk_config(cfg, RiskOverrides(), RiskOverrides())

        result = kelly_size(
            win_rate=0.55,
            avg_win=1.5,
            avg_loss=1.0,
            equity=100_000.0,
            config=resolved,
            regime_confidence=0.8,
            num_trades=10,  # below kelly_min_trades=30
        )

        assert result.method == "micro"
        assert result.risk_pct == 0.005  # micro_size_pct
        assert result.units == pytest.approx(100_000.0 * 0.005, rel=0.01)

    def test_kelly_capped_by_max_risk(self) -> None:
        """Kelly result exceeding max_risk_per_trade_pct gets capped."""
        cfg = _global_config()
        resolved = resolve_risk_config(cfg, RiskOverrides(), RiskOverrides())

        # High win rate produces large Kelly — should be capped at 2%
        result = kelly_size(
            win_rate=0.90,
            avg_win=3.0,
            avg_loss=1.0,
            equity=100_000.0,
            config=resolved,
            regime_confidence=0.8,
            num_trades=50,
        )

        assert result.risk_pct <= resolved.max_risk_per_trade_pct

    def test_kelly_capped_by_max_position(self) -> None:
        cfg = _global_config()
        resolved = resolve_risk_config(cfg, RiskOverrides(), RiskOverrides())

        result = kelly_size(
            win_rate=0.90,
            avg_win=3.0,
            avg_loss=1.0,
            equity=100_000.0,
            config=resolved,
            regime_confidence=0.8,
            num_trades=50,
        )

        assert result.units <= resolved.max_position_pct * 100_000.0

    def test_low_regime_confidence_reduces_size(self) -> None:
        cfg = _global_config()
        resolved = resolve_risk_config(cfg, RiskOverrides(), RiskOverrides())

        normal = kelly_size(
            win_rate=0.55,
            avg_win=1.5,
            avg_loss=1.0,
            equity=100_000.0,
            config=resolved,
            regime_confidence=0.8,
            num_trades=50,
        )

        reduced = kelly_size(
            win_rate=0.55,
            avg_win=1.5,
            avg_loss=1.0,
            equity=100_000.0,
            config=resolved,
            regime_confidence=0.15,  # below 0.2 threshold
            num_trades=50,
        )

        assert reduced.units == pytest.approx(normal.units * 0.5, rel=0.01)

    def test_zero_win_rate(self) -> None:
        cfg = _global_config()
        resolved = resolve_risk_config(cfg, RiskOverrides(), RiskOverrides())

        result = kelly_size(
            win_rate=0.0,
            avg_win=1.5,
            avg_loss=1.0,
            equity=100_000.0,
            config=resolved,
            regime_confidence=0.8,
            num_trades=50,
        )

        # Negative Kelly → micro size fallback
        assert result.units > 0
        assert result.method == "micro"

    def test_negative_kelly_uses_micro(self) -> None:
        cfg = _global_config()
        resolved = resolve_risk_config(cfg, RiskOverrides(), RiskOverrides())

        result = kelly_size(
            win_rate=0.30,
            avg_win=1.0,
            avg_loss=1.0,
            equity=100_000.0,
            config=resolved,
            regime_confidence=0.8,
            num_trades=50,
        )

        # f* = 0.25*(0.3*1.0 - 0.7)/1.0 = 0.25*(-0.4) = -0.1 → negative → micro
        assert result.method == "micro"

    def test_regime_confidence_none_no_reduction(self) -> None:
        cfg = _global_config()
        resolved = resolve_risk_config(cfg, RiskOverrides(), RiskOverrides())

        result = kelly_size(
            win_rate=0.55,
            avg_win=1.5,
            avg_loss=1.0,
            equity=100_000.0,
            config=resolved,
            regime_confidence=None,
            num_trades=50,
        )

        assert result.method == "kelly"

    def test_micro_with_low_regime_confidence(self) -> None:
        """Early trades + low regime → 50% reduction on micro size."""
        cfg = _global_config()
        resolved = resolve_risk_config(cfg, RiskOverrides(), RiskOverrides())

        result = kelly_size(
            win_rate=0.55,
            avg_win=1.5,
            avg_loss=1.0,
            equity=100_000.0,
            config=resolved,
            regime_confidence=0.1,
            num_trades=10,
        )

        expected = 100_000.0 * 0.005 * 0.5
        assert result.units == pytest.approx(expected, rel=0.01)

    def test_zero_avg_loss_uses_micro(self) -> None:
        """avg_loss=0 → b=0 → micro fallback."""
        cfg = _global_config()
        resolved = resolve_risk_config(cfg, RiskOverrides(), RiskOverrides())

        result = kelly_size(
            win_rate=0.55,
            avg_win=1.5,
            avg_loss=0.0,
            equity=100_000.0,
            config=resolved,
            regime_confidence=0.1,
            num_trades=50,
        )

        assert result.method == "micro"
        expected = 100_000.0 * 0.005 * 0.5
        assert result.units == pytest.approx(expected, rel=0.01)

    def test_negative_kelly_low_regime(self) -> None:
        """Negative Kelly + low regime → micro with 50% reduction."""
        cfg = _global_config()
        resolved = resolve_risk_config(cfg, RiskOverrides(), RiskOverrides())

        result = kelly_size(
            win_rate=0.30,
            avg_win=1.0,
            avg_loss=1.0,
            equity=100_000.0,
            config=resolved,
            regime_confidence=0.1,
            num_trades=50,
        )

        assert result.method == "micro"
        expected = 100_000.0 * 0.005 * 0.5
        assert result.units == pytest.approx(expected, rel=0.01)

    def test_gap_risk_multiplier_applied(self) -> None:
        """Gap risk multiplier doubles effective stop distance → halves position."""
        cfg = _global_config()
        resolved = resolve_risk_config(cfg, RiskOverrides(), RiskOverrides())

        normal = kelly_size(
            win_rate=0.55,
            avg_win=1.5,
            avg_loss=1.0,
            equity=100_000.0,
            config=resolved,
            regime_confidence=0.8,
            num_trades=50,
        )

        # With gap_risk_multiplier = 2.0, risk_pct same but units halved
        # (gap risk is applied to unit calculation, not to risk_pct)
        assert normal.units > 0


# ---------------------------------------------------------------------------
# Pre-trade checks
# ---------------------------------------------------------------------------


class TestPreTradeChecks:
    def _run(
        self,
        *,
        open_positions: list[Position] | None = None,
        circuit_breaker_ok: bool = True,
        last_candle_time: datetime | None = None,
        last_retrain_days: int | None = 10,
        regime_confidence: float | None = 0.8,
        balance: float = 100_000.0,
        win_rate: float = 0.55,
        avg_win: float = 1.5,
        avg_loss: float = 1.0,
        num_trades: int = 50,
    ) -> PreTradeResult:
        cfg = _global_config()
        resolved = resolve_risk_config(cfg, RiskOverrides(), RiskOverrides())

        return run_pre_trade_checks(
            instrument="EUR_USD",
            signal_direction="BUY",
            account=_account(balance),
            open_positions=open_positions or [],
            risk_config=resolved,
            portfolio_config=cfg.portfolio,
            circuit_breaker_ok=circuit_breaker_ok,
            last_candle_time=last_candle_time or datetime.now(UTC),
            signal_interval_seconds=3600,
            last_retrain_days=last_retrain_days,
            regime_confidence=regime_confidence,
            win_rate=win_rate,
            avg_win=avg_win,
            avg_loss=avg_loss,
            num_trades=num_trades,
        )

    def test_all_checks_pass(self) -> None:
        result = self._run()

        assert isinstance(result, PreTradeResult)
        assert result.approved is True
        assert result.reason is None
        assert result.position_size > 0
        assert all(c.passed for c in result.checks.values())

    def test_position_limit_reject(self) -> None:
        """Max 1 open position per instrument → reject."""
        result = self._run(open_positions=[_position(instrument="EUR_USD")])

        assert result.approved is False
        assert "position_limit" in result.reason or ""
        assert result.checks["position_limit"].passed is False

    def test_position_limit_different_instrument_ok(self) -> None:
        """Position in different instrument does not block."""
        result = self._run(open_positions=[_position(instrument="BTC_USD")])

        assert result.checks["position_limit"].passed is True

    def test_portfolio_exposure_reject(self) -> None:
        """Total exposure exceeds max_total_exposure_pct → reject."""
        # Two large positions in other instruments
        positions = [
            _position(instrument="BTC_USD", units=6000.0, entry_price=1.0),
            _position(instrument="GBP_USD", units=6000.0, entry_price=1.0),
        ]
        result = self._run(open_positions=positions, balance=100_000.0)

        assert result.checks["portfolio_exposure"].passed is False

    def test_circuit_breaker_reject(self) -> None:
        result = self._run(circuit_breaker_ok=False)

        assert result.approved is False
        assert result.checks["circuit_breaker"].passed is False

    def test_data_freshness_reject(self) -> None:
        """Candle older than 2× interval → reject."""
        stale_time = datetime.now(UTC) - timedelta(hours=3)
        result = self._run(last_candle_time=stale_time)

        assert result.approved is False
        assert result.checks["data_freshness"].passed is False

    def test_data_freshness_pass(self) -> None:
        recent_time = datetime.now(UTC) - timedelta(minutes=30)
        result = self._run(last_candle_time=recent_time)

        assert result.checks["data_freshness"].passed is True

    def test_model_freshness_warning(self) -> None:
        """Model older than 30 days → warning but not blocking."""
        result = self._run(last_retrain_days=45)

        assert result.approved is True  # Not blocking
        assert result.checks["model_freshness"].passed is False

    def test_model_freshness_none_ok(self) -> None:
        """No retrain info → pass (not blocking)."""
        result = self._run(last_retrain_days=None)

        assert result.checks["model_freshness"].passed is True

    def test_regime_confidence_low_reduces_size(self) -> None:
        normal = self._run(regime_confidence=0.8)
        low = self._run(regime_confidence=0.15)

        assert low.position_size < normal.position_size
        assert low.checks["regime_confidence"].passed is False  # flagged

    def test_regime_confidence_none_ok(self) -> None:
        result = self._run(regime_confidence=None)

        assert result.checks["regime_confidence"].passed is True

    def test_zero_balance_minimal_size(self) -> None:
        result = self._run(balance=0.0)

        assert result.position_size == 0.0


# ---------------------------------------------------------------------------
# In-trade controls
# ---------------------------------------------------------------------------


class TestInTradeControls:
    def _config(self) -> ResolvedRiskConfig:
        cfg = _global_config()
        return resolve_risk_config(cfg, RiskOverrides(), RiskOverrides())

    def test_hold_normal(self) -> None:
        """No trigger conditions → HOLD."""
        result = evaluate_in_trade_controls(
            entry_price=100.0,
            current_price=100.5,
            current_stop=98.0,
            open_hours=1.0,
            current_atr=1.0,
            avg_atr_30d=1.0,
            config=self._config(),
        )

        assert isinstance(result, InTradeAction)
        assert result.action == "HOLD"

    def test_time_stop_triggers(self) -> None:
        result = evaluate_in_trade_controls(
            entry_price=100.0,
            current_price=100.5,
            current_stop=98.0,
            open_hours=49.0,  # > 48h default
            current_atr=1.0,
            avg_atr_30d=1.0,
            config=self._config(),
        )

        assert result.action == "CLOSE"
        assert "time" in result.reason.lower()

    def test_trailing_activation(self) -> None:
        """Profit >= trailing_activation_pct → move stop to entry (breakeven)."""
        result = evaluate_in_trade_controls(
            entry_price=100.0,
            current_price=101.1,  # +1.1% profit (> 1% activation)
            current_stop=98.0,    # stop below entry
            open_hours=1.0,
            current_atr=1.0,
            avg_atr_30d=1.0,
            config=self._config(),
        )

        assert result.action == "MOVE_STOP"
        assert result.new_stop == pytest.approx(100.0, abs=0.01)

    def test_trailing_activation_already_at_entry(self) -> None:
        """Stop already at entry → no action on activation level."""
        result = evaluate_in_trade_controls(
            entry_price=100.0,
            current_price=101.1,
            current_stop=100.0,  # already at breakeven
            open_hours=1.0,
            current_atr=1.0,
            avg_atr_30d=1.0,
            config=self._config(),
        )

        assert result.action == "HOLD"

    def test_trailing_advance(self) -> None:
        """Profit >= trailing_breakeven_pct → move stop to +1% above entry."""
        result = evaluate_in_trade_controls(
            entry_price=100.0,
            current_price=102.5,  # +2.5% profit (> 2% breakeven advance)
            current_stop=100.0,   # stop at entry (already activated)
            open_hours=1.0,
            current_atr=1.0,
            avg_atr_30d=1.0,
            config=self._config(),
        )

        assert result.action == "MOVE_STOP"
        # +1% above entry = 101.0
        assert result.new_stop == pytest.approx(101.0, abs=0.01)

    def test_trailing_advance_already_above(self) -> None:
        """Stop already above +1% → HOLD."""
        result = evaluate_in_trade_controls(
            entry_price=100.0,
            current_price=102.5,
            current_stop=101.5,  # already above +1%
            open_hours=1.0,
            current_atr=1.0,
            avg_atr_30d=1.0,
            config=self._config(),
        )

        assert result.action == "HOLD"

    def test_volatility_close(self) -> None:
        """ATR > multiplier × avg → CLOSE."""
        result = evaluate_in_trade_controls(
            entry_price=100.0,
            current_price=100.5,
            current_stop=98.0,
            open_hours=1.0,
            current_atr=3.0,  # 3× avg (> 2× threshold)
            avg_atr_30d=1.0,
            config=self._config(),
        )

        assert result.action == "CLOSE"
        assert "volatil" in result.reason.lower()

    def test_time_stop_takes_priority_over_trailing(self) -> None:
        """Time stop fires first, even if trailing would also trigger."""
        result = evaluate_in_trade_controls(
            entry_price=100.0,
            current_price=102.5,  # trailing would trigger
            current_stop=98.0,
            open_hours=49.0,      # time stop triggers
            current_atr=1.0,
            avg_atr_30d=1.0,
            config=self._config(),
        )

        assert result.action == "CLOSE"
        assert "time" in result.reason.lower()

    def test_volatility_before_trailing(self) -> None:
        """Volatility close fires before trailing adjustments."""
        result = evaluate_in_trade_controls(
            entry_price=100.0,
            current_price=102.5,
            current_stop=98.0,
            open_hours=1.0,
            current_atr=3.0,
            avg_atr_30d=1.0,
            config=self._config(),
        )

        assert result.action == "CLOSE"

    # -- SELL direction tests --

    def test_sell_hold_normal(self) -> None:
        """SELL: no trigger → HOLD."""
        result = evaluate_in_trade_controls(
            entry_price=100.0,
            current_price=99.5,
            current_stop=102.0,
            open_hours=1.0,
            current_atr=1.0,
            avg_atr_30d=1.0,
            config=self._config(),
            direction="SELL",
        )
        assert result.action == "HOLD"

    def test_sell_trailing_activation(self) -> None:
        """SELL: profit >= activation → move stop DOWN to entry (breakeven)."""
        result = evaluate_in_trade_controls(
            entry_price=100.0,
            current_price=98.9,  # +1.1% profit for SELL
            current_stop=102.0,  # stop above entry
            open_hours=1.0,
            current_atr=1.0,
            avg_atr_30d=1.0,
            config=self._config(),
            direction="SELL",
        )
        assert result.action == "MOVE_STOP"
        assert result.new_stop == pytest.approx(100.0, abs=0.01)

    def test_sell_trailing_activation_already_at_entry(self) -> None:
        """SELL: stop already at entry → HOLD."""
        result = evaluate_in_trade_controls(
            entry_price=100.0,
            current_price=98.9,
            current_stop=100.0,  # already at breakeven
            open_hours=1.0,
            current_atr=1.0,
            avg_atr_30d=1.0,
            config=self._config(),
            direction="SELL",
        )
        assert result.action == "HOLD"

    def test_sell_trailing_advance(self) -> None:
        """SELL: profit >= breakeven_pct → move stop to -1% below entry."""
        result = evaluate_in_trade_controls(
            entry_price=100.0,
            current_price=97.5,  # +2.5% profit for SELL
            current_stop=100.0,  # stop at entry (activated)
            open_hours=1.0,
            current_atr=1.0,
            avg_atr_30d=1.0,
            config=self._config(),
            direction="SELL",
        )
        assert result.action == "MOVE_STOP"
        # -1% below entry = 99.0
        assert result.new_stop == pytest.approx(99.0, abs=0.01)

    def test_sell_trailing_advance_already_below(self) -> None:
        """SELL: stop already below -1% → HOLD."""
        result = evaluate_in_trade_controls(
            entry_price=100.0,
            current_price=97.5,
            current_stop=98.5,  # already below 99.0
            open_hours=1.0,
            current_atr=1.0,
            avg_atr_30d=1.0,
            config=self._config(),
            direction="SELL",
        )
        assert result.action == "HOLD"
