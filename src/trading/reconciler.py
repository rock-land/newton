"""Position reconciliation loop (SPEC §5.12).

Compares broker-reported positions against internal trade records
(status=OPEN) and classifies mismatches into MATCH, SYSTEM_EXTRA,
or BROKER_EXTRA states.  Runs per-broker at a 60-second cadence.

SYSTEM_EXTRA  — internal record exists but broker has no matching position.
                Trade is marked CLOSED with exit_reason='RECONCILIATION'.

BROKER_EXTRA  — broker has a position the system doesn't know about.
                Entries for that instrument are halted until manual review.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any, Literal, Protocol

from src.trading.broker_base import BrokerAdapter, Position
from src.trading.executor import TradeRecord, TradeStore

logger = logging.getLogger(__name__)

ReconciliationStatus = Literal["MATCH", "SYSTEM_EXTRA", "BROKER_EXTRA"]


# ---------------------------------------------------------------------------
# Domain models — frozen per DEC-010
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReconciliationResult:
    """Single reconciliation check outcome (§5.12)."""

    checked_at: datetime
    broker: str
    instrument: str
    status: ReconciliationStatus
    details: dict[str, Any]
    resolved: bool


# ---------------------------------------------------------------------------
# ReconciliationStore protocol — persistence abstraction (DEC-005)
# ---------------------------------------------------------------------------


class ReconciliationStore(Protocol):
    """Persistence layer for reconciliation results."""

    def save_result(self, result: ReconciliationResult) -> None: ...

    def get_unresolved(self) -> list[ReconciliationResult]: ...

    def mark_resolved(self, index: int) -> None: ...


class InMemoryReconciliationStore:
    """In-memory implementation of ReconciliationStore for testing."""

    def __init__(self) -> None:
        self._results: list[ReconciliationResult] = []

    def save_result(self, result: ReconciliationResult) -> None:
        self._results.append(result)

    def get_unresolved(self) -> list[ReconciliationResult]:
        return [r for r in self._results if not r.resolved]

    def mark_resolved(self, index: int) -> None:
        if index < 0 or index >= len(self._results):
            msg = f"index out of range: {index}"
            raise IndexError(msg)
        current = self._results[index]
        self._results[index] = replace(current, resolved=True)


# ---------------------------------------------------------------------------
# PositionReconciler
# ---------------------------------------------------------------------------


class PositionReconciler:
    """Compares broker positions with internal trade records (SPEC §5.12).

    Runs per-broker.  The caller is responsible for scheduling at 60s
    intervals.  Maintains a set of halted instruments for BROKER_EXTRA
    cases that require manual review.
    """

    def __init__(
        self,
        *,
        broker: BrokerAdapter,
        broker_name: str,
        trade_store: TradeStore,
        recon_store: ReconciliationStore,
        circuit_breaker: object,
    ) -> None:
        self._broker = broker
        self._broker_name = broker_name
        self._trade_store = trade_store
        self._recon_store = recon_store
        self._circuit_breaker = circuit_breaker
        self._halted_instruments: set[str] = set()

    # ------------------------------------------------------------------
    # Main reconciliation
    # ------------------------------------------------------------------

    def reconcile(self) -> list[ReconciliationResult]:
        """Run one reconciliation cycle per §5.12.

        1. Fetch broker positions.
        2. Fetch internal OPEN trades for this broker.
        3. Classify each (instrument, direction) pair.
        4. Execute actions for mismatches.
        5. Persist results.

        Returns list of ReconciliationResult for this cycle.
        """
        now = datetime.now(UTC)

        # 1. Fetch broker positions
        try:
            broker_positions = self._broker.get_positions()
        except Exception:
            logger.error(
                "Reconciliation failed: cannot fetch positions from %s",
                self._broker_name,
                exc_info=True,
            )
            return []

        # 2. Fetch internal OPEN trades, filtered to this broker
        all_open = self._trade_store.get_open_trades(None)
        internal_trades = [
            t for t in all_open
            if t.broker == self._broker_name and t.broker_order_id is not None
        ]

        # 3. Build lookup maps keyed by (instrument, direction)
        _Key = tuple[str, str]
        broker_map: dict[_Key, list[Position]] = {}
        for pos in broker_positions:
            key: _Key = (pos.instrument, pos.direction)
            broker_map.setdefault(key, []).append(pos)

        internal_map: dict[_Key, list[TradeRecord]] = {}
        for trade in internal_trades:
            key = (trade.instrument, trade.direction)
            internal_map.setdefault(key, []).append(trade)

        # 4. Collect all unique keys
        all_keys: set[_Key] = set(broker_map.keys()) | set(internal_map.keys())

        results: list[ReconciliationResult] = []

        for key in sorted(all_keys):
            instrument, direction = key
            broker_group = broker_map.get(key, [])
            internal_group = internal_map.get(key, [])

            has_broker = len(broker_group) > 0
            has_internal = len(internal_group) > 0

            if has_broker and has_internal:
                # MATCH
                result = ReconciliationResult(
                    checked_at=now,
                    broker=self._broker_name,
                    instrument=instrument,
                    status="MATCH",
                    details={
                        "direction": direction,
                        "broker_count": len(broker_group),
                        "internal_count": len(internal_group),
                    },
                    resolved=True,
                )
                results.append(result)
                logger.debug(
                    "Reconciliation MATCH: %s %s (%d broker, %d internal)",
                    instrument, direction,
                    len(broker_group), len(internal_group),
                )

            elif has_internal and not has_broker:
                # SYSTEM_EXTRA — internal thinks open, broker does not
                for trade in internal_group:
                    self._handle_system_extra(trade, now)
                    result = ReconciliationResult(
                        checked_at=now,
                        broker=self._broker_name,
                        instrument=instrument,
                        status="SYSTEM_EXTRA",
                        details={
                            "direction": direction,
                            "client_order_id": trade.client_order_id,
                            "broker_order_id": trade.broker_order_id,
                        },
                        resolved=False,
                    )
                    results.append(result)

            elif has_broker and not has_internal:
                # BROKER_EXTRA — broker has position system doesn't know
                for pos in broker_group:
                    self._handle_broker_extra(pos, instrument, now)
                    result = ReconciliationResult(
                        checked_at=now,
                        broker=self._broker_name,
                        instrument=instrument,
                        status="BROKER_EXTRA",
                        details={
                            "direction": direction,
                            "trade_id": pos.trade_id,
                            "units": pos.units,
                            "entry_price": pos.entry_price,
                        },
                        resolved=False,
                    )
                    results.append(result)

        # 5. Persist all results
        for r in results:
            self._recon_store.save_result(r)

        return results

    # ------------------------------------------------------------------
    # Halt management
    # ------------------------------------------------------------------

    def is_instrument_halted(self, instrument: str) -> bool:
        """Check if entries are halted due to unresolved BROKER_EXTRA."""
        return instrument in self._halted_instruments

    def clear_halt(self, instrument: str) -> None:
        """Manual review complete — clear the halt for an instrument."""
        if instrument in self._halted_instruments:
            self._halted_instruments.discard(instrument)
            logger.info("Halt cleared for %s", instrument)

    # ------------------------------------------------------------------
    # Internal handlers
    # ------------------------------------------------------------------

    def _handle_system_extra(self, trade: TradeRecord, now: datetime) -> None:
        """Handle SYSTEM_EXTRA: mark trade CLOSED with RECONCILIATION reason."""
        self._trade_store.update_trade(
            trade.client_order_id,
            status="CLOSED",
            exit_time=now,
            exit_reason="RECONCILIATION",
        )
        logger.critical(
            "SYSTEM_EXTRA: trade %s (%s %s) open internally but not on broker %s — "
            "marked CLOSED",
            trade.client_order_id, trade.instrument, trade.direction,
            self._broker_name,
        )

    def _handle_broker_extra(
        self, pos: Position, instrument: str, now: datetime,
    ) -> None:
        """Handle BROKER_EXTRA: halt entries and log critical alert."""
        self._halted_instruments.add(instrument)
        logger.critical(
            "BROKER_EXTRA: broker %s has position %s (%s %s, %.2f units) "
            "not tracked internally — entries halted for %s, manual review required",
            self._broker_name, pos.trade_id, instrument, pos.direction,
            pos.units, instrument,
        )
