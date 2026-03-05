"""Risk management engine (SPEC §6.1–6.4).

Provides config resolution with 3-tier precedence, pre-trade safety checks,
Kelly criterion position sizing, and in-trade control evaluation. Circuit
breaker state is accepted as a parameter — the circuit breaker module (T-505)
owns the state machine.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from src.data.schema import RiskConfig, RiskOverrides, RiskPortfolio
from src.trading.broker_base import AccountInfo, Direction, Position

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Domain models — all frozen per DEC-010
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ResolvedRiskConfig:
    """Fully resolved risk parameters for a single instrument.

    Result of applying 3-tier precedence: instrument > strategy > global.
    """

    max_position_pct: float
    max_risk_per_trade_pct: float
    kelly_fraction: float
    kelly_min_trades: int
    kelly_window: int
    micro_size_pct: float
    hard_stop_pct: float
    trailing_activation_pct: float
    trailing_breakeven_pct: float
    time_stop_hours: int
    daily_loss_limit_pct: float
    max_drawdown_pct: float
    consecutive_loss_halt: int
    consecutive_loss_halt_hours: int
    gap_risk_multiplier: float
    volatility_threshold_multiplier: float
    high_volatility_size_reduction: float
    high_volatility_stop_pct: float


@dataclass(frozen=True)
class CheckResult:
    """Outcome of a single pre-trade check."""

    passed: bool
    detail: str


@dataclass(frozen=True)
class SizingResult:
    """Position sizing calculation output.

    ``units`` is the dollar risk amount (equity × risk_pct). Conversion to
    instrument units requires the current price and stop distance, which is
    done by the executor at order placement time.
    """

    units: float  # Dollar risk amount, NOT instrument units
    risk_pct: float
    method: str  # "kelly" | "micro"


@dataclass(frozen=True)
class PreTradeResult:
    """Aggregate result of all pre-trade checks."""

    approved: bool
    reason: str | None
    position_size: float
    checks: dict[str, CheckResult]


@dataclass(frozen=True)
class InTradeAction:
    """Decision from in-trade control evaluation."""

    action: Literal["HOLD", "MOVE_STOP", "CLOSE"]
    new_stop: float | None
    reason: str


# ---------------------------------------------------------------------------
# Config resolution (§6.1)
# ---------------------------------------------------------------------------

# Fields that can be overridden at instrument/strategy level
_OVERRIDE_FIELDS = (
    "max_position_pct",
    "max_risk_per_trade_pct",
    "kelly_fraction",
    "kelly_min_trades",
    "kelly_window",
    "micro_size_pct",
    "hard_stop_pct",
    "trailing_activation_pct",
    "trailing_breakeven_pct",
    "time_stop_hours",
    "daily_loss_limit_pct",
    "max_drawdown_pct",
    "consecutive_loss_halt",
    "consecutive_loss_halt_hours",
    "gap_risk_multiplier",
    "volatility_threshold_multiplier",
    "high_volatility_size_reduction",
    "high_volatility_stop_pct",
)


def resolve_risk_config(
    global_config: RiskConfig,
    instrument_overrides: RiskOverrides,
    strategy_overrides: RiskOverrides,
) -> ResolvedRiskConfig:
    """Merge 3-tier risk config: instrument > strategy > global (§6.1)."""
    resolved: dict[str, object] = {}

    for field in _OVERRIDE_FIELDS:
        # Highest precedence: instrument override
        inst_val = getattr(instrument_overrides, field, None)
        if inst_val is not None:
            resolved[field] = inst_val
            continue

        # Second: strategy override
        strat_val = getattr(strategy_overrides, field, None)
        if strat_val is not None:
            resolved[field] = strat_val
            continue

        # Fallback: global default
        resolved[field] = getattr(global_config.defaults, field)

    return ResolvedRiskConfig(**resolved)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Kelly criterion sizing (§6.3)
# ---------------------------------------------------------------------------


def kelly_size(
    *,
    win_rate: float,
    avg_win: float,
    avg_loss: float,
    equity: float,
    config: ResolvedRiskConfig,
    regime_confidence: float | None,
    num_trades: int,
) -> SizingResult:
    """Compute position size using Kelly criterion (§6.3).

    First ``kelly_min_trades`` trades: fixed ``micro_size_pct``.
    Negative Kelly → fallback to micro size.
    Low regime confidence (< 0.2) → reduce by 50%.
    Capped by ``max_risk_per_trade_pct`` and ``max_position_pct``.
    """
    if equity <= 0:
        return SizingResult(units=0.0, risk_pct=0.0, method="micro")

    # Early trades → micro size
    if num_trades < config.kelly_min_trades:
        risk_pct = config.micro_size_pct
        units = equity * risk_pct
        if regime_confidence is not None and regime_confidence < 0.2:
            units *= 0.5
        return SizingResult(units=units, risk_pct=risk_pct, method="micro")

    # Kelly formula: f* = kelly_fraction × (p × b - q) / b
    p = win_rate
    q = 1.0 - win_rate
    b = avg_win / avg_loss if avg_loss > 0 else 0.0

    if b <= 0:
        risk_pct = config.micro_size_pct
        units = equity * risk_pct
        if regime_confidence is not None and regime_confidence < 0.2:
            units *= 0.5
        return SizingResult(units=units, risk_pct=risk_pct, method="micro")

    f_star = config.kelly_fraction * (p * b - q) / b

    # Negative Kelly → micro fallback
    if f_star <= 0:
        risk_pct = config.micro_size_pct
        units = equity * risk_pct
        if regime_confidence is not None and regime_confidence < 0.2:
            units *= 0.5
        return SizingResult(units=units, risk_pct=risk_pct, method="micro")

    # Cap by max_risk_per_trade_pct
    risk_pct = min(f_star, config.max_risk_per_trade_pct)

    # Compute units, cap by max_position_pct
    units = equity * risk_pct
    max_units = equity * config.max_position_pct
    units = min(units, max_units)

    # Low regime confidence → 50% reduction (§6.3)
    if regime_confidence is not None and regime_confidence < 0.2:
        units *= 0.5

    return SizingResult(units=units, risk_pct=risk_pct, method="kelly")


# ---------------------------------------------------------------------------
# Pre-trade checks (§6.3)
# ---------------------------------------------------------------------------


def run_pre_trade_checks(
    *,
    instrument: str,
    signal_direction: Direction,
    account: AccountInfo,
    open_positions: list[Position],
    risk_config: ResolvedRiskConfig,
    portfolio_config: RiskPortfolio,
    circuit_breaker_ok: bool,
    last_candle_time: datetime,
    signal_interval_seconds: int,
    last_retrain_days: int | None,
    regime_confidence: float | None,
    win_rate: float,
    avg_win: float,
    avg_loss: float,
    num_trades: int,
) -> PreTradeResult:
    """Run all pre-trade safety checks per §6.3.

    Returns approved=True only if all blocking checks pass.
    Model freshness is a warning (non-blocking).
    """
    checks: dict[str, CheckResult] = {}

    # 1. Position limit: max 1 open per instrument
    same_instrument = [p for p in open_positions if p.instrument == instrument]
    if same_instrument:
        checks["position_limit"] = CheckResult(
            passed=False,
            detail=f"already have {len(same_instrument)} open position(s) for {instrument}",
        )
    else:
        checks["position_limit"] = CheckResult(passed=True, detail="ok")

    # 2. Portfolio exposure: total units*entry_price / equity < max_total_exposure_pct
    equity = account.balance
    total_exposure = sum(p.units * p.entry_price for p in open_positions)
    exposure_pct = total_exposure / equity if equity > 0 else 0.0
    if exposure_pct >= portfolio_config.max_total_exposure_pct:
        checks["portfolio_exposure"] = CheckResult(
            passed=False,
            detail=f"exposure {exposure_pct:.2%} >= limit {portfolio_config.max_total_exposure_pct:.2%}",
        )
    else:
        checks["portfolio_exposure"] = CheckResult(passed=True, detail="ok")

    # 3. Circuit breaker
    if not circuit_breaker_ok:
        checks["circuit_breaker"] = CheckResult(
            passed=False, detail="circuit breaker tripped",
        )
    else:
        checks["circuit_breaker"] = CheckResult(passed=True, detail="ok")

    # 4. Data freshness: last candle < 2× interval ago
    max_age_seconds = signal_interval_seconds * 2
    age_seconds = (datetime.now(UTC) - last_candle_time).total_seconds()
    if age_seconds > max_age_seconds:
        checks["data_freshness"] = CheckResult(
            passed=False,
            detail=f"last candle {age_seconds:.0f}s ago (limit {max_age_seconds}s)",
        )
    else:
        checks["data_freshness"] = CheckResult(passed=True, detail="ok")

    # 5. Model freshness: warning only (non-blocking)
    if last_retrain_days is not None and last_retrain_days > 30:
        checks["model_freshness"] = CheckResult(
            passed=False,
            detail=f"last retrain {last_retrain_days}d ago (> 30d)",
        )
        logger.warning(
            "Model freshness warning for %s: %dd since retrain",
            instrument, last_retrain_days,
        )
    else:
        checks["model_freshness"] = CheckResult(passed=True, detail="ok")

    # 6. Regime confidence
    if regime_confidence is not None and regime_confidence < 0.2:
        checks["regime_confidence"] = CheckResult(
            passed=False,
            detail=f"low regime confidence {regime_confidence:.2f} (< 0.2)",
        )
    else:
        checks["regime_confidence"] = CheckResult(passed=True, detail="ok")

    # Determine if any blocking check failed
    # model_freshness is non-blocking (warning only)
    blocking_checks = {
        k: v for k, v in checks.items() if k != "model_freshness"
    }
    blocking_failures = {k: v for k, v in blocking_checks.items() if not v.passed}

    # 7. Position sizing (only if blocking checks pass, except regime_confidence
    # which reduces size but doesn't block)
    hard_failures = {
        k: v for k, v in blocking_failures.items()
        if k != "regime_confidence"
    }

    if hard_failures:
        first_fail = next(iter(hard_failures))
        return PreTradeResult(
            approved=False,
            reason=first_fail,
            position_size=0.0,
            checks=checks,
        )

    # Compute position size
    sizing = kelly_size(
        win_rate=win_rate,
        avg_win=avg_win,
        avg_loss=avg_loss,
        equity=equity,
        config=risk_config,
        regime_confidence=regime_confidence,
        num_trades=num_trades,
    )

    return PreTradeResult(
        approved=True,
        reason=None,
        position_size=sizing.units,
        checks=checks,
    )


# ---------------------------------------------------------------------------
# In-trade controls (§6.4)
# ---------------------------------------------------------------------------


def evaluate_in_trade_controls(
    *,
    entry_price: float,
    current_price: float,
    current_stop: float,
    open_hours: float,
    current_atr: float,
    avg_atr_30d: float,
    config: ResolvedRiskConfig,
    direction: Direction = "BUY",
) -> InTradeAction:
    """Evaluate in-trade controls and return recommended action (§6.4).

    Priority: time stop → volatility → trailing advance → trailing activation → hold.
    Direction-aware: profit and stop targets computed correctly for both BUY and SELL.
    """
    # 1. Time stop
    if open_hours > config.time_stop_hours:
        return InTradeAction(
            action="CLOSE",
            new_stop=None,
            reason=f"time stop: open {open_hours:.1f}h > {config.time_stop_hours}h limit",
        )

    # 2. Volatility check: ATR > multiplier × 30d avg → close
    if avg_atr_30d > 0:
        vol_threshold = config.volatility_threshold_multiplier * avg_atr_30d
        if current_atr > vol_threshold:
            return InTradeAction(
                action="CLOSE",
                new_stop=None,
                reason=f"volatility: ATR {current_atr:.4f} > {vol_threshold:.4f} threshold",
            )

    # Profit percentage — direction-aware
    if entry_price > 0:
        if direction == "BUY":
            profit_pct = (current_price - entry_price) / entry_price
        else:
            profit_pct = (entry_price - current_price) / entry_price
    else:
        profit_pct = 0.0

    # Trailing stop logic — direction-aware
    if direction == "BUY":
        # BUY: stop moves UP to protect profits
        # 3. Advance: profit >= breakeven_pct → move stop to +activation_pct above entry
        if profit_pct >= config.trailing_breakeven_pct:
            target_stop = entry_price * (1.0 + config.trailing_activation_pct)
            if current_stop < target_stop:
                return InTradeAction(
                    action="MOVE_STOP",
                    new_stop=target_stop,
                    reason=f"trailing advance: profit {profit_pct:.2%} >= {config.trailing_breakeven_pct:.2%}",
                )

        # 4. Activation: profit >= activation_pct → move to breakeven (entry)
        if profit_pct >= config.trailing_activation_pct:
            if current_stop < entry_price:
                return InTradeAction(
                    action="MOVE_STOP",
                    new_stop=entry_price,
                    reason=f"trailing activation: profit {profit_pct:.2%} >= {config.trailing_activation_pct:.2%}",
                )
    else:
        # SELL: stop moves DOWN to protect profits
        # 3. Advance: profit >= breakeven_pct → move stop to -activation_pct below entry
        if profit_pct >= config.trailing_breakeven_pct:
            target_stop = entry_price * (1.0 - config.trailing_activation_pct)
            if current_stop > target_stop:
                return InTradeAction(
                    action="MOVE_STOP",
                    new_stop=target_stop,
                    reason=f"trailing advance: profit {profit_pct:.2%} >= {config.trailing_breakeven_pct:.2%}",
                )

        # 4. Activation: profit >= activation_pct → move to breakeven (entry)
        if profit_pct >= config.trailing_activation_pct:
            if current_stop > entry_price:
                return InTradeAction(
                    action="MOVE_STOP",
                    new_stop=entry_price,
                    reason=f"trailing activation: profit {profit_pct:.2%} >= {config.trailing_activation_pct:.2%}",
                )

    # 5. Hold
    return InTradeAction(action="HOLD", new_stop=None, reason="no trigger")
