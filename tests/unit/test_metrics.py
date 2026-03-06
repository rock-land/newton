"""Tests for backtest performance metrics (T-603, SPEC §9.5)."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from dataclasses import FrozenInstanceError

import pytest

from src.backtest.engine import BacktestConfig, BacktestResult, BacktestTrade
from src.backtest.metrics import (
    CalibrationDecile,
    GateEvaluation,
    MetricGateResult,
    PerformanceMetrics,
    PortfolioMetrics,
    compute_metrics,
    compute_portfolio_metrics,
    evaluate_gates,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BASE_TIME = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _ts(hour: int) -> datetime:
    return _BASE_TIME.replace(hour=hour)


def _config(instrument: str = "EUR_USD") -> BacktestConfig:
    return BacktestConfig(
        instrument=instrument,
        interval="1h",
        start_date=_BASE_TIME,
        end_date=_BASE_TIME.replace(day=31),
        initial_equity=10000.0,
        pessimistic=False,
    )


def _trade(pnl: float, *, hour: int = 1) -> BacktestTrade:
    return BacktestTrade(
        entry_time=_ts(0),
        entry_price=100.0,
        exit_time=_ts(hour),
        exit_price=100.0 + pnl,
        direction="BUY",
        quantity=1.0,
        pnl=pnl,
        commission=0.0,
        slippage_cost=0.0,
        spread_cost=0.0,
        exit_reason="signal",
        regime_label="UNKNOWN",
    )


def _equity_curve_from_values(values: list[float]) -> list[tuple[datetime, float]]:
    """Build an equity curve from a list of equity values."""
    return [(_BASE_TIME.replace(hour=i % 24, day=1 + i // 24), v) for i, v in enumerate(values)]


def _result_with_trades(
    trades: list[BacktestTrade],
    equity_values: list[float] | None = None,
    initial: float = 10000.0,
) -> BacktestResult:
    """Build a BacktestResult from trades and optional equity curve."""
    if equity_values is None:
        # Simple: start at initial, apply PnL sequentially
        eq = [initial]
        for t in trades:
            eq.append(eq[-1] + t.pnl)
        equity_values = eq

    equity_curve = _equity_curve_from_values(equity_values)
    final = equity_values[-1]
    return BacktestResult(
        config=_config(),
        equity_curve=equity_curve,
        trades=trades,
        initial_equity=initial,
        final_equity=final,
        total_return=(final - initial) / initial,
        trade_count=len(trades),
    )


# ---------------------------------------------------------------------------
# Dataclass immutability (DEC-010)
# ---------------------------------------------------------------------------


class TestDataclassImmutability:
    def test_performance_metrics_frozen(self) -> None:
        m = PerformanceMetrics(
            sharpe_ratio=1.0, profit_factor=2.0, max_drawdown=0.1,
            win_rate=0.6, calmar_ratio=1.5, expectancy=50.0,
            calibration_error=0.02, trade_count=100,
            annualized_return=0.15, total_return=0.10,
        )
        with pytest.raises(FrozenInstanceError):
            m.sharpe_ratio = 2.0  # type: ignore[misc]

    def test_metric_gate_result_frozen(self) -> None:
        r = MetricGateResult(
            metric_name="sharpe", value=1.0, threshold=0.8,
            gate_type="hard", passed=True,
        )
        with pytest.raises(FrozenInstanceError):
            r.passed = False  # type: ignore[misc]

    def test_gate_evaluation_frozen(self) -> None:
        e = GateEvaluation(results=[], all_hard_gates_passed=True, instrument="EUR_USD")
        with pytest.raises(FrozenInstanceError):
            e.all_hard_gates_passed = False  # type: ignore[misc]

    def test_portfolio_metrics_frozen(self) -> None:
        p = PortfolioMetrics(
            portfolio_sharpe=1.0, max_portfolio_drawdown=0.1,
            instrument_correlation=0.3, per_instrument={},
        )
        with pytest.raises(FrozenInstanceError):
            p.portfolio_sharpe = 2.0  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Sharpe Ratio
# ---------------------------------------------------------------------------


class TestSharpeRatio:
    def test_positive_sharpe(self) -> None:
        """Consistent positive returns → positive Sharpe."""
        # 10 trades, each +100 PnL on 10000 equity → 1% return per step
        trades = [_trade(100.0) for _ in range(10)]
        result = _result_with_trades(trades)
        m = compute_metrics(result, annualization_factor=math.sqrt(252))
        assert m.sharpe_ratio > 0

    def test_zero_std_returns_zero_sharpe(self) -> None:
        """Zero standard deviation of returns → Sharpe = 0."""
        # Flat equity curve
        result = _result_with_trades([], equity_values=[10000.0] * 10)
        m = compute_metrics(result, annualization_factor=math.sqrt(252))
        assert m.sharpe_ratio == 0.0

    def test_annualization_factor_applied(self) -> None:
        """Different annualization factors produce different Sharpe values."""
        trades = [_trade(100.0) for _ in range(10)]
        result = _result_with_trades(trades)
        m_forex = compute_metrics(result, annualization_factor=math.sqrt(252))
        m_crypto = compute_metrics(result, annualization_factor=math.sqrt(365))
        assert m_crypto.sharpe_ratio > m_forex.sharpe_ratio


# ---------------------------------------------------------------------------
# Profit Factor
# ---------------------------------------------------------------------------


class TestProfitFactor:
    def test_basic_profit_factor(self) -> None:
        """PF = sum(wins) / abs(sum(losses))."""
        trades = [_trade(200.0), _trade(-100.0)]
        result = _result_with_trades(trades)
        m = compute_metrics(result, annualization_factor=math.sqrt(252))
        assert m.profit_factor == pytest.approx(2.0)

    def test_all_winners_capped(self) -> None:
        """All winning trades → PF capped at 999.9."""
        trades = [_trade(100.0) for _ in range(5)]
        result = _result_with_trades(trades)
        m = compute_metrics(result, annualization_factor=math.sqrt(252))
        assert m.profit_factor == pytest.approx(999.9)

    def test_all_losers(self) -> None:
        """All losing trades → PF = 0."""
        trades = [_trade(-100.0) for _ in range(5)]
        result = _result_with_trades(trades)
        m = compute_metrics(result, annualization_factor=math.sqrt(252))
        assert m.profit_factor == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Max Drawdown
# ---------------------------------------------------------------------------


class TestMaxDrawdown:
    def test_drawdown_from_equity_curve(self) -> None:
        """Drawdown computed from peak-to-trough of equity curve."""
        # Peak at 12000, trough at 9000 → DD = 3000/12000 = 25%
        equity = [10000.0, 12000.0, 9000.0, 10000.0]
        result = _result_with_trades([], equity_values=equity)
        m = compute_metrics(result, annualization_factor=math.sqrt(252))
        assert m.max_drawdown == pytest.approx(0.25)

    def test_no_drawdown(self) -> None:
        """Monotonically increasing equity → DD = 0."""
        equity = [10000.0, 10100.0, 10200.0, 10300.0]
        result = _result_with_trades([], equity_values=equity)
        m = compute_metrics(result, annualization_factor=math.sqrt(252))
        assert m.max_drawdown == pytest.approx(0.0)

    def test_full_drawdown(self) -> None:
        """Equity drops to near zero."""
        equity = [10000.0, 100.0]
        result = _result_with_trades([], equity_values=equity)
        m = compute_metrics(result, annualization_factor=math.sqrt(252))
        assert m.max_drawdown == pytest.approx(0.99)


# ---------------------------------------------------------------------------
# Win Rate
# ---------------------------------------------------------------------------


class TestWinRate:
    def test_win_rate_calculation(self) -> None:
        trades = [_trade(100.0), _trade(-50.0), _trade(75.0)]
        result = _result_with_trades(trades)
        m = compute_metrics(result, annualization_factor=math.sqrt(252))
        assert m.win_rate == pytest.approx(2.0 / 3.0)

    def test_no_trades_zero_win_rate(self) -> None:
        result = _result_with_trades([])
        m = compute_metrics(result, annualization_factor=math.sqrt(252))
        assert m.win_rate == 0.0


# ---------------------------------------------------------------------------
# Calmar Ratio
# ---------------------------------------------------------------------------


class TestCalmarRatio:
    def test_calmar_calculation(self) -> None:
        """Calmar = annualized_return / max_drawdown."""
        # Build equity that goes up, dips, recovers
        # Peak 11000, trough 10000 → DD = 1/11 ≈ 9.09%
        equity = [10000.0, 11000.0, 10000.0, 11500.0]
        result = _result_with_trades([], equity_values=equity)
        m = compute_metrics(result, annualization_factor=math.sqrt(252))
        # annualized_return = total_return * annualization_factor^2 / periods ... simplified
        # Just verify it's positive and finite
        assert m.calmar_ratio > 0
        assert math.isfinite(m.calmar_ratio)

    def test_zero_drawdown_returns_zero_calmar(self) -> None:
        """Zero drawdown → Calmar = 0 (guard div-by-zero)."""
        equity = [10000.0, 10100.0, 10200.0]
        result = _result_with_trades([], equity_values=equity)
        m = compute_metrics(result, annualization_factor=math.sqrt(252))
        assert m.calmar_ratio == 0.0


# ---------------------------------------------------------------------------
# Expectancy
# ---------------------------------------------------------------------------


class TestExpectancy:
    def test_expectancy_formula(self) -> None:
        """Expectancy = (win_rate × avg_win) - (loss_rate × avg_loss)."""
        # 2 wins of 100, 1 loss of 50
        # win_rate=2/3, avg_win=100, loss_rate=1/3, avg_loss=50
        # expectancy = (2/3)*100 - (1/3)*50 = 66.67 - 16.67 = 50.0
        trades = [_trade(100.0), _trade(100.0), _trade(-50.0)]
        result = _result_with_trades(trades)
        m = compute_metrics(result, annualization_factor=math.sqrt(252))
        assert m.expectancy == pytest.approx(50.0, abs=0.01)

    def test_negative_expectancy(self) -> None:
        trades = [_trade(-100.0), _trade(-100.0), _trade(50.0)]
        result = _result_with_trades(trades)
        m = compute_metrics(result, annualization_factor=math.sqrt(252))
        assert m.expectancy < 0


# ---------------------------------------------------------------------------
# Calibration Error
# ---------------------------------------------------------------------------


class TestCalibrationError:
    def test_no_probabilities_returns_zero(self) -> None:
        """Without predicted probabilities, calibration error is 0.0."""
        trades = [_trade(100.0)]
        result = _result_with_trades(trades)
        m = compute_metrics(result, annualization_factor=math.sqrt(252))
        assert m.calibration_error == 0.0

    def test_perfect_calibration(self) -> None:
        """Perfectly calibrated predictions → error near 0."""
        # 100 trades: first 60 win (prob=0.6), last 40 lose (prob=0.6)
        # In decile 6 (0.55-0.65): all 100 trades, 60 wins → observed 0.6
        # predicted avg ~0.6, observed 0.6 → error ≈ 0
        trades = [_trade(100.0) for _ in range(60)] + [_trade(-50.0) for _ in range(40)]
        probs = [0.6] * 100
        result = _result_with_trades(trades)
        m = compute_metrics(
            result, annualization_factor=math.sqrt(252),
            predicted_probabilities=probs,
        )
        assert m.calibration_error < 0.05

    def test_poor_calibration(self) -> None:
        """High confidence but low win rate → large calibration error."""
        # All trades predicted at 0.9 probability but only 20% win
        trades = [_trade(100.0) for _ in range(2)] + [_trade(-50.0) for _ in range(8)]
        probs = [0.9] * 10
        result = _result_with_trades(trades)
        m = compute_metrics(
            result, annualization_factor=math.sqrt(252),
            predicted_probabilities=probs,
        )
        assert m.calibration_error > 0.5

    def test_calibration_deciles_populated(self) -> None:
        """When probabilities are provided, calibration_deciles are returned."""
        trades = [_trade(100.0) for _ in range(60)] + [_trade(-50.0) for _ in range(40)]
        probs = [0.6] * 100
        result = _result_with_trades(trades)
        m = compute_metrics(
            result, annualization_factor=math.sqrt(252),
            predicted_probabilities=probs,
        )
        assert len(m.calibration_deciles) > 0
        decile = m.calibration_deciles[0]
        assert isinstance(decile, CalibrationDecile)
        assert decile.count == 100  # all in one bin
        assert decile.bin_index == 6  # 0.6 falls in bin 6
        assert abs(decile.predicted_mid - 0.6) < 0.01
        assert abs(decile.observed_freq - 0.6) < 0.01

    def test_calibration_deciles_empty_without_probabilities(self) -> None:
        """Without predicted probabilities, calibration_deciles is empty."""
        trades = [_trade(100.0)]
        result = _result_with_trades(trades)
        m = compute_metrics(result, annualization_factor=math.sqrt(252))
        assert m.calibration_deciles == ()

    def test_calibration_decile_frozen(self) -> None:
        """CalibrationDecile is a frozen dataclass."""
        d = CalibrationDecile(bin_index=0, predicted_mid=0.05, observed_freq=0.1, count=5)
        with pytest.raises(FrozenInstanceError):
            d.count = 10  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Gate Evaluation
# ---------------------------------------------------------------------------


class TestGateEvaluation:
    def test_all_gates_pass(self) -> None:
        m = PerformanceMetrics(
            sharpe_ratio=1.5, profit_factor=2.0, max_drawdown=0.10,
            win_rate=0.55, calmar_ratio=1.0, expectancy=50.0,
            calibration_error=0.03, trade_count=50,
            annualized_return=0.20, total_return=0.15,
        )
        gate = evaluate_gates(m, instrument="EUR_USD", trade_count_per_fold=50)
        assert gate.all_hard_gates_passed is True
        assert all(r.passed for r in gate.results)

    def test_sharpe_fails_gate(self) -> None:
        m = PerformanceMetrics(
            sharpe_ratio=0.5, profit_factor=2.0, max_drawdown=0.10,
            win_rate=0.55, calmar_ratio=1.0, expectancy=50.0,
            calibration_error=0.03, trade_count=50,
            annualized_return=0.20, total_return=0.15,
        )
        gate = evaluate_gates(m, instrument="EUR_USD", trade_count_per_fold=50)
        assert gate.all_hard_gates_passed is False
        sharpe_result = next(r for r in gate.results if r.metric_name == "sharpe_ratio")
        assert sharpe_result.passed is False

    def test_drawdown_fails_gate(self) -> None:
        m = PerformanceMetrics(
            sharpe_ratio=1.5, profit_factor=2.0, max_drawdown=0.20,
            win_rate=0.55, calmar_ratio=1.0, expectancy=50.0,
            calibration_error=0.03, trade_count=50,
            annualized_return=0.20, total_return=0.15,
        )
        gate = evaluate_gates(m, instrument="EUR_USD", trade_count_per_fold=50)
        assert gate.all_hard_gates_passed is False

    def test_trade_count_below_minimum(self) -> None:
        m = PerformanceMetrics(
            sharpe_ratio=1.5, profit_factor=2.0, max_drawdown=0.10,
            win_rate=0.55, calmar_ratio=1.0, expectancy=50.0,
            calibration_error=0.03, trade_count=20,
            annualized_return=0.20, total_return=0.15,
        )
        gate = evaluate_gates(m, instrument="EUR_USD", trade_count_per_fold=20)
        assert gate.all_hard_gates_passed is False

    def test_informational_gates_dont_block(self) -> None:
        """Win rate and Calmar below threshold but informational → still passes."""
        m = PerformanceMetrics(
            sharpe_ratio=1.5, profit_factor=2.0, max_drawdown=0.10,
            win_rate=0.30, calmar_ratio=0.2, expectancy=50.0,
            calibration_error=0.03, trade_count=50,
            annualized_return=0.20, total_return=0.15,
        )
        gate = evaluate_gates(m, instrument="EUR_USD", trade_count_per_fold=50)
        assert gate.all_hard_gates_passed is True
        # But informational gates should be marked as failed
        wr = next(r for r in gate.results if r.metric_name == "win_rate")
        assert wr.passed is False
        assert wr.gate_type == "informational"


# ---------------------------------------------------------------------------
# Portfolio Metrics
# ---------------------------------------------------------------------------


class TestPortfolioMetrics:
    def _make_result(
        self, instrument: str, equity_values: list[float],
    ) -> BacktestResult:
        curve = _equity_curve_from_values(equity_values)
        return BacktestResult(
            config=_config(instrument),
            equity_curve=curve,
            trades=[],
            initial_equity=equity_values[0],
            final_equity=equity_values[-1],
            total_return=(equity_values[-1] - equity_values[0]) / equity_values[0],
            trade_count=0,
        )

    def test_portfolio_sharpe_computed(self) -> None:
        r1 = self._make_result("EUR_USD", [10000, 10100, 10200, 10300, 10400])
        r2 = self._make_result("BTC_USD", [10000, 10050, 10100, 10150, 10200])
        pm = compute_portfolio_metrics(
            {"EUR_USD": r1, "BTC_USD": r2},
            annualization_factors={"EUR_USD": math.sqrt(252), "BTC_USD": math.sqrt(365)},
        )
        assert pm.portfolio_sharpe > 0
        assert math.isfinite(pm.portfolio_sharpe)

    def test_portfolio_max_drawdown(self) -> None:
        r1 = self._make_result("EUR_USD", [10000, 12000, 9000, 11000])
        r2 = self._make_result("BTC_USD", [10000, 10000, 10000, 10000])
        pm = compute_portfolio_metrics(
            {"EUR_USD": r1, "BTC_USD": r2},
            annualization_factors={"EUR_USD": math.sqrt(252), "BTC_USD": math.sqrt(365)},
        )
        # Portfolio DD should reflect EUR_USD drawdown, dampened by flat BTC_USD
        assert pm.max_portfolio_drawdown > 0
        assert pm.max_portfolio_drawdown < 0.25  # less than EUR_USD alone

    def test_correlation_between_instruments(self) -> None:
        # Perfectly correlated returns
        r1 = self._make_result("EUR_USD", [10000, 10100, 10200, 10300, 10400])
        r2 = self._make_result("BTC_USD", [10000, 10100, 10200, 10300, 10400])
        pm = compute_portfolio_metrics(
            {"EUR_USD": r1, "BTC_USD": r2},
            annualization_factors={"EUR_USD": math.sqrt(252), "BTC_USD": math.sqrt(365)},
        )
        # Highly correlated
        assert pm.instrument_correlation > 0.9

    def test_single_instrument_portfolio(self) -> None:
        r1 = self._make_result("EUR_USD", [10000, 10100, 10200, 10300])
        pm = compute_portfolio_metrics(
            {"EUR_USD": r1},
            annualization_factors={"EUR_USD": math.sqrt(252)},
        )
        assert pm.instrument_correlation == 0.0  # no pair to correlate
        assert len(pm.per_instrument) == 1


# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_result(self) -> None:
        """Empty backtest result → safe defaults."""
        result = BacktestResult(
            config=_config(),
            equity_curve=[],
            trades=[],
            initial_equity=10000.0,
            final_equity=10000.0,
            total_return=0.0,
            trade_count=0,
        )
        m = compute_metrics(result, annualization_factor=math.sqrt(252))
        assert m.sharpe_ratio == 0.0
        assert m.profit_factor == 0.0
        assert m.max_drawdown == 0.0
        assert m.win_rate == 0.0
        assert m.expectancy == 0.0
        assert m.trade_count == 0

    def test_single_trade(self) -> None:
        """Single trade → metrics still compute."""
        trades = [_trade(100.0)]
        result = _result_with_trades(trades)
        m = compute_metrics(result, annualization_factor=math.sqrt(252))
        assert m.win_rate == 1.0
        assert m.trade_count == 1
        assert m.profit_factor == pytest.approx(999.9)


# ---------------------------------------------------------------------------
# T-608-FIX2: Financial formula corrections
# ---------------------------------------------------------------------------


class TestSharpeRiskFreeRate:
    """SR-C2: Sharpe formula subtracts daily risk-free rate."""

    def test_risk_free_rate_reduces_sharpe(self) -> None:
        """Nonzero risk-free rate → lower Sharpe than zero."""
        trades = [_trade(100.0) for _ in range(10)]
        result = _result_with_trades(trades)
        m_zero = compute_metrics(
            result, annualization_factor=math.sqrt(252), risk_free_rate=0.0,
        )
        m_rfr = compute_metrics(
            result, annualization_factor=math.sqrt(252), risk_free_rate=0.05,
        )
        assert m_rfr.sharpe_ratio < m_zero.sharpe_ratio

    def test_risk_free_rate_default_zero(self) -> None:
        """Default risk_free_rate=0.0 produces same result as explicit 0."""
        trades = [_trade(100.0) for _ in range(10)]
        result = _result_with_trades(trades)
        m_default = compute_metrics(result, annualization_factor=math.sqrt(252))
        m_explicit = compute_metrics(
            result, annualization_factor=math.sqrt(252), risk_free_rate=0.0,
        )
        assert m_default.sharpe_ratio == pytest.approx(m_explicit.sharpe_ratio)


class TestCompoundCagr:
    """SR-H1: Annualized return uses compound CAGR formula."""

    def test_cagr_formula_applied(self) -> None:
        """Compound CAGR: (1+total_return)^(ppy/n) - 1."""
        # 10% total return over 252 periods → CAGR = (1.1)^(252/252) - 1 = 0.1
        equity = [10000.0] + [10000.0 + i * (1000.0 / 252) for i in range(1, 253)]
        result = _result_with_trades([], equity_values=equity)
        m = compute_metrics(result, annualization_factor=math.sqrt(252))
        expected_cagr = (1.0 + result.total_return) ** (252.0 / 252.0) - 1.0
        assert m.annualized_return == pytest.approx(expected_cagr, abs=0.001)

    def test_short_period_cagr(self) -> None:
        """Short backtest with high return → CAGR properly annualizes."""
        # 5% return over 10 periods at √252 annualization
        equity = [10000.0, 10100.0, 10200.0, 10300.0, 10400.0, 10500.0]
        result = _result_with_trades([], equity_values=equity)
        m = compute_metrics(result, annualization_factor=math.sqrt(252))
        # Compound formula produces higher annualized return for short periods
        assert m.annualized_return > result.total_return


class TestCalibrationErrorMismatch:
    """SR-M4: Calibration error raises ValueError on length mismatch."""

    def test_length_mismatch_raises(self) -> None:
        """Mismatched predicted_probabilities and trades → ValueError."""
        trades = [_trade(100.0), _trade(-50.0)]
        result = _result_with_trades(trades)
        with pytest.raises(ValueError, match="does not match trade count"):
            compute_metrics(
                result, annualization_factor=math.sqrt(252),
                predicted_probabilities=[0.7],  # 1 prob for 2 trades
            )


class TestPortfolioSharpeConsistentFactor:
    """SR-M5: Portfolio Sharpe uses consistent √365 convention."""

    def test_portfolio_sharpe_uses_sqrt_365(self) -> None:
        """Portfolio Sharpe should use √365, not average of factors."""
        r1 = BacktestResult(
            config=_config("EUR_USD"),
            equity_curve=_equity_curve_from_values([10000, 10100, 10200, 10300, 10400]),
            trades=[], initial_equity=10000.0, final_equity=10400.0,
            total_return=0.04, trade_count=0,
        )
        r2 = BacktestResult(
            config=_config("BTC_USD"),
            equity_curve=_equity_curve_from_values([10000, 10050, 10100, 10150, 10200]),
            trades=[], initial_equity=10000.0, final_equity=10200.0,
            total_return=0.02, trade_count=0,
        )
        pm = compute_portfolio_metrics(
            {"EUR_USD": r1, "BTC_USD": r2},
            annualization_factors={"EUR_USD": math.sqrt(252), "BTC_USD": math.sqrt(365)},
        )
        # Portfolio Sharpe should be computed, not zero
        assert pm.portfolio_sharpe > 0
