"""Broker adapter protocol and trading domain models (SPEC §3.3, §5.9).

Defines the abstract BrokerAdapter interface and frozen dataclasses for
account info, positions, order results, and order status. All broker
implementations (Oanda, Binance) satisfy this protocol.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol, runtime_checkable

from src.data.fetcher_base import CandleRecord

# ---------------------------------------------------------------------------
# Type literals — must match trades table CHECK constraints
# ---------------------------------------------------------------------------

Direction = Literal["BUY", "SELL"]
TradeStatus = Literal["PENDING", "OPEN", "CLOSED", "CANCELLED", "REJECTED"]
OrderState = Literal["PENDING", "FILLED", "CANCELLED", "REJECTED"]


# ---------------------------------------------------------------------------
# Domain models — all frozen per DEC-010
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AccountInfo:
    """Broker account summary."""

    balance: float
    currency: str
    unrealized_pnl: float
    margin_used: float
    margin_available: float


@dataclass(frozen=True)
class Position:
    """A single open position as reported by the broker."""

    instrument: str
    direction: Direction
    units: float
    entry_price: float
    unrealized_pnl: float
    stop_loss: float | None
    trade_id: str


@dataclass(frozen=True)
class OrderResult:
    """Result of a place/modify/close order request."""

    success: bool
    order_id: str | None
    client_order_id: str
    instrument: str
    direction: Direction
    units: float
    fill_price: float | None
    timestamp: datetime
    error_message: str | None


@dataclass(frozen=True)
class OrderStatus:
    """Status of an order looked up by client_order_id."""

    client_order_id: str
    broker_order_id: str | None
    state: OrderState
    fill_price: float | None
    fill_time: datetime | None


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------


def make_client_order_id(instrument: str) -> str:
    """Generate a unique client order ID per SPEC §5.9.

    Format: ``NEWTON-{instrument}-{timestamp_ms}``
    """
    timestamp_ms = int(time.time() * 1000)
    return f"NEWTON-{instrument}-{timestamp_ms}"


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class OrderNotFoundError(Exception):
    """Raised when an order lookup finds no matching order on the broker."""


# ---------------------------------------------------------------------------
# Protocol — per DEC-005 (no inheritance)
# ---------------------------------------------------------------------------


@runtime_checkable
class BrokerAdapter(Protocol):
    """Abstract broker interface. Implemented per broker (SPEC §3.3).

    All methods are synchronous, matching the codebase convention
    established in DEC-013 (sync batch signature for FeatureProvider).
    """

    def get_candles(
        self,
        instrument: str,
        interval: str,
        start: datetime,
        end: datetime,
    ) -> list[CandleRecord]: ...

    def get_account(self) -> AccountInfo: ...

    def get_positions(self) -> list[Position]: ...

    def place_market_order(
        self,
        instrument: str,
        units: float,
        stop_loss: float,
        client_order_id: str,
    ) -> OrderResult: ...

    def modify_stop_loss(self, trade_id: str, new_stop: float) -> OrderResult: ...

    def close_position(self, trade_id: str) -> OrderResult: ...

    def get_order_status(self, client_order_id: str) -> OrderStatus: ...
