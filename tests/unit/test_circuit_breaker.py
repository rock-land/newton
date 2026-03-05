"""Tests for circuit breaker system (T-505, SPEC §6.5)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from src.trading.circuit_breaker import (
    BreakerState,
    BreakerTrip,
    CircuitBreakerManager,
    CircuitBreakerSnapshot,
    _rolling_sharpe,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(UTC)


# ---------------------------------------------------------------------------
# BreakerState model tests
# ---------------------------------------------------------------------------


class TestBreakerState:
    def test_frozen(self) -> None:
        state = BreakerState(
            name="daily_loss", tripped=False, tripped_at=None,
            reason="", scope="instrument",
        )
        with pytest.raises(AttributeError):
            state.tripped = True  # type: ignore[misc]

    def test_fields(self) -> None:
        now = _now()
        state = BreakerState(
            name="kill_switch", tripped=True, tripped_at=now,
            reason="manual", scope="system",
        )
        assert state.name == "kill_switch"
        assert state.tripped is True
        assert state.tripped_at == now
        assert state.scope == "system"


# ---------------------------------------------------------------------------
# CircuitBreakerSnapshot tests
# ---------------------------------------------------------------------------


class TestCircuitBreakerSnapshot:
    def test_frozen(self) -> None:
        snap = CircuitBreakerSnapshot(
            instrument_breakers={}, portfolio_breakers=[],
            system_breakers=[], any_tripped=False,
        )
        with pytest.raises(AttributeError):
            snap.any_tripped = True  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Daily loss breaker
# ---------------------------------------------------------------------------


class TestDailyLossBreaker:
    def test_no_trip_when_within_limit(self) -> None:
        mgr = CircuitBreakerManager()
        mgr.update_equity(
            instrument="EUR_USD", day_open_equity=100_000.0,
            current_equity=99_000.0, ath_equity=100_000.0,
            daily_loss_limit_pct=0.02, max_drawdown_pct=0.20,
        )
        assert mgr.is_entry_allowed("EUR_USD")

    def test_trips_at_threshold(self) -> None:
        mgr = CircuitBreakerManager()
        mgr.update_equity(
            instrument="EUR_USD", day_open_equity=100_000.0,
            current_equity=98_000.0, ath_equity=100_000.0,
            daily_loss_limit_pct=0.02, max_drawdown_pct=0.20,
        )
        assert not mgr.is_entry_allowed("EUR_USD")

    def test_trips_beyond_threshold(self) -> None:
        mgr = CircuitBreakerManager()
        mgr.update_equity(
            instrument="EUR_USD", day_open_equity=100_000.0,
            current_equity=97_000.0, ath_equity=100_000.0,
            daily_loss_limit_pct=0.02, max_drawdown_pct=0.20,
        )
        assert not mgr.is_entry_allowed("EUR_USD")

    def test_auto_reset_daily(self) -> None:
        mgr = CircuitBreakerManager()
        mgr.update_equity(
            instrument="EUR_USD", day_open_equity=100_000.0,
            current_equity=97_000.0, ath_equity=100_000.0,
            daily_loss_limit_pct=0.02, max_drawdown_pct=0.20,
        )
        assert not mgr.is_entry_allowed("EUR_USD")
        mgr.reset_daily()
        assert mgr.is_entry_allowed("EUR_USD")

    def test_portfolio_scope(self) -> None:
        """Daily loss also trips at portfolio level."""
        mgr = CircuitBreakerManager()
        mgr.update_equity(
            instrument="EUR_USD", day_open_equity=100_000.0,
            current_equity=97_000.0, ath_equity=100_000.0,
            daily_loss_limit_pct=0.02, max_drawdown_pct=0.20,
        )
        snap = mgr.get_snapshot()
        portfolio_daily = [b for b in snap.portfolio_breakers if b.name == "daily_loss"]
        assert len(portfolio_daily) == 1
        assert portfolio_daily[0].tripped


# ---------------------------------------------------------------------------
# Max drawdown breaker
# ---------------------------------------------------------------------------


class TestMaxDrawdownBreaker:
    def test_no_trip_within_limit(self) -> None:
        mgr = CircuitBreakerManager()
        # 15% drawdown < 20% limit; daily_loss_limit high to avoid that trigger
        mgr.update_equity(
            instrument="EUR_USD", day_open_equity=100_000.0,
            current_equity=85_000.0, ath_equity=100_000.0,
            daily_loss_limit_pct=0.20, max_drawdown_pct=0.20,
        )
        assert mgr.is_entry_allowed("EUR_USD")

    def test_trips_at_threshold(self) -> None:
        mgr = CircuitBreakerManager()
        mgr.update_equity(
            instrument="EUR_USD", day_open_equity=100_000.0,
            current_equity=80_000.0, ath_equity=100_000.0,
            daily_loss_limit_pct=0.02, max_drawdown_pct=0.20,
        )
        assert not mgr.is_entry_allowed("EUR_USD")

    def test_manual_reset_only(self) -> None:
        """Daily reset does NOT clear max drawdown."""
        mgr = CircuitBreakerManager()
        mgr.update_equity(
            instrument="EUR_USD", day_open_equity=100_000.0,
            current_equity=79_000.0, ath_equity=100_000.0,
            daily_loss_limit_pct=0.02, max_drawdown_pct=0.20,
        )
        mgr.reset_daily()
        assert not mgr.is_entry_allowed("EUR_USD")

    def test_manual_reset_clears(self) -> None:
        mgr = CircuitBreakerManager()
        # High daily_loss_limit so only max_drawdown trips
        mgr.update_equity(
            instrument="EUR_USD", day_open_equity=100_000.0,
            current_equity=79_000.0, ath_equity=100_000.0,
            daily_loss_limit_pct=0.50, max_drawdown_pct=0.20,
        )
        mgr.reset_max_drawdown("EUR_USD")
        assert mgr.is_entry_allowed("EUR_USD")

    def test_manual_reset_all(self) -> None:
        """reset_max_drawdown(None) resets all instruments."""
        mgr = CircuitBreakerManager()
        for inst in ("EUR_USD", "BTC_USD"):
            mgr.update_equity(
                instrument=inst, day_open_equity=100_000.0,
                current_equity=79_000.0, ath_equity=100_000.0,
                daily_loss_limit_pct=0.50, max_drawdown_pct=0.20,
            )
        mgr.reset_max_drawdown(None)
        assert mgr.is_entry_allowed("EUR_USD")
        assert mgr.is_entry_allowed("BTC_USD")


# ---------------------------------------------------------------------------
# Consecutive losses breaker
# ---------------------------------------------------------------------------


class TestConsecutiveLossesBreaker:
    def test_no_trip_below_threshold(self) -> None:
        mgr = CircuitBreakerManager()
        for _ in range(4):
            mgr.record_trade_result("EUR_USD", pnl=-100.0)
        assert mgr.is_entry_allowed("EUR_USD")

    def test_trips_at_threshold(self) -> None:
        mgr = CircuitBreakerManager()
        for _ in range(5):
            mgr.record_trade_result("EUR_USD", pnl=-100.0, consecutive_loss_halt=5)
        assert not mgr.is_entry_allowed("EUR_USD")

    def test_win_resets_streak(self) -> None:
        mgr = CircuitBreakerManager()
        for _ in range(4):
            mgr.record_trade_result("EUR_USD", pnl=-100.0)
        mgr.record_trade_result("EUR_USD", pnl=200.0)
        for _ in range(4):
            mgr.record_trade_result("EUR_USD", pnl=-100.0)
        assert mgr.is_entry_allowed("EUR_USD")

    def test_auto_reset_after_timeout(self) -> None:
        mgr = CircuitBreakerManager()
        for _ in range(5):
            mgr.record_trade_result("EUR_USD", pnl=-100.0, consecutive_loss_halt=5)
        # Manually backdate the tripped_at time
        mgr._consecutive_loss_tripped_at["EUR_USD"] = _now() - timedelta(hours=25)
        mgr.try_auto_reset_consecutive(consecutive_loss_halt_hours=24)
        assert mgr.is_entry_allowed("EUR_USD")

    def test_no_reset_before_timeout(self) -> None:
        mgr = CircuitBreakerManager()
        for _ in range(5):
            mgr.record_trade_result("EUR_USD", pnl=-100.0, consecutive_loss_halt=5)
        mgr._consecutive_loss_tripped_at["EUR_USD"] = _now() - timedelta(hours=23)
        mgr.try_auto_reset_consecutive(consecutive_loss_halt_hours=24)
        assert not mgr.is_entry_allowed("EUR_USD")

    def test_per_instrument_isolation(self) -> None:
        """Consecutive losses for EUR_USD don't affect BTC_USD."""
        mgr = CircuitBreakerManager()
        for _ in range(5):
            mgr.record_trade_result("EUR_USD", pnl=-100.0, consecutive_loss_halt=5)
        assert mgr.is_entry_allowed("BTC_USD")


# ---------------------------------------------------------------------------
# Model degradation breaker
# ---------------------------------------------------------------------------


class TestModelDegradationBreaker:
    def test_no_trip_positive_sharpe(self) -> None:
        mgr = CircuitBreakerManager()
        for _ in range(30):
            mgr.record_trade_result(
                "EUR_USD", pnl=100.0, consecutive_loss_halt=100,
            )
        assert mgr.is_entry_allowed("EUR_USD")

    def test_trips_negative_sharpe(self) -> None:
        mgr = CircuitBreakerManager()
        # Mostly losses → negative Sharpe
        for _ in range(25):
            mgr.record_trade_result(
                "EUR_USD", pnl=-100.0, consecutive_loss_halt=100,
            )
        for _ in range(5):
            mgr.record_trade_result(
                "EUR_USD", pnl=50.0, consecutive_loss_halt=100,
            )
        assert not mgr.is_entry_allowed("EUR_USD")

    def test_auto_reset_when_sharpe_recovers(self) -> None:
        mgr = CircuitBreakerManager()
        for _ in range(25):
            mgr.record_trade_result(
                "EUR_USD", pnl=-100.0, consecutive_loss_halt=100,
            )
        for _ in range(5):
            mgr.record_trade_result(
                "EUR_USD", pnl=50.0, consecutive_loss_halt=100,
            )
        assert not mgr.is_entry_allowed("EUR_USD")
        # Add enough wins to make Sharpe positive
        for _ in range(30):
            mgr.record_trade_result(
                "EUR_USD", pnl=200.0, consecutive_loss_halt=100,
            )
        assert mgr.is_entry_allowed("EUR_USD")

    def test_not_triggered_below_30_trades(self) -> None:
        """Model degradation requires at least 30 trades."""
        mgr = CircuitBreakerManager()
        for _ in range(29):
            mgr.record_trade_result(
                "EUR_USD", pnl=-100.0, consecutive_loss_halt=100,
            )
        assert mgr.is_entry_allowed("EUR_USD")


# ---------------------------------------------------------------------------
# Kill switch
# ---------------------------------------------------------------------------


class TestKillSwitch:
    def test_inactive_by_default(self) -> None:
        mgr = CircuitBreakerManager()
        assert not mgr.is_kill_switch_active()
        assert mgr.is_entry_allowed("EUR_USD")

    def test_activate(self) -> None:
        mgr = CircuitBreakerManager()
        mgr.activate_kill_switch("emergency stop")
        assert mgr.is_kill_switch_active()
        assert not mgr.is_entry_allowed("EUR_USD")
        assert not mgr.is_entry_allowed("BTC_USD")

    def test_deactivate(self) -> None:
        mgr = CircuitBreakerManager()
        mgr.activate_kill_switch("test")
        mgr.deactivate_kill_switch()
        assert not mgr.is_kill_switch_active()
        assert mgr.is_entry_allowed("EUR_USD")

    def test_daily_reset_does_not_clear_kill_switch(self) -> None:
        mgr = CircuitBreakerManager()
        mgr.activate_kill_switch("test")
        mgr.reset_daily()
        assert mgr.is_kill_switch_active()

    def test_system_scope_in_snapshot(self) -> None:
        mgr = CircuitBreakerManager()
        mgr.activate_kill_switch("emergency")
        snap = mgr.get_snapshot()
        assert snap.any_tripped
        assert len(snap.system_breakers) == 1
        assert snap.system_breakers[0].name == "kill_switch"
        assert snap.system_breakers[0].scope == "system"


# ---------------------------------------------------------------------------
# Snapshot and is_entry_allowed aggregation
# ---------------------------------------------------------------------------


class TestSnapshotAndAggregation:
    def test_empty_manager_allows_entry(self) -> None:
        mgr = CircuitBreakerManager()
        assert mgr.is_entry_allowed("EUR_USD")
        snap = mgr.get_snapshot()
        assert not snap.any_tripped

    def test_multiple_breakers_tripped(self) -> None:
        """Both daily loss and consecutive losses tripped."""
        mgr = CircuitBreakerManager()
        mgr.update_equity(
            instrument="EUR_USD", day_open_equity=100_000.0,
            current_equity=97_000.0, ath_equity=100_000.0,
            daily_loss_limit_pct=0.02, max_drawdown_pct=0.20,
        )
        for _ in range(5):
            mgr.record_trade_result(
                "EUR_USD", pnl=-100.0, consecutive_loss_halt=5,
            )
        assert not mgr.is_entry_allowed("EUR_USD")
        snap = mgr.get_snapshot()
        assert snap.any_tripped
        eur_breakers = snap.instrument_breakers.get("EUR_USD", [])
        tripped_names = {b.name for b in eur_breakers if b.tripped}
        assert "daily_loss" in tripped_names
        assert "consecutive_losses" in tripped_names

    def test_snapshot_includes_all_instruments(self) -> None:
        mgr = CircuitBreakerManager()
        mgr.update_equity(
            instrument="EUR_USD", day_open_equity=100_000.0,
            current_equity=99_000.0, ath_equity=100_000.0,
            daily_loss_limit_pct=0.02, max_drawdown_pct=0.20,
        )
        mgr.update_equity(
            instrument="BTC_USD", day_open_equity=50_000.0,
            current_equity=49_000.0, ath_equity=50_000.0,
            daily_loss_limit_pct=0.02, max_drawdown_pct=0.20,
        )
        snap = mgr.get_snapshot()
        assert "EUR_USD" in snap.instrument_breakers
        assert "BTC_USD" in snap.instrument_breakers

    def test_zero_equity_safe(self) -> None:
        """Zero day-open equity doesn't cause division by zero."""
        mgr = CircuitBreakerManager()
        mgr.update_equity(
            instrument="EUR_USD", day_open_equity=0.0,
            current_equity=0.0, ath_equity=0.0,
            daily_loss_limit_pct=0.02, max_drawdown_pct=0.20,
        )
        assert mgr.is_entry_allowed("EUR_USD")

    def test_instrument_daily_loss_without_portfolio(self) -> None:
        """Cover instrument-level daily_loss return (line 259).

        Directly set instrument state without portfolio flag to exercise
        the defensive guard.
        """
        mgr = CircuitBreakerManager()
        state = mgr._instruments["EUR_USD"]
        state.daily_loss_tripped = True
        state.daily_loss_reason = "direct set"
        assert not mgr.is_entry_allowed("EUR_USD")

    def test_instrument_max_drawdown_without_portfolio(self) -> None:
        """Cover instrument-level max_drawdown return (line 262).

        Directly set instrument state without portfolio flag to exercise
        the defensive guard.
        """
        mgr = CircuitBreakerManager()
        state = mgr._instruments["EUR_USD"]
        state.max_drawdown_tripped = True
        state.max_drawdown_reason = "direct set"
        assert not mgr.is_entry_allowed("EUR_USD")

    def test_rolling_sharpe_empty_deque(self) -> None:
        """Cover _rolling_sharpe guard for empty input."""
        from collections import deque

        assert _rolling_sharpe(deque()) == 0.0


# ---------------------------------------------------------------------------
# Daily loss latching (SPEC §6.5)
# ---------------------------------------------------------------------------


class TestDailyLossLatching:
    def test_daily_loss_does_not_auto_untrip_on_recovery(self) -> None:
        """Daily loss breaker stays tripped even when equity recovers (§6.5)."""
        mgr = CircuitBreakerManager()
        # Trip the breaker
        mgr.update_equity(
            instrument="EUR_USD", day_open_equity=100_000.0,
            current_equity=97_000.0, ath_equity=100_000.0,
            daily_loss_limit_pct=0.02, max_drawdown_pct=0.20,
        )
        assert not mgr.is_entry_allowed("EUR_USD")

        # Equity recovers — breaker should still be tripped
        mgr.update_equity(
            instrument="EUR_USD", day_open_equity=100_000.0,
            current_equity=100_000.0, ath_equity=100_000.0,
            daily_loss_limit_pct=0.02, max_drawdown_pct=0.20,
        )
        assert not mgr.is_entry_allowed("EUR_USD")

        # Only reset_daily clears it
        mgr.reset_daily()
        assert mgr.is_entry_allowed("EUR_USD")


# ---------------------------------------------------------------------------
# BreakerTrip returns from update_equity
# ---------------------------------------------------------------------------


class TestBreakerTripReturns:
    def test_breaker_trip_frozen(self) -> None:
        trip = BreakerTrip(name="daily_loss", instrument="EUR_USD", action="close_positions")
        with pytest.raises(AttributeError):
            trip.name = "other"  # type: ignore[misc]

    def test_daily_loss_returns_close_positions(self) -> None:
        """Daily loss trip returns BreakerTrip with action='close_positions'."""
        mgr = CircuitBreakerManager()
        trips = mgr.update_equity(
            instrument="EUR_USD", day_open_equity=100_000.0,
            current_equity=97_000.0, ath_equity=100_000.0,
            daily_loss_limit_pct=0.02, max_drawdown_pct=0.20,
        )
        assert len(trips) >= 1
        daily = [t for t in trips if t.name == "daily_loss"]
        assert len(daily) == 1
        assert daily[0].action == "close_positions"
        assert daily[0].instrument == "EUR_USD"

    def test_max_drawdown_returns_close_all(self) -> None:
        """Max drawdown trip returns BreakerTrip with action='close_all'."""
        mgr = CircuitBreakerManager()
        trips = mgr.update_equity(
            instrument="EUR_USD", day_open_equity=100_000.0,
            current_equity=79_000.0, ath_equity=100_000.0,
            daily_loss_limit_pct=0.50, max_drawdown_pct=0.20,
        )
        dd_trips = [t for t in trips if t.name == "max_drawdown"]
        assert len(dd_trips) == 1
        assert dd_trips[0].action == "close_all"

    def test_no_trip_returns_empty_list(self) -> None:
        """No breaker tripped returns empty list."""
        mgr = CircuitBreakerManager()
        trips = mgr.update_equity(
            instrument="EUR_USD", day_open_equity=100_000.0,
            current_equity=99_500.0, ath_equity=100_000.0,
            daily_loss_limit_pct=0.02, max_drawdown_pct=0.20,
        )
        assert trips == []

    def test_already_tripped_no_duplicate_trip(self) -> None:
        """Second call with same conditions doesn't return duplicate trips."""
        mgr = CircuitBreakerManager()
        trips1 = mgr.update_equity(
            instrument="EUR_USD", day_open_equity=100_000.0,
            current_equity=97_000.0, ath_equity=100_000.0,
            daily_loss_limit_pct=0.02, max_drawdown_pct=0.20,
        )
        trips2 = mgr.update_equity(
            instrument="EUR_USD", day_open_equity=100_000.0,
            current_equity=96_000.0, ath_equity=100_000.0,
            daily_loss_limit_pct=0.02, max_drawdown_pct=0.20,
        )
        assert len(trips1) >= 1
        assert len(trips2) == 0  # Already tripped, no new trips
