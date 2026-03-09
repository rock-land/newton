# Strategy Management

The Strategy page lets you view and manage per-instrument trading strategy configurations.

## Current Configuration

Select an instrument to view its active strategy configuration. The JSON viewer shows all parameters including:

- **Signal thresholds** — Probability cutoffs for BUY/SELL actions
- **ML model settings** — XGBoost hyperparameters and training windows
- **Bayesian parameters** — Prior settings, Laplace smoothing alpha, posterior cap
- **Event definitions** — What constitutes a tradeable event for this instrument

## Version History

Every strategy configuration change is versioned. The version history table shows:

- **Version number** — Monotonically incrementing
- **Timestamp** — When the version was created
- **Notes** — Description of what changed

## Comparing Versions

Select two versions to see a side-by-side diff highlighting what changed between them. This is useful for understanding the impact of parameter adjustments.

## Activating a Version

To roll back to a previous configuration, select a version and click "Activate". This makes that version the active strategy for the instrument. The change takes effect immediately for new signal generation.
