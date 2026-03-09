# System Configuration

The Config page lets you manage risk parameters and regime overrides.

## Risk Parameters

Edit the global risk configuration that governs position sizing and trade limits. Key parameters include:

- **max_position_pct** — Maximum portfolio percentage for a single position
- **max_portfolio_exposure** — Total portfolio exposure limit across all instruments
- **kelly_fraction** — Fraction of Kelly criterion to use for position sizing (0.25 = quarter Kelly)
- **max_drawdown_pct** — Maximum drawdown before the circuit breaker trips
- **daily_loss_limit_pct** — Maximum daily loss percentage

Changes are validated before applying. Invalid values (e.g., negative limits) are rejected with an error message. All changes are audit-logged.

### Precedence

Risk parameters follow a 3-tier precedence:
1. **Instrument-level** overrides (in instrument config files)
2. **Strategy-level** settings
3. **Global defaults** (editable on this page)

## Regime Overrides

Manually override the detected market regime for an instrument. This is useful when you disagree with the automated classification or want to force conservative behavior.

- **Set Override** — Choose a regime label (TRENDING, MEAN_REVERTING, VOLATILE, QUIET) and provide a reason
- **Clear Override** — Remove the manual override and return to automated detection

Overrides take effect immediately for all downstream signal generation and risk checks.

## Trading Mode

Shows whether the system is in paper or live trading mode. Mode changes require config file edits and are not available through the UI.
