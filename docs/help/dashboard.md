# Dashboard

The Dashboard provides a high-level overview of system health, portfolio status, and recent activity.

## System Health

The health card shows the current state of database connectivity, broker connections, and candle data freshness. A green status indicates all systems are operational.

## Instrument Status

Each instrument card displays:

- **Last Signal** — The most recent signal action (BUY, SELL, or HOLD) and probability
- **Regime** — Current market regime classification and confidence band
- **Circuit Breakers** — Whether any circuit breakers are tripped for this instrument

## Kill Switch

The kill switch is a safety mechanism that immediately halts all trading activity. When activated:

- All open positions are closed across all brokers
- No new trades are placed
- The switch remains active until manually deactivated

Use the kill switch toggle on the dashboard to activate or deactivate it.

## Recent Alerts

The alerts section shows the most recent system events, including circuit breaker trips, reconciliation mismatches, and signal generation errors.
