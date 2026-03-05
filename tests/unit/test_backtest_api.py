"""Tests for backtest API endpoints (T-606)."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from src.api.v1.backtest import BacktestRunner, BacktestService, configure
from src.app import app
from src.backtest.engine import BacktestConfig, BacktestResult, BacktestTrade

client = TestClient(app)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_NOW = datetime(2024, 1, 1, tzinfo=UTC)
_END = datetime(2024, 6, 1, tzinfo=UTC)


def _make_trade(
    direction: str = "BUY",
    pnl: float = 100.0,
    regime_label: str = "LOW_VOL_TRENDING",
) -> BacktestTrade:
    return BacktestTrade(
        entry_time=_NOW,
        entry_price=1.1000,
        exit_time=datetime(2024, 1, 2, tzinfo=UTC),
        exit_price=1.1100,
        direction=direction,
        quantity=100.0,
        pnl=pnl,
        commission=0.0,
        slippage_cost=0.001,
        spread_cost=0.0005,
        exit_reason="hard_stop",
        regime_label=regime_label,
    )


def _make_result(instrument: str = "EUR_USD") -> BacktestResult:
    trades = [_make_trade(pnl=100.0), _make_trade(pnl=-50.0, direction="SELL")]
    return BacktestResult(
        config=BacktestConfig(
            instrument=instrument,
            interval="H1",
            start_date=_NOW,
            end_date=_END,
            initial_equity=10_000.0,
            pessimistic=False,
        ),
        equity_curve=[
            (_NOW, 10_000.0),
            (datetime(2024, 1, 2, tzinfo=UTC), 10_100.0),
            (datetime(2024, 1, 3, tzinfo=UTC), 10_050.0),
        ],
        trades=trades,
        initial_equity=10_000.0,
        final_equity=10_050.0,
        total_return=0.005,
        trade_count=2,
    )


class FakeRunner:
    """Fake BacktestRunner that returns canned results."""

    def __init__(self) -> None:
        self.calls: list[BacktestConfig] = []

    def run(self, config: BacktestConfig) -> BacktestResult:
        self.calls.append(config)
        return _make_result(config.instrument)


class FailingRunner:
    """Runner that always raises."""

    def run(self, config: BacktestConfig) -> BacktestResult:
        raise ValueError("Backtest simulation failed")


def _setup_service(runner: BacktestRunner | None = None) -> BacktestService:
    r: BacktestRunner = runner if runner is not None else FakeRunner()
    service = BacktestService(runner=r)
    configure(service)
    return service


def _post_backtest(
    instrument: str = "EUR_USD",
    start: str = "2024-01-01T00:00:00Z",
    end: str = "2024-06-01T00:00:00Z",
    **overrides: object,
) -> dict:  # type: ignore[type-arg]
    body: dict[str, object] = {
        "instrument": instrument,
        "start_date": start,
        "end_date": end,
        **overrides,
    }
    resp = client.post("/api/v1/backtest", json=body)
    return {"status_code": resp.status_code, "data": resp.json()}


# ---------------------------------------------------------------------------
# POST /api/v1/backtest
# ---------------------------------------------------------------------------


class TestPostBacktest:
    def test_creates_run_returns_id(self) -> None:
        _setup_service()
        r = _post_backtest()
        assert r["status_code"] == 200
        assert "id" in r["data"]
        assert r["data"]["status"] == "completed"
        assert r["data"]["instrument"] == "EUR_USD"

    def test_includes_result_on_completion(self) -> None:
        _setup_service()
        r = _post_backtest()
        result = r["data"]["result"]
        assert result is not None
        assert "equity_curve" in result
        assert "trades" in result
        assert "metrics" in result
        assert "gate_evaluation" in result
        assert "regime_breakdown" in result
        assert "bias_controls" in result

    def test_validates_instrument(self) -> None:
        _setup_service()
        r = _post_backtest(instrument="INVALID")
        assert r["status_code"] == 400

    def test_validates_date_range(self) -> None:
        _setup_service()
        r = _post_backtest(start="2024-06-01T00:00:00Z", end="2024-01-01T00:00:00Z")
        assert r["status_code"] == 400

    def test_pessimistic_flag_passed(self) -> None:
        runner = FakeRunner()
        _setup_service(runner)
        _post_backtest(pessimistic=True)
        assert runner.calls[0].pessimistic is True

    def test_custom_initial_equity(self) -> None:
        runner = FakeRunner()
        _setup_service(runner)
        _post_backtest(initial_equity=50_000.0)
        assert runner.calls[0].initial_equity == 50_000.0

    def test_failed_run(self) -> None:
        _setup_service(FailingRunner())
        r = _post_backtest()
        assert r["data"]["status"] == "failed"
        assert r["data"]["error"] is not None

    def test_btc_instrument(self) -> None:
        _setup_service()
        r = _post_backtest(instrument="BTC_USD")
        assert r["status_code"] == 200
        assert r["data"]["instrument"] == "BTC_USD"


# ---------------------------------------------------------------------------
# GET /api/v1/backtest/{run_id}
# ---------------------------------------------------------------------------


class TestGetBacktestById:
    def test_returns_completed_result(self) -> None:
        _setup_service()
        post = _post_backtest()
        run_id = post["data"]["id"]
        resp = client.get(f"/api/v1/backtest/{run_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == run_id
        assert data["status"] == "completed"
        assert data["result"] is not None

    def test_unknown_id_returns_404(self) -> None:
        _setup_service()
        resp = client.get("/api/v1/backtest/nonexistent")
        assert resp.status_code == 404

    def test_result_fields_complete(self) -> None:
        _setup_service()
        post = _post_backtest()
        run_id = post["data"]["id"]
        resp = client.get(f"/api/v1/backtest/{run_id}")
        result = resp.json()["result"]

        # Equity curve
        assert isinstance(result["equity_curve"], list)
        assert len(result["equity_curve"]) == 3
        point = result["equity_curve"][0]
        assert "time" in point
        assert "equity" in point

        # Trades
        assert isinstance(result["trades"], list)
        assert len(result["trades"]) == 2
        trade = result["trades"][0]
        assert "entry_time" in trade
        assert "pnl" in trade
        assert "regime_label" in trade

        # Metrics
        m = result["metrics"]
        for key in ("sharpe_ratio", "profit_factor", "max_drawdown",
                     "win_rate", "expectancy", "trade_count"):
            assert key in m

        # Gate evaluation
        g = result["gate_evaluation"]
        assert "results" in g
        assert isinstance(g["results"], list)
        assert "all_hard_gates_passed" in g

        # Regime breakdown
        assert isinstance(result["regime_breakdown"], dict)

        # Bias controls
        assert isinstance(result["bias_controls"], list)
        assert len(result["bias_controls"]) == 5

        # Low sample regimes
        assert isinstance(result["low_sample_regimes"], list)


# ---------------------------------------------------------------------------
# GET /api/v1/backtest (list)
# ---------------------------------------------------------------------------


class TestListBacktests:
    def test_list_empty(self) -> None:
        _setup_service()
        resp = client.get("/api/v1/backtest")
        assert resp.status_code == 200
        data = resp.json()
        assert data["runs"] == []
        assert data["count"] == 0

    def test_list_after_runs(self) -> None:
        _setup_service()
        _post_backtest(instrument="EUR_USD")
        _post_backtest(instrument="BTC_USD")
        resp = client.get("/api/v1/backtest")
        data = resp.json()
        assert data["count"] == 2
        assert len(data["runs"]) == 2

    def test_list_excludes_result_data(self) -> None:
        _setup_service()
        _post_backtest()
        resp = client.get("/api/v1/backtest")
        runs = resp.json()["runs"]
        assert runs[0]["result"] is None


# ---------------------------------------------------------------------------
# Result content
# ---------------------------------------------------------------------------


class TestResultContent:
    def test_equity_and_trade_count(self) -> None:
        _setup_service()
        r = _post_backtest()
        result = r["data"]["result"]
        assert result["initial_equity"] == 10_000.0
        assert result["final_equity"] == 10_050.0
        assert result["trade_count"] == 2

    def test_bias_controls_five_entries(self) -> None:
        _setup_service()
        r = _post_backtest()
        bias = r["data"]["result"]["bias_controls"]
        assert len(bias) == 5
        names = {b["bias_name"] for b in bias}
        assert names == {
            "look_ahead", "overfitting", "survivorship", "selection", "data_snooping",
        }

    def test_regime_breakdown_present(self) -> None:
        _setup_service()
        r = _post_backtest()
        regime = r["data"]["result"]["regime_breakdown"]
        assert "LOW_VOL_TRENDING" in regime
        rp = regime["LOW_VOL_TRENDING"]
        assert "sharpe_ratio" in rp
        assert rp["trade_count"] == 2

    def test_low_sample_regimes_flagged(self) -> None:
        _setup_service()
        r = _post_backtest()
        result = r["data"]["result"]
        # 2 trades < default threshold of 20
        assert "LOW_VOL_TRENDING" in result["low_sample_regimes"]


# ---------------------------------------------------------------------------
# Service pattern
# ---------------------------------------------------------------------------


class TestServicePattern:
    def test_configure_and_get(self) -> None:
        from src.api.v1.backtest import _get_service
        service = _setup_service()
        assert _get_service() is service

    def test_unconfigured_returns_503(self) -> None:
        from src.api.v1 import backtest as bt_module
        bt_module._service = None
        resp = client.post("/api/v1/backtest", json={
            "instrument": "EUR_USD",
            "start_date": "2024-01-01T00:00:00Z",
            "end_date": "2024-06-01T00:00:00Z",
        })
        assert resp.status_code == 503
