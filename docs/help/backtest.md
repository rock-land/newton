# Backtesting

The Backtest page lets you run historical simulations and analyze trading strategy performance.

## Running a Backtest

1. Select an **instrument** (EUR_USD or BTC_USD)
2. Set the **date range** (start and end dates)
3. Optionally enable **pessimistic mode** (doubles slippage and spread assumptions)
4. Set **initial equity** (starting capital)
5. Click "Run Backtest"

The simulation runs on the server and results are displayed when complete.

## Results

### Equity Curve
Shows portfolio value over time. Look for steady growth with controlled drawdowns.

### Performance Metrics
- **Sharpe Ratio** — Risk-adjusted return (target: > 0.8)
- **Profit Factor** — Gross profit / gross loss (target: > 1.3)
- **Max Drawdown** — Largest peak-to-trough decline (target: < 15%)
- **Win Rate** — Percentage of profitable trades
- **Expectancy** — Average expected profit per trade (target: > 0)
- **Calmar Ratio** — Annualized return / max drawdown

### Gate Evaluation
Hard gates that must pass for a strategy to be considered viable. Green badges indicate passing metrics.

### Trade List
Individual trades with entry/exit prices, P&L, duration, and exit reason (stop loss, time stop, signal reversal).

## Comparing Backtests

Select two completed runs to compare side-by-side. Metrics are shown with diff highlighting to quickly identify improvements or regressions.

## Regime Breakdown

Performance broken down by market regime (trending, mean-reverting, volatile, quiet). Low-sample flags warn when a regime has fewer than 20 trades, making statistics unreliable.

## Bias Controls

The bias controls checklist shows which safeguards are in place to prevent overfitting:
- Walk-forward validation (no look-ahead)
- Purged K-fold cross-validation
- Realistic transaction costs
- Survivorship bias awareness
