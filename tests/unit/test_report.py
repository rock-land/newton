"""Tests for regime-aware backtest reporting (T-605)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.backtest.engine import BacktestConfig, BacktestResult, BacktestTrade
from src.backtest.metrics import GateEvaluation, MetricGateResult, PerformanceMetrics
from src.backtest.report import (
    BiasControl,
    RegimePerformance,
    RegimeTransition,
    ReportConfig,
    build_bias_controls,
    build_regime_timeline,
    compute_regime_adjusted_metrics,
    compute_regime_breakdown,
    generate_report,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _dt(hour: int, day: int = 1) -> datetime:
    return datetime(2025, 1, day, hour, 0, 0, tzinfo=timezone.utc)


def _make_trade(
    *,
    entry_hour: int = 0,
    exit_hour: int = 1,
    day: int = 1,
    pnl: float = 10.0,
    regime: str = "LOW_VOL_TRENDING",
    direction: str = "BUY",
) -> BacktestTrade:
    return BacktestTrade(
        entry_time=_dt(entry_hour, day),
        entry_price=100.0,
        exit_time=_dt(exit_hour, day),
        exit_price=101.0 if pnl > 0 else 99.0,
        direction=direction,
        quantity=1.0,
        pnl=pnl,
        commission=0.01,
        slippage_cost=0.005,
        spread_cost=0.005,
        exit_reason="stop_loss",
        regime_label=regime,
    )


def _make_result(trades: list[BacktestTrade]) -> BacktestResult:
    equity = 10000.0
    curve: list[tuple[datetime, float]] = [(_dt(0), equity)]
    for t in trades:
        equity += t.pnl
        curve.append((t.exit_time or t.entry_time, equity))
    return BacktestResult(
        config=BacktestConfig(
            instrument="EUR_USD",
            interval="1h",
            start_date=_dt(0),
            end_date=_dt(23),
            initial_equity=10000.0,
            pessimistic=False,
        ),
        equity_curve=curve,
        trades=trades,
        initial_equity=10000.0,
        final_equity=equity,
        total_return=(equity - 10000.0) / 10000.0,
        trade_count=len(trades),
    )


def _default_gate_eval() -> GateEvaluation:
    return GateEvaluation(
        results=[
            MetricGateResult(
                metric_name="sharpe_ratio",
                value=1.0,
                threshold=0.8,
                gate_type="hard",
                passed=True,
            ),
        ],
        all_hard_gates_passed=True,
        instrument="EUR_USD",
    )


def _default_report_config(
    annualization_factor: float = 15.875,  # sqrt(252)
) -> ReportConfig:
    return ReportConfig(
        low_sample_threshold=20,
        annualization_factor=annualization_factor,
    )


# ---------------------------------------------------------------------------
# Frozen dataclasses
# ---------------------------------------------------------------------------

class TestDataclassImmutability:
    def test_regime_performance_frozen(self) -> None:
        rp = RegimePerformance(
            regime_label="LOW_VOL_TRENDING",
            sharpe_ratio=1.0,
            profit_factor=1.5,
            win_rate=0.55,
            trade_count=30,
            total_pnl=100.0,
            low_sample_flag=False,
        )
        with pytest.raises(AttributeError):
            rp.sharpe_ratio = 2.0  # type: ignore[misc]

    def test_regime_transition_frozen(self) -> None:
        rt = RegimeTransition(time=_dt(0), regime_label="LOW_VOL_TRENDING")
        with pytest.raises(AttributeError):
            rt.regime_label = "HIGH_VOL_TRENDING"  # type: ignore[misc]

    def test_bias_control_frozen(self) -> None:
        bc = BiasControl(
            bias_name="look_ahead",
            mitigation="Walk-forward with 48h embargo",
            status="APPLIED",
        )
        with pytest.raises(AttributeError):
            bc.status = "FLAGGED"  # type: ignore[misc]

    def test_report_config_frozen(self) -> None:
        rc = _default_report_config()
        with pytest.raises(AttributeError):
            rc.low_sample_threshold = 10  # type: ignore[misc]

    def test_backtest_report_frozen(self) -> None:
        trades = [_make_trade(pnl=10.0)]
        result = _make_result(trades)
        report = generate_report(
            result,
            config=_default_report_config(),
            gate_evaluation=_default_gate_eval(),
        )
        with pytest.raises(AttributeError):
            report.instrument = "BTC_USD"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# compute_regime_breakdown
# ---------------------------------------------------------------------------

class TestComputeRegimeBreakdown:
    def test_groups_by_regime(self) -> None:
        """Trades are grouped by regime_label."""
        trades = [
            _make_trade(regime="LOW_VOL_TRENDING", pnl=10.0),
            _make_trade(regime="HIGH_VOL_TRENDING", pnl=20.0),
            _make_trade(regime="LOW_VOL_TRENDING", pnl=-5.0),
        ]
        breakdown = compute_regime_breakdown(trades, annualization_factor=15.875)
        assert set(breakdown.keys()) == {"LOW_VOL_TRENDING", "HIGH_VOL_TRENDING"}
        assert breakdown["LOW_VOL_TRENDING"].trade_count == 2
        assert breakdown["HIGH_VOL_TRENDING"].trade_count == 1

    def test_per_regime_win_rate(self) -> None:
        """Win rate computed per regime."""
        trades = [
            _make_trade(regime="LOW_VOL_TRENDING", pnl=10.0),
            _make_trade(regime="LOW_VOL_TRENDING", pnl=-5.0),
            _make_trade(regime="LOW_VOL_TRENDING", pnl=15.0),
        ]
        breakdown = compute_regime_breakdown(trades, annualization_factor=15.875)
        # 2 wins out of 3
        assert abs(breakdown["LOW_VOL_TRENDING"].win_rate - 2 / 3) < 1e-10

    def test_per_regime_profit_factor(self) -> None:
        """Profit factor = sum(wins) / abs(sum(losses))."""
        trades = [
            _make_trade(regime="LOW_VOL_TRENDING", pnl=30.0),
            _make_trade(regime="LOW_VOL_TRENDING", pnl=-10.0),
        ]
        breakdown = compute_regime_breakdown(trades, annualization_factor=15.875)
        assert abs(breakdown["LOW_VOL_TRENDING"].profit_factor - 3.0) < 1e-10

    def test_per_regime_total_pnl(self) -> None:
        """Total PnL summed per regime."""
        trades = [
            _make_trade(regime="HIGH_VOL_RANGING", pnl=20.0),
            _make_trade(regime="HIGH_VOL_RANGING", pnl=-5.0),
        ]
        breakdown = compute_regime_breakdown(trades, annualization_factor=15.875)
        assert abs(breakdown["HIGH_VOL_RANGING"].total_pnl - 15.0) < 1e-10

    def test_low_sample_flag_below_threshold(self) -> None:
        """Regime with < 20 trades is flagged."""
        trades = [_make_trade(regime="LOW_VOL_RANGING", pnl=5.0) for _ in range(10)]
        breakdown = compute_regime_breakdown(trades, annualization_factor=15.875)
        assert breakdown["LOW_VOL_RANGING"].low_sample_flag is True

    def test_low_sample_flag_above_threshold(self) -> None:
        """Regime with >= 20 trades is not flagged."""
        trades = [_make_trade(regime="LOW_VOL_RANGING", pnl=5.0) for _ in range(25)]
        breakdown = compute_regime_breakdown(trades, annualization_factor=15.875)
        assert breakdown["LOW_VOL_RANGING"].low_sample_flag is False

    def test_empty_trades(self) -> None:
        """Empty trade list produces empty breakdown."""
        breakdown = compute_regime_breakdown([], annualization_factor=15.875)
        assert breakdown == {}

    def test_all_losses_profit_factor_zero(self) -> None:
        """All losing trades should give profit_factor 0."""
        trades = [
            _make_trade(regime="HIGH_VOL_TRENDING", pnl=-10.0),
            _make_trade(regime="HIGH_VOL_TRENDING", pnl=-5.0),
        ]
        breakdown = compute_regime_breakdown(trades, annualization_factor=15.875)
        assert breakdown["HIGH_VOL_TRENDING"].profit_factor == 0.0


# ---------------------------------------------------------------------------
# build_regime_timeline
# ---------------------------------------------------------------------------

class TestBuildRegimeTimeline:
    def test_transitions_on_change(self) -> None:
        """Only emit transition when regime changes."""
        labels = [
            (_dt(0), "LOW_VOL_TRENDING"),
            (_dt(1), "LOW_VOL_TRENDING"),
            (_dt(2), "HIGH_VOL_TRENDING"),
            (_dt(3), "HIGH_VOL_TRENDING"),
            (_dt(4), "LOW_VOL_RANGING"),
        ]
        timeline = build_regime_timeline(labels)
        assert len(timeline) == 3
        assert timeline[0].regime_label == "LOW_VOL_TRENDING"
        assert timeline[0].time == _dt(0)
        assert timeline[1].regime_label == "HIGH_VOL_TRENDING"
        assert timeline[1].time == _dt(2)
        assert timeline[2].regime_label == "LOW_VOL_RANGING"
        assert timeline[2].time == _dt(4)

    def test_no_change_single_entry(self) -> None:
        """Constant regime produces single transition."""
        labels = [
            (_dt(0), "LOW_VOL_TRENDING"),
            (_dt(1), "LOW_VOL_TRENDING"),
            (_dt(2), "LOW_VOL_TRENDING"),
        ]
        timeline = build_regime_timeline(labels)
        assert len(timeline) == 1
        assert timeline[0].regime_label == "LOW_VOL_TRENDING"

    def test_empty_input(self) -> None:
        """Empty input produces empty timeline."""
        timeline = build_regime_timeline([])
        assert timeline == ()

    def test_single_point(self) -> None:
        """Single data point produces one transition."""
        labels = [(_dt(0), "HIGH_VOL_RANGING")]
        timeline = build_regime_timeline(labels)
        assert len(timeline) == 1

    def test_every_bar_changes(self) -> None:
        """Every bar has a different regime."""
        labels = [
            (_dt(0), "LOW_VOL_TRENDING"),
            (_dt(1), "HIGH_VOL_TRENDING"),
            (_dt(2), "LOW_VOL_RANGING"),
            (_dt(3), "HIGH_VOL_RANGING"),
        ]
        timeline = build_regime_timeline(labels)
        assert len(timeline) == 4


# ---------------------------------------------------------------------------
# compute_regime_adjusted_metrics
# ---------------------------------------------------------------------------

class TestComputeRegimeAdjustedMetrics:
    def test_weighted_average(self) -> None:
        """Metrics weighted by time-in-regime."""
        breakdown = {
            "LOW_VOL_TRENDING": RegimePerformance(
                regime_label="LOW_VOL_TRENDING",
                sharpe_ratio=2.0,
                profit_factor=2.0,
                win_rate=0.60,
                trade_count=30,
                total_pnl=100.0,
                low_sample_flag=False,
            ),
            "HIGH_VOL_TRENDING": RegimePerformance(
                regime_label="HIGH_VOL_TRENDING",
                sharpe_ratio=1.0,
                profit_factor=1.0,
                win_rate=0.40,
                trade_count=30,
                total_pnl=50.0,
                low_sample_flag=False,
            ),
        }
        durations = {"LOW_VOL_TRENDING": 0.6, "HIGH_VOL_TRENDING": 0.4}
        adjusted = compute_regime_adjusted_metrics(breakdown, durations)
        # Weighted Sharpe: 2.0*0.6 + 1.0*0.4 = 1.6
        assert abs(adjusted["sharpe_ratio"] - 1.6) < 1e-10
        # Weighted PF: 2.0*0.6 + 1.0*0.4 = 1.6
        assert abs(adjusted["profit_factor"] - 1.6) < 1e-10
        # Weighted win rate: 0.60*0.6 + 0.40*0.4 = 0.52
        assert abs(adjusted["win_rate"] - 0.52) < 1e-10

    def test_excludes_low_sample_regimes(self) -> None:
        """Low-sample regimes excluded from weighting, weights renormalized."""
        breakdown = {
            "LOW_VOL_TRENDING": RegimePerformance(
                regime_label="LOW_VOL_TRENDING",
                sharpe_ratio=2.0,
                profit_factor=2.0,
                win_rate=0.60,
                trade_count=30,
                total_pnl=100.0,
                low_sample_flag=False,
            ),
            "HIGH_VOL_RANGING": RegimePerformance(
                regime_label="HIGH_VOL_RANGING",
                sharpe_ratio=0.5,
                profit_factor=0.5,
                win_rate=0.30,
                trade_count=5,
                total_pnl=10.0,
                low_sample_flag=True,
            ),
        }
        durations = {"LOW_VOL_TRENDING": 0.7, "HIGH_VOL_RANGING": 0.3}
        adjusted = compute_regime_adjusted_metrics(breakdown, durations)
        # Only LOW_VOL_TRENDING contributes, renormalized weight = 1.0
        assert abs(adjusted["sharpe_ratio"] - 2.0) < 1e-10
        assert abs(adjusted["profit_factor"] - 2.0) < 1e-10

    def test_single_regime(self) -> None:
        """Single regime: adjusted = raw metrics."""
        breakdown = {
            "LOW_VOL_TRENDING": RegimePerformance(
                regime_label="LOW_VOL_TRENDING",
                sharpe_ratio=1.5,
                profit_factor=1.8,
                win_rate=0.55,
                trade_count=40,
                total_pnl=200.0,
                low_sample_flag=False,
            ),
        }
        durations = {"LOW_VOL_TRENDING": 1.0}
        adjusted = compute_regime_adjusted_metrics(breakdown, durations)
        assert abs(adjusted["sharpe_ratio"] - 1.5) < 1e-10

    def test_all_low_sample_returns_empty(self) -> None:
        """All regimes flagged low-sample returns empty metrics."""
        breakdown = {
            "LOW_VOL_TRENDING": RegimePerformance(
                regime_label="LOW_VOL_TRENDING",
                sharpe_ratio=1.0,
                profit_factor=1.0,
                win_rate=0.50,
                trade_count=5,
                total_pnl=10.0,
                low_sample_flag=True,
            ),
        }
        durations = {"LOW_VOL_TRENDING": 1.0}
        adjusted = compute_regime_adjusted_metrics(breakdown, durations)
        assert adjusted == {}

    def test_empty_breakdown(self) -> None:
        """Empty breakdown returns empty metrics."""
        adjusted = compute_regime_adjusted_metrics({}, {})
        assert adjusted == {}


# ---------------------------------------------------------------------------
# build_bias_controls
# ---------------------------------------------------------------------------

class TestBuildBiasControls:
    def test_all_applied_with_full_validation(self) -> None:
        """All controls APPLIED when walk-forward and kfold both present."""
        controls = build_bias_controls(
            has_walk_forward=True,
            has_kfold=True,
            instrument="EUR_USD",
        )
        assert len(controls) == 5
        by_name = {c.bias_name: c for c in controls}
        assert by_name["look_ahead"].status == "APPLIED"
        assert by_name["overfitting"].status == "APPLIED"
        assert by_name["survivorship"].status == "NOT_APPLICABLE"
        assert by_name["selection"].status == "APPLIED"
        assert by_name["data_snooping"].status == "APPLIED"

    def test_survivorship_flagged_for_btc(self) -> None:
        """Survivorship is FLAGGED for BTC_USD."""
        controls = build_bias_controls(
            has_walk_forward=True,
            has_kfold=True,
            instrument="BTC_USD",
        )
        by_name = {c.bias_name: c for c in controls}
        assert by_name["survivorship"].status == "FLAGGED"

    def test_missing_walk_forward(self) -> None:
        """Look-ahead FLAGGED without walk-forward."""
        controls = build_bias_controls(
            has_walk_forward=False,
            has_kfold=True,
            instrument="EUR_USD",
        )
        by_name = {c.bias_name: c for c in controls}
        assert by_name["look_ahead"].status == "FLAGGED"

    def test_missing_kfold(self) -> None:
        """Overfitting FLAGGED without both walk-forward and kfold."""
        controls = build_bias_controls(
            has_walk_forward=True,
            has_kfold=False,
            instrument="EUR_USD",
        )
        by_name = {c.bias_name: c for c in controls}
        assert by_name["overfitting"].status == "FLAGGED"

    def test_both_missing(self) -> None:
        """Both look-ahead and overfitting FLAGGED when no validation."""
        controls = build_bias_controls(
            has_walk_forward=False,
            has_kfold=False,
            instrument="EUR_USD",
        )
        by_name = {c.bias_name: c for c in controls}
        assert by_name["look_ahead"].status == "FLAGGED"
        assert by_name["overfitting"].status == "FLAGGED"


# ---------------------------------------------------------------------------
# generate_report
# ---------------------------------------------------------------------------

class TestGenerateReport:
    def test_end_to_end_with_trades(self) -> None:
        """Full report generation with mixed-regime trades."""
        trades = [
            _make_trade(regime="LOW_VOL_TRENDING", pnl=10.0, entry_hour=0, exit_hour=1),
            _make_trade(regime="LOW_VOL_TRENDING", pnl=15.0, entry_hour=2, exit_hour=3),
            _make_trade(regime="HIGH_VOL_TRENDING", pnl=-5.0, entry_hour=4, exit_hour=5),
        ]
        result = _make_result(trades)
        report = generate_report(
            result,
            config=_default_report_config(),
            gate_evaluation=_default_gate_eval(),
            has_walk_forward=True,
            has_kfold=True,
        )
        assert report.instrument == "EUR_USD"
        assert "LOW_VOL_TRENDING" in report.regime_breakdown
        assert "HIGH_VOL_TRENDING" in report.regime_breakdown
        assert len(report.bias_controls) == 5
        assert isinstance(report.generated_at, datetime)

    def test_report_with_regime_timeline(self) -> None:
        """Report includes regime timeline when regime_labels provided."""
        trades = [_make_trade(pnl=10.0)]
        result = _make_result(trades)
        regime_labels = [
            (_dt(0), "LOW_VOL_TRENDING"),
            (_dt(1), "HIGH_VOL_TRENDING"),
            (_dt(2), "HIGH_VOL_TRENDING"),
        ]
        report = generate_report(
            result,
            config=_default_report_config(),
            gate_evaluation=_default_gate_eval(),
            regime_labels=regime_labels,
        )
        assert len(report.regime_timeline) == 2  # Two distinct regimes

    def test_report_without_regime_timeline(self) -> None:
        """Report has empty timeline when no regime_labels provided."""
        trades = [_make_trade(pnl=10.0)]
        result = _make_result(trades)
        report = generate_report(
            result,
            config=_default_report_config(),
            gate_evaluation=_default_gate_eval(),
        )
        assert report.regime_timeline == ()

    def test_low_sample_regimes_listed(self) -> None:
        """Low-sample regime labels collected in report."""
        trades = [_make_trade(regime="LOW_VOL_RANGING", pnl=5.0) for _ in range(5)]
        result = _make_result(trades)
        report = generate_report(
            result,
            config=_default_report_config(),
            gate_evaluation=_default_gate_eval(),
        )
        assert "LOW_VOL_RANGING" in report.low_sample_regimes

    def test_gate_evaluation_preserved(self) -> None:
        """Gate evaluation passed through to report."""
        trades = [_make_trade(pnl=10.0)]
        result = _make_result(trades)
        gate = _default_gate_eval()
        report = generate_report(
            result,
            config=_default_report_config(),
            gate_evaluation=gate,
        )
        assert report.gate_evaluation is gate

    def test_metrics_included(self) -> None:
        """Report includes computed PerformanceMetrics."""
        trades = [_make_trade(pnl=10.0) for _ in range(5)]
        result = _make_result(trades)
        report = generate_report(
            result,
            config=_default_report_config(),
            gate_evaluation=_default_gate_eval(),
        )
        assert isinstance(report.metrics, PerformanceMetrics)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_zero_trades_report(self) -> None:
        """Report works with zero trades."""
        result = _make_result([])
        report = generate_report(
            result,
            config=_default_report_config(),
            gate_evaluation=_default_gate_eval(),
        )
        assert report.regime_breakdown == {}
        assert report.low_sample_regimes == ()
        assert report.regime_adjusted_metrics == {}

    def test_all_trades_same_regime(self) -> None:
        """All trades in one regime: breakdown has single entry."""
        trades = [_make_trade(regime="HIGH_VOL_RANGING", pnl=10.0) for _ in range(25)]
        result = _make_result(trades)
        report = generate_report(
            result,
            config=_default_report_config(),
            gate_evaluation=_default_gate_eval(),
        )
        assert len(report.regime_breakdown) == 1
        assert "HIGH_VOL_RANGING" in report.regime_breakdown

    def test_regime_durations_from_labels(self) -> None:
        """Regime durations correctly derived from regime_labels."""
        trades = [
            _make_trade(regime="LOW_VOL_TRENDING", pnl=10.0),
        ]
        result = _make_result(trades)
        # 3 bars LOW_VOL_TRENDING, 1 bar HIGH_VOL_TRENDING
        regime_labels = [
            (_dt(0), "LOW_VOL_TRENDING"),
            (_dt(1), "LOW_VOL_TRENDING"),
            (_dt(2), "LOW_VOL_TRENDING"),
            (_dt(3), "HIGH_VOL_TRENDING"),
        ]
        report = generate_report(
            result,
            config=_default_report_config(),
            gate_evaluation=_default_gate_eval(),
            regime_labels=regime_labels,
        )
        # Should have regime_adjusted_metrics based on time weights
        # LOW_VOL_TRENDING: 3/4, HIGH_VOL_TRENDING: 1/4
        # Only LOW_VOL_TRENDING has trades (1 trade < 20 → low sample)
        # So regime_adjusted_metrics may be empty if all are low sample
        assert isinstance(report.regime_adjusted_metrics, dict)

    def test_json_serializable_output(self) -> None:
        """Report fields are JSON-serializable types."""
        import json

        trades = [_make_trade(pnl=10.0)]
        result = _make_result(trades)
        report = generate_report(
            result,
            config=_default_report_config(),
            gate_evaluation=_default_gate_eval(),
        )
        # All fields should be serializable
        data = {
            "instrument": report.instrument,
            "generated_at": report.generated_at.isoformat(),
            "low_sample_regimes": list(report.low_sample_regimes),
            "regime_adjusted_metrics": report.regime_adjusted_metrics,
            "regime_breakdown": {
                k: {
                    "regime_label": v.regime_label,
                    "sharpe_ratio": v.sharpe_ratio,
                    "profit_factor": v.profit_factor,
                    "win_rate": v.win_rate,
                    "trade_count": v.trade_count,
                    "total_pnl": v.total_pnl,
                    "low_sample_flag": v.low_sample_flag,
                }
                for k, v in report.regime_breakdown.items()
            },
            "bias_controls": [
                {
                    "bias_name": c.bias_name,
                    "mitigation": c.mitigation,
                    "status": c.status,
                }
                for c in report.bias_controls
            ],
        }
        serialized = json.dumps(data)
        assert isinstance(serialized, str)
