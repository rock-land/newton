"""Backtest performance metrics (T-603, SPEC §9.5).

Computes per-instrument and portfolio-level metrics from BacktestResult objects.
Evaluates hard/informational gates per §9.5 threshold table.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from src.backtest.engine import BacktestResult

# ---------------------------------------------------------------------------
# Domain models — all frozen per DEC-010
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PerformanceMetrics:
    """Per-instrument performance metrics."""

    sharpe_ratio: float
    profit_factor: float
    max_drawdown: float
    win_rate: float
    calmar_ratio: float
    expectancy: float
    calibration_error: float
    trade_count: int
    annualized_return: float
    total_return: float


@dataclass(frozen=True)
class MetricGateResult:
    """Result of evaluating a single metric against its threshold."""

    metric_name: str
    value: float
    threshold: float
    gate_type: str  # "hard" or "informational"
    passed: bool


@dataclass(frozen=True)
class GateEvaluation:
    """Aggregate gate evaluation for one instrument."""

    results: list[MetricGateResult]
    all_hard_gates_passed: bool
    instrument: str


@dataclass(frozen=True)
class PortfolioMetrics:
    """Cross-instrument portfolio-level metrics."""

    portfolio_sharpe: float
    max_portfolio_drawdown: float
    instrument_correlation: float
    per_instrument: dict[str, PerformanceMetrics]


# ---------------------------------------------------------------------------
# Metric computation
# ---------------------------------------------------------------------------

_PF_CAP = 999.9


def compute_metrics(
    result: BacktestResult,
    *,
    annualization_factor: float,
    predicted_probabilities: Sequence[float] | None = None,
) -> PerformanceMetrics:
    """Compute all §9.5 metrics from a BacktestResult.

    Args:
        result: Output of run_backtest().
        annualization_factor: √252 for forex, √365 for crypto.
        predicted_probabilities: Optional per-trade predicted probabilities
            for calibration error. Must match len(result.trades) if provided.

    Returns:
        Frozen PerformanceMetrics dataclass.
    """
    trades = result.trades
    equity_curve = result.equity_curve

    if not equity_curve:
        return PerformanceMetrics(
            sharpe_ratio=0.0,
            profit_factor=0.0,
            max_drawdown=0.0,
            win_rate=0.0,
            calmar_ratio=0.0,
            expectancy=0.0,
            calibration_error=0.0,
            trade_count=len(trades),
            annualized_return=0.0,
            total_return=result.total_return,
        )

    # --- Returns from equity curve ---
    equity_values = [v for _, v in equity_curve]
    returns = _compute_returns(equity_values)

    # --- Sharpe ---
    sharpe = _compute_sharpe(returns, annualization_factor)

    # --- Max Drawdown ---
    max_dd = _compute_max_drawdown(equity_values)

    # --- Annualized Return ---
    total_return = result.total_return
    n_periods = len(equity_values) - 1
    if n_periods > 0:
        annualized_return = total_return * (annualization_factor ** 2) / n_periods
    else:
        annualized_return = 0.0

    # --- Calmar ---
    calmar = annualized_return / max_dd if max_dd > 0 else 0.0

    # --- Trade-dependent metrics ---
    if not trades:
        return PerformanceMetrics(
            sharpe_ratio=sharpe,
            profit_factor=0.0,
            max_drawdown=max_dd,
            win_rate=0.0,
            calmar_ratio=calmar,
            expectancy=0.0,
            calibration_error=0.0,
            trade_count=0,
            annualized_return=annualized_return,
            total_return=total_return,
        )

    # --- Profit Factor ---
    profit_factor = _compute_profit_factor(trades)

    # --- Win Rate ---
    wins = [t for t in trades if t.pnl > 0]
    win_rate = len(wins) / len(trades)

    # --- Expectancy ---
    losses = [t for t in trades if t.pnl <= 0]
    avg_win = sum(t.pnl for t in wins) / len(wins) if wins else 0.0
    avg_loss = sum(abs(t.pnl) for t in losses) / len(losses) if losses else 0.0
    loss_rate = 1.0 - win_rate
    expectancy = (win_rate * avg_win) - (loss_rate * avg_loss)

    # --- Calibration Error ---
    cal_error = _compute_calibration_error(trades, predicted_probabilities)

    return PerformanceMetrics(
        sharpe_ratio=sharpe,
        profit_factor=profit_factor,
        max_drawdown=max_dd,
        win_rate=win_rate,
        calmar_ratio=calmar,
        expectancy=expectancy,
        calibration_error=cal_error,
        trade_count=len(trades),
        annualized_return=annualized_return,
        total_return=total_return,
    )


# ---------------------------------------------------------------------------
# Gate evaluation
# ---------------------------------------------------------------------------

# §9.5 thresholds: (metric_name, threshold, gate_type, comparison)
# comparison: "gt" = value must be > threshold, "lt" = value must be < threshold
_GATE_DEFS: list[tuple[str, float, str, str]] = [
    ("sharpe_ratio", 0.8, "hard", "gt"),
    ("profit_factor", 1.3, "hard", "gt"),
    ("max_drawdown", 0.15, "hard", "lt"),
    ("expectancy", 0.0, "hard", "gt"),
    ("calibration_error", 0.05, "hard", "lt"),
    ("win_rate", 0.45, "informational", "gt"),
    ("calmar_ratio", 0.5, "informational", "gt"),
]


def evaluate_gates(
    metrics: PerformanceMetrics,
    *,
    instrument: str,
    trade_count_per_fold: int | None = None,
) -> GateEvaluation:
    """Evaluate metrics against §9.5 gate thresholds.

    Args:
        metrics: Computed performance metrics.
        instrument: Instrument identifier for the result.
        trade_count_per_fold: Trade count per fold for minimum sample check.
            If None, uses metrics.trade_count.

    Returns:
        Frozen GateEvaluation with per-metric results.
    """
    results: list[MetricGateResult] = []

    for name, threshold, gate_type, comparison in _GATE_DEFS:
        value = getattr(metrics, name)
        if comparison == "gt":
            passed = value > threshold
        else:
            passed = value < threshold
        results.append(MetricGateResult(
            metric_name=name,
            value=value,
            threshold=threshold,
            gate_type=gate_type,
            passed=passed,
        ))

    # Trade count gate (hard, >30 per fold)
    tc = trade_count_per_fold if trade_count_per_fold is not None else metrics.trade_count
    results.append(MetricGateResult(
        metric_name="trade_count",
        value=float(tc),
        threshold=30.0,
        gate_type="hard",
        passed=tc > 30,
    ))

    all_hard_passed = all(r.passed for r in results if r.gate_type == "hard")

    return GateEvaluation(
        results=results,
        all_hard_gates_passed=all_hard_passed,
        instrument=instrument,
    )


# ---------------------------------------------------------------------------
# Portfolio metrics
# ---------------------------------------------------------------------------


def compute_portfolio_metrics(
    results: dict[str, BacktestResult],
    annualization_factors: dict[str, float],
) -> PortfolioMetrics:
    """Compute portfolio-level metrics across multiple instruments.

    Args:
        results: Dict mapping instrument name to BacktestResult.
        annualization_factors: Dict mapping instrument name to annualization factor.

    Returns:
        Frozen PortfolioMetrics dataclass.
    """
    # Per-instrument metrics
    per_instrument: dict[str, PerformanceMetrics] = {}
    for inst, res in results.items():
        per_instrument[inst] = compute_metrics(
            res, annualization_factor=annualization_factors[inst],
        )

    instruments = list(results.keys())

    # Align equity curves to same length (use returns)
    all_returns: dict[str, list[float]] = {}
    for inst, res in results.items():
        eq_vals = [v for _, v in res.equity_curve]
        all_returns[inst] = _compute_returns(eq_vals) if len(eq_vals) > 1 else []

    # Portfolio equity curve: sum of equity values at each time step
    # Align by index (assume same-length curves for same backtest period)
    max_len = max((len(res.equity_curve) for res in results.values()), default=0)
    portfolio_equity: list[float] = []
    for i in range(max_len):
        total = 0.0
        for res in results.values():
            if i < len(res.equity_curve):
                total += res.equity_curve[i][1]
            elif res.equity_curve:
                total += res.equity_curve[-1][1]
        portfolio_equity.append(total)

    # Portfolio Sharpe from combined returns
    portfolio_returns = _compute_returns(portfolio_equity) if len(portfolio_equity) > 1 else []
    # Use average annualization factor for portfolio
    avg_factor = (
        sum(annualization_factors.values()) / len(annualization_factors)
        if annualization_factors else math.sqrt(252)
    )
    portfolio_sharpe = _compute_sharpe(portfolio_returns, avg_factor)

    # Portfolio max drawdown
    max_portfolio_dd = _compute_max_drawdown(portfolio_equity) if portfolio_equity else 0.0

    # Instrument return correlation
    correlation = _compute_correlation(all_returns, instruments)

    return PortfolioMetrics(
        portfolio_sharpe=portfolio_sharpe,
        max_portfolio_drawdown=max_portfolio_dd,
        instrument_correlation=correlation,
        per_instrument=per_instrument,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _compute_returns(equity_values: list[float]) -> list[float]:
    """Compute period-over-period returns from equity values."""
    if len(equity_values) < 2:
        return []
    returns = []
    for i in range(1, len(equity_values)):
        prev = equity_values[i - 1]
        if prev != 0:
            returns.append((equity_values[i] - prev) / prev)
        else:
            returns.append(0.0)
    return returns


def _compute_sharpe(returns: list[float], annualization_factor: float) -> float:
    """Sharpe ratio = (mean_return / std_return) × annualization_factor."""
    if len(returns) < 2:
        return 0.0
    mean_ret = sum(returns) / len(returns)
    variance = sum((r - mean_ret) ** 2 for r in returns) / (len(returns) - 1)
    std_ret = math.sqrt(variance)
    if std_ret == 0:
        return 0.0
    return (mean_ret / std_ret) * annualization_factor


def _compute_profit_factor(trades: Sequence[object]) -> float:
    """Profit factor = sum(winning PnL) / abs(sum(losing PnL))."""
    from src.backtest.engine import BacktestTrade

    winning_pnl = sum(t.pnl for t in trades if isinstance(t, BacktestTrade) and t.pnl > 0)
    losing_pnl = sum(t.pnl for t in trades if isinstance(t, BacktestTrade) and t.pnl <= 0)

    if losing_pnl == 0:
        return _PF_CAP if winning_pnl > 0 else 0.0
    return winning_pnl / abs(losing_pnl)


def _compute_max_drawdown(equity_values: list[float]) -> float:
    """Max drawdown = max(peak - trough) / peak from equity curve."""
    if len(equity_values) < 2:
        return 0.0
    peak = equity_values[0]
    max_dd = 0.0
    for v in equity_values:
        if v > peak:
            peak = v
        dd = (peak - v) / peak if peak > 0 else 0.0
        if dd > max_dd:
            max_dd = dd
    return max_dd


def _compute_calibration_error(
    trades: Sequence[object],
    predicted_probabilities: Sequence[float] | None,
) -> float:
    """Max absolute calibration error per decile bin.

    Returns 0.0 if predicted_probabilities is None or empty.
    """
    from src.backtest.engine import BacktestTrade

    if predicted_probabilities is None or len(predicted_probabilities) == 0:
        return 0.0

    trade_list = [t for t in trades if isinstance(t, BacktestTrade)]
    if len(trade_list) != len(predicted_probabilities):
        return 0.0

    # Bin by decile (0.0-0.1, 0.1-0.2, ..., 0.9-1.0)
    bins: dict[int, list[tuple[float, bool]]] = {i: [] for i in range(10)}
    for prob, trade in zip(predicted_probabilities, trade_list):
        bin_idx = min(int(prob * 10), 9)
        won = trade.pnl > 0
        bins[bin_idx].append((prob, won))

    max_error = 0.0
    for entries in bins.values():
        if not entries:
            continue
        avg_predicted = sum(p for p, _ in entries) / len(entries)
        observed_freq = sum(1 for _, w in entries if w) / len(entries)
        error = abs(avg_predicted - observed_freq)
        if error > max_error:
            max_error = error

    return max_error


def _compute_correlation(
    all_returns: dict[str, list[float]],
    instruments: list[str],
) -> float:
    """Pearson correlation between instrument returns.

    Returns 0.0 if fewer than 2 instruments or insufficient data.
    """
    if len(instruments) < 2:
        return 0.0

    # For 2 instruments, compute pairwise correlation
    # For >2, average pairwise correlations
    pairs: list[float] = []
    for i in range(len(instruments)):
        for j in range(i + 1, len(instruments)):
            r1 = all_returns.get(instruments[i], [])
            r2 = all_returns.get(instruments[j], [])
            corr = _pearson(r1, r2)
            if corr is not None:
                pairs.append(corr)

    return sum(pairs) / len(pairs) if pairs else 0.0


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    """Pearson correlation coefficient. Returns None if insufficient data."""
    n = min(len(xs), len(ys))
    if n < 3:
        return None

    xs = xs[:n]
    ys = ys[:n]

    mean_x = sum(xs) / n
    mean_y = sum(ys) / n

    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / (n - 1)
    var_x = sum((x - mean_x) ** 2 for x in xs) / (n - 1)
    var_y = sum((y - mean_y) ** 2 for y in ys) / (n - 1)

    denom = math.sqrt(var_x * var_y)
    if denom == 0:
        return None
    return cov / denom
