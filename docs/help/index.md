# Newton Trading System

Newton is a fully automated multi-instrument trading system that generates sustainable income using a hybrid machine-learning approach (Bayesian + XGBoost) to identify and execute trades across forex and cryptocurrency markets.

## Supported Instruments

- **EUR/USD** — Forex spot via Oanda
- **BTC/USD** — Cryptocurrency spot via Binance

## Key Features

- **Bayesian + ML Signal Generation** — Combines Bayesian inference with XGBoost machine learning for robust trade signals
- **Regime Detection** — Automatically classifies market conditions (trending, mean-reverting, volatile, quiet) to adapt strategy behavior
- **Risk Management** — Comprehensive pre-trade checks, position sizing via Kelly criterion, and circuit breakers
- **Backtesting** — Walk-forward validation with regime-aware reporting and bias controls
- **Real-time Monitoring** — Live trading dashboard with position tracking, signal logs, and kill switch

## Navigation

Use the sidebar to navigate between pages. Each page has a help button (?) in the top-right corner that provides contextual guidance.

## Trading Modes

- **Paper Trading** — Simulated execution against live market data (Oanda practice / Binance testnet)
- **Live Trading** — Real money execution (requires explicit activation)
