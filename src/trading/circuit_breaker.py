"""Circuit breaker system (SPEC §6.5).

Provides 5 circuit breakers with per-instrument, portfolio, and system scope.
The manager tracks state in-memory; the executor and API layers query it
before placing trades. Kill switch flag is set here — position closure is
handled by the caller (executor / API).

Breakers:
  1. daily_loss       — equity drop from day-open >= daily_loss_limit_pct
  2. max_drawdown     — equity drop from ATH >= max_drawdown_pct
  3. consecutive_losses — N consecutive losers (per instrument)
  4. model_degradation — rolling 30-trade Sharpe < 0 (per instrument)
  5. kill_switch       — manual system-wide halt
"""

from __future__ import annotations

import logging
import math
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

logger = logging.getLogger(__name__)

# Maximum trade history kept per instrument for Sharpe calculation
_SHARPE_WINDOW = 30


# ---------------------------------------------------------------------------
# Domain models — frozen per DEC-010
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BreakerState:
    """Snapshot of a single circuit breaker's state."""

    name: str
    tripped: bool
    tripped_at: datetime | None
    reason: str
    scope: Literal["instrument", "portfolio", "system"]


@dataclass(frozen=True)
class BreakerTrip:
    """Action required when a circuit breaker newly trips (§6.5)."""

    name: str
    instrument: str
    action: str  # "close_positions" | "close_all"


@dataclass(frozen=True)
class CircuitBreakerSnapshot:
    """Point-in-time snapshot of all circuit breaker states."""

    instrument_breakers: dict[str, list[BreakerState]]
    portfolio_breakers: list[BreakerState]
    system_breakers: list[BreakerState]
    any_tripped: bool


# ---------------------------------------------------------------------------
# Internal mutable state containers
# ---------------------------------------------------------------------------


@dataclass
class _InstrumentState:
    """Mutable per-instrument breaker state."""

    daily_loss_tripped: bool = False
    daily_loss_tripped_at: datetime | None = None
    daily_loss_reason: str = ""

    max_drawdown_tripped: bool = False
    max_drawdown_tripped_at: datetime | None = None
    max_drawdown_reason: str = ""

    consecutive_losses: int = 0
    consecutive_loss_tripped: bool = False
    consecutive_loss_tripped_at: datetime | None = None

    model_degradation_tripped: bool = False
    model_degradation_tripped_at: datetime | None = None

    trade_pnls: deque[float] = field(default_factory=lambda: deque(maxlen=_SHARPE_WINDOW))


# ---------------------------------------------------------------------------
# Circuit breaker manager
# ---------------------------------------------------------------------------


class CircuitBreakerManager:
    """Manages all circuit breaker state (SPEC §6.5).

    State is mutable and tracked in-memory. Query via ``is_entry_allowed``
    and ``get_snapshot``. The kill switch flag is set here; position closure
    is the caller's responsibility.
    """

    def __init__(self) -> None:
        self._instruments: dict[str, _InstrumentState] = defaultdict(_InstrumentState)
        self._portfolio_daily_loss_tripped: bool = False
        self._portfolio_daily_loss_tripped_at: datetime | None = None
        self._portfolio_daily_loss_reason: str = ""
        self._portfolio_max_drawdown_tripped: bool = False
        self._portfolio_max_drawdown_tripped_at: datetime | None = None
        self._portfolio_max_drawdown_reason: str = ""
        self._kill_switch_active: bool = False
        self._kill_switch_at: datetime | None = None
        self._kill_switch_reason: str = ""
        # Expose for testing timeout manipulation
        self._consecutive_loss_tripped_at: dict[str, datetime] = {}

    # ------------------------------------------------------------------
    # Equity updates — triggers daily_loss and max_drawdown checks
    # ------------------------------------------------------------------

    def update_equity(
        self,
        *,
        instrument: str,
        day_open_equity: float,
        current_equity: float,
        ath_equity: float,
        daily_loss_limit_pct: float,
        max_drawdown_pct: float,
    ) -> list[BreakerTrip]:
        """Update equity and evaluate daily loss / max drawdown breakers.

        Returns a list of newly tripped breakers with required actions.
        Daily loss latches once tripped — only reset via ``reset_daily()``
        at 00:00 UTC (SPEC §6.5).
        """
        state = self._instruments[instrument]
        now = datetime.now(UTC)
        trips: list[BreakerTrip] = []

        # --- Daily loss check (latching — no auto-untrip on recovery) ---
        if day_open_equity > 0 and not state.daily_loss_tripped:
            loss_pct = (day_open_equity - current_equity) / day_open_equity
            if loss_pct >= daily_loss_limit_pct:
                state.daily_loss_tripped = True
                state.daily_loss_tripped_at = now
                state.daily_loss_reason = (
                    f"daily loss {loss_pct:.2%} >= {daily_loss_limit_pct:.2%}"
                )
                logger.warning(
                    "Circuit breaker TRIPPED [daily_loss] %s: %s",
                    instrument, state.daily_loss_reason,
                )
                trips.append(BreakerTrip(
                    name="daily_loss",
                    instrument=instrument,
                    action="close_positions",
                ))
                # Also trip portfolio-level
                if not self._portfolio_daily_loss_tripped:
                    self._portfolio_daily_loss_tripped = True
                    self._portfolio_daily_loss_tripped_at = now
                    self._portfolio_daily_loss_reason = (
                        f"daily loss on {instrument}: {loss_pct:.2%}"
                    )

        # --- Max drawdown check ---
        if ath_equity > 0:
            drawdown_pct = (ath_equity - current_equity) / ath_equity
            if drawdown_pct >= max_drawdown_pct:
                if not state.max_drawdown_tripped:
                    state.max_drawdown_tripped = True
                    state.max_drawdown_tripped_at = now
                    state.max_drawdown_reason = (
                        f"drawdown {drawdown_pct:.2%} >= {max_drawdown_pct:.2%}"
                    )
                    logger.warning(
                        "Circuit breaker TRIPPED [max_drawdown] %s: %s",
                        instrument, state.max_drawdown_reason,
                    )
                    trips.append(BreakerTrip(
                        name="max_drawdown",
                        instrument=instrument,
                        action="close_all",
                    ))
                if not self._portfolio_max_drawdown_tripped:
                    self._portfolio_max_drawdown_tripped = True
                    self._portfolio_max_drawdown_tripped_at = now
                    self._portfolio_max_drawdown_reason = (
                        f"drawdown on {instrument}: {drawdown_pct:.2%}"
                    )

        return trips

    # ------------------------------------------------------------------
    # Trade result recording — triggers consecutive loss & model degradation
    # ------------------------------------------------------------------

    def record_trade_result(
        self,
        instrument: str,
        pnl: float,
        *,
        consecutive_loss_halt: int = 5,
    ) -> None:
        """Record a completed trade PnL for an instrument.

        Updates consecutive loss counter and rolling Sharpe window.
        Eagerly trips consecutive_loss breaker when threshold is reached.
        """
        state = self._instruments[instrument]

        # Consecutive loss tracking
        if pnl < 0:
            state.consecutive_losses += 1
            # Eagerly trip when threshold reached
            if (
                state.consecutive_losses >= consecutive_loss_halt
                and not state.consecutive_loss_tripped
            ):
                now = datetime.now(UTC)
                state.consecutive_loss_tripped = True
                state.consecutive_loss_tripped_at = now
                self._consecutive_loss_tripped_at[instrument] = now
                logger.warning(
                    "Circuit breaker TRIPPED [consecutive_losses] %s: "
                    "%d consecutive losses >= %d",
                    instrument, state.consecutive_losses, consecutive_loss_halt,
                )
        else:
            state.consecutive_losses = 0
            state.consecutive_loss_tripped = False
            state.consecutive_loss_tripped_at = None
            self._consecutive_loss_tripped_at.pop(instrument, None)

        # Rolling trade PnL for Sharpe
        state.trade_pnls.append(pnl)

        # Eagerly evaluate model degradation
        if len(state.trade_pnls) >= _SHARPE_WINDOW:
            sharpe = _rolling_sharpe(state.trade_pnls)
            if sharpe < 0:
                if not state.model_degradation_tripped:
                    state.model_degradation_tripped = True
                    state.model_degradation_tripped_at = datetime.now(UTC)
                    logger.warning(
                        "Circuit breaker TRIPPED [model_degradation] %s: "
                        "30-trade Sharpe %.3f < 0",
                        instrument, sharpe,
                    )
            else:
                state.model_degradation_tripped = False
                state.model_degradation_tripped_at = None

    # ------------------------------------------------------------------
    # Query: is entry allowed?
    # ------------------------------------------------------------------

    def is_entry_allowed(self, instrument: str) -> bool:
        """Check if new entries are allowed for an instrument.

        Returns False if ANY breaker is tripped for this instrument,
        at portfolio level, or system-wide. Breaker states are set
        eagerly by ``update_equity`` and ``record_trade_result``.
        """
        if self._kill_switch_active:
            return False

        if self._portfolio_daily_loss_tripped:
            return False

        if self._portfolio_max_drawdown_tripped:
            return False

        state = self._instruments[instrument]

        if state.daily_loss_tripped:
            return False

        if state.max_drawdown_tripped:
            return False

        if state.consecutive_loss_tripped:
            return False

        if state.model_degradation_tripped:
            return False

        return True

    # ------------------------------------------------------------------
    # Kill switch
    # ------------------------------------------------------------------

    def activate_kill_switch(self, reason: str) -> None:
        """Activate system-wide kill switch (SPEC §6.5)."""
        self._kill_switch_active = True
        self._kill_switch_at = datetime.now(UTC)
        self._kill_switch_reason = reason
        logger.critical("KILL SWITCH ACTIVATED: %s", reason)

    def deactivate_kill_switch(self) -> None:
        """Deactivate kill switch (manual reset only)."""
        self._kill_switch_active = False
        self._kill_switch_at = None
        self._kill_switch_reason = ""
        logger.info("Kill switch deactivated")

    def is_kill_switch_active(self) -> bool:
        """Check if kill switch is active."""
        return self._kill_switch_active

    # ------------------------------------------------------------------
    # Resets
    # ------------------------------------------------------------------

    def reset_daily(self) -> None:
        """Auto-reset daily loss breakers at 00:00 UTC."""
        for state in self._instruments.values():
            state.daily_loss_tripped = False
            state.daily_loss_tripped_at = None
            state.daily_loss_reason = ""
        self._portfolio_daily_loss_tripped = False
        self._portfolio_daily_loss_tripped_at = None
        self._portfolio_daily_loss_reason = ""
        logger.info("Daily loss breakers reset")

    def reset_max_drawdown(self, instrument: str | None = None) -> None:
        """Manual reset of max drawdown breaker.

        Args:
            instrument: Specific instrument to reset, or None for all.
        """
        if instrument is not None:
            state = self._instruments[instrument]
            state.max_drawdown_tripped = False
            state.max_drawdown_tripped_at = None
            state.max_drawdown_reason = ""
            # Re-evaluate portfolio flag: only clear if no other instruments tripped
            if not any(
                s.max_drawdown_tripped
                for s in self._instruments.values()
            ):
                self._portfolio_max_drawdown_tripped = False
                self._portfolio_max_drawdown_tripped_at = None
                self._portfolio_max_drawdown_reason = ""
        else:
            for state in self._instruments.values():
                state.max_drawdown_tripped = False
                state.max_drawdown_tripped_at = None
                state.max_drawdown_reason = ""
            self._portfolio_max_drawdown_tripped = False
            self._portfolio_max_drawdown_tripped_at = None
            self._portfolio_max_drawdown_reason = ""
        logger.info("Max drawdown breaker reset: %s", instrument or "all")

    def try_auto_reset_consecutive(
        self,
        *,
        consecutive_loss_halt_hours: int = 24,
    ) -> None:
        """Auto-reset consecutive loss breakers after timeout."""
        now = datetime.now(UTC)
        for instrument in list(self._consecutive_loss_tripped_at):
            tripped_at = self._consecutive_loss_tripped_at[instrument]
            elapsed_hours = (now - tripped_at).total_seconds() / 3600
            if elapsed_hours >= consecutive_loss_halt_hours:
                state = self._instruments[instrument]
                state.consecutive_losses = 0
                state.consecutive_loss_tripped = False
                state.consecutive_loss_tripped_at = None
                del self._consecutive_loss_tripped_at[instrument]
                logger.info(
                    "Consecutive loss breaker auto-reset for %s after %.1fh",
                    instrument, elapsed_hours,
                )

    # ------------------------------------------------------------------
    # Snapshot
    # ------------------------------------------------------------------

    def get_snapshot(self) -> CircuitBreakerSnapshot:
        """Generate a point-in-time snapshot of all breaker states."""
        instrument_breakers: dict[str, list[BreakerState]] = {}

        for instrument, state in self._instruments.items():
            breakers: list[BreakerState] = []

            # Daily loss
            breakers.append(BreakerState(
                name="daily_loss",
                tripped=state.daily_loss_tripped,
                tripped_at=state.daily_loss_tripped_at,
                reason=state.daily_loss_reason,
                scope="instrument",
            ))

            # Max drawdown
            breakers.append(BreakerState(
                name="max_drawdown",
                tripped=state.max_drawdown_tripped,
                tripped_at=state.max_drawdown_tripped_at,
                reason=state.max_drawdown_reason,
                scope="instrument",
            ))

            # Consecutive losses
            breakers.append(BreakerState(
                name="consecutive_losses",
                tripped=state.consecutive_loss_tripped,
                tripped_at=state.consecutive_loss_tripped_at,
                reason=(
                    f"{state.consecutive_losses} consecutive losses"
                    if state.consecutive_loss_tripped else ""
                ),
                scope="instrument",
            ))

            # Model degradation
            breakers.append(BreakerState(
                name="model_degradation",
                tripped=state.model_degradation_tripped,
                tripped_at=state.model_degradation_tripped_at,
                reason="30-trade Sharpe < 0" if state.model_degradation_tripped else "",
                scope="instrument",
            ))

            instrument_breakers[instrument] = breakers

        # Portfolio breakers
        portfolio_breakers: list[BreakerState] = [
            BreakerState(
                name="daily_loss",
                tripped=self._portfolio_daily_loss_tripped,
                tripped_at=self._portfolio_daily_loss_tripped_at,
                reason=self._portfolio_daily_loss_reason,
                scope="portfolio",
            ),
            BreakerState(
                name="max_drawdown",
                tripped=self._portfolio_max_drawdown_tripped,
                tripped_at=self._portfolio_max_drawdown_tripped_at,
                reason=self._portfolio_max_drawdown_reason,
                scope="portfolio",
            ),
        ]

        # System breakers
        system_breakers: list[BreakerState] = [
            BreakerState(
                name="kill_switch",
                tripped=self._kill_switch_active,
                tripped_at=self._kill_switch_at,
                reason=self._kill_switch_reason,
                scope="system",
            ),
        ]

        # Any tripped?
        any_tripped = (
            self._kill_switch_active
            or self._portfolio_daily_loss_tripped
            or self._portfolio_max_drawdown_tripped
            or any(
                s.daily_loss_tripped
                or s.max_drawdown_tripped
                or s.consecutive_loss_tripped
                or s.model_degradation_tripped
                for s in self._instruments.values()
            )
        )

        return CircuitBreakerSnapshot(
            instrument_breakers=instrument_breakers,
            portfolio_breakers=portfolio_breakers,
            system_breakers=system_breakers,
            any_tripped=any_tripped,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _rolling_sharpe(pnls: deque[float]) -> float:
    """Compute Sharpe ratio over a deque of PnL values.

    Returns 0.0 if standard deviation is zero (all identical returns).
    """
    n = len(pnls)
    if n == 0:
        return 0.0

    mean = sum(pnls) / n
    variance = sum((x - mean) ** 2 for x in pnls) / n
    std = math.sqrt(variance)

    if std == 0:
        return 0.0 if mean == 0 else (math.inf if mean > 0 else -math.inf)

    return mean / std
