# Trading Monitor

The Trading Monitor provides real-time visibility into trading activity, positions, and signals.

## Open Positions

The positions table shows all currently open trades with:

- **Instrument** — Which market the position is in
- **Direction** — BUY (long) or SELL (short)
- **Entry price and time** — When and at what price the position was opened
- **Stop loss** — Current stop-loss level
- **Unrealized P&L** — Current profit or loss based on market price

## Trade History

Browse historical trades with filters for instrument, date range, and status. Each trade shows entry/exit details, P&L, commission, and exit reason.

## Signal Log

Recent signal generation results showing the probability, action, and which generator produced the signal. Useful for understanding why trades were or weren't taken.

## Pause/Resume

You can pause trading for individual instruments without affecting others. When paused:

- No new signals are generated for that instrument
- Existing positions remain open
- Resume to restart signal generation

## Manual Position Close

In emergencies, you can manually close any open position from the positions table. This bypasses normal exit logic and immediately submits a market close order.
