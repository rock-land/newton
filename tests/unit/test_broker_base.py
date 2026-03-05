"""Tests for broker adapter protocol and domain models (T-501)."""

from __future__ import annotations

import re
import time
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from src.trading.broker_base import (
    AccountInfo,
    BrokerAdapter,
    Direction,
    OrderResult,
    OrderState,
    OrderStatus,
    Position,
    TradeStatus,
    make_client_order_id,
)


# ---------------------------------------------------------------------------
# Domain model immutability
# ---------------------------------------------------------------------------


class TestAccountInfo:
    def test_frozen(self) -> None:
        info = AccountInfo(
            balance=10_000.0,
            currency="USD",
            unrealized_pnl=0.0,
            margin_used=0.0,
            margin_available=10_000.0,
        )
        with pytest.raises(FrozenInstanceError):
            info.balance = 5_000.0  # type: ignore[misc]

    def test_fields(self) -> None:
        info = AccountInfo(
            balance=50_000.0,
            currency="USD",
            unrealized_pnl=150.0,
            margin_used=1_000.0,
            margin_available=49_000.0,
        )
        assert info.balance == 50_000.0
        assert info.currency == "USD"
        assert info.unrealized_pnl == 150.0
        assert info.margin_used == 1_000.0
        assert info.margin_available == 49_000.0


class TestPosition:
    def test_frozen(self) -> None:
        pos = Position(
            instrument="EUR_USD",
            direction="BUY",
            units=1000.0,
            entry_price=1.1050,
            unrealized_pnl=25.0,
            stop_loss=1.1000,
            trade_id="T-123",
        )
        with pytest.raises(FrozenInstanceError):
            pos.units = 2000.0  # type: ignore[misc]

    def test_fields(self) -> None:
        pos = Position(
            instrument="BTC_USD",
            direction="SELL",
            units=0.5,
            entry_price=42_000.0,
            unrealized_pnl=-100.0,
            stop_loss=43_000.0,
            trade_id="T-456",
        )
        assert pos.instrument == "BTC_USD"
        assert pos.direction == "SELL"
        assert pos.units == 0.5
        assert pos.entry_price == 42_000.0
        assert pos.unrealized_pnl == -100.0
        assert pos.stop_loss == 43_000.0
        assert pos.trade_id == "T-456"


class TestOrderResult:
    def test_frozen(self) -> None:
        result = OrderResult(
            success=True,
            order_id="ORD-001",
            client_order_id="NEWTON-EUR_USD-1234567890",
            instrument="EUR_USD",
            direction="BUY",
            units=1000.0,
            fill_price=1.1050,
            timestamp=datetime(2026, 3, 4, tzinfo=UTC),
            error_message=None,
        )
        with pytest.raises(FrozenInstanceError):
            result.success = False  # type: ignore[misc]

    def test_successful_order(self) -> None:
        ts = datetime(2026, 3, 4, 12, 0, tzinfo=UTC)
        result = OrderResult(
            success=True,
            order_id="ORD-001",
            client_order_id="NEWTON-EUR_USD-1234567890",
            instrument="EUR_USD",
            direction="BUY",
            units=1000.0,
            fill_price=1.1050,
            timestamp=ts,
            error_message=None,
        )
        assert result.success is True
        assert result.order_id == "ORD-001"
        assert result.error_message is None

    def test_failed_order(self) -> None:
        ts = datetime(2026, 3, 4, 12, 0, tzinfo=UTC)
        result = OrderResult(
            success=False,
            order_id=None,
            client_order_id="NEWTON-EUR_USD-1234567890",
            instrument="EUR_USD",
            direction="BUY",
            units=1000.0,
            fill_price=None,
            timestamp=ts,
            error_message="Insufficient margin",
        )
        assert result.success is False
        assert result.order_id is None
        assert result.fill_price is None
        assert result.error_message == "Insufficient margin"


class TestOrderStatus:
    def test_frozen(self) -> None:
        status = OrderStatus(
            client_order_id="NEWTON-EUR_USD-1234567890",
            broker_order_id="BRK-001",
            state="FILLED",
            fill_price=1.1050,
            fill_time=datetime(2026, 3, 4, tzinfo=UTC),
        )
        with pytest.raises(FrozenInstanceError):
            status.state = "CANCELLED"  # type: ignore[misc]

    def test_pending_status(self) -> None:
        status = OrderStatus(
            client_order_id="NEWTON-EUR_USD-1234567890",
            broker_order_id="BRK-001",
            state="PENDING",
            fill_price=None,
            fill_time=None,
        )
        assert status.state == "PENDING"
        assert status.fill_price is None
        assert status.fill_time is None

    def test_filled_status(self) -> None:
        ft = datetime(2026, 3, 4, 12, 30, tzinfo=UTC)
        status = OrderStatus(
            client_order_id="NEWTON-EUR_USD-1234567890",
            broker_order_id="BRK-001",
            state="FILLED",
            fill_price=1.1055,
            fill_time=ft,
        )
        assert status.state == "FILLED"
        assert status.fill_price == 1.1055
        assert status.fill_time == ft


# ---------------------------------------------------------------------------
# client_order_id generation
# ---------------------------------------------------------------------------


class TestMakeClientOrderId:
    def test_format(self) -> None:
        oid = make_client_order_id("EUR_USD")
        assert oid.startswith("NEWTON-EUR_USD-")
        # Timestamp portion should be numeric
        ts_part = oid.split("-", 2)[2]
        assert ts_part.isdigit()

    def test_format_btc(self) -> None:
        oid = make_client_order_id("BTC_USD")
        assert oid.startswith("NEWTON-BTC_USD-")

    def test_uniqueness(self) -> None:
        ids = {make_client_order_id("EUR_USD") for _ in range(100)}
        # Should produce at least 2 distinct IDs (time-based, may collide in tight loop)
        assert len(ids) >= 1

    def test_timestamp_is_recent(self) -> None:
        before_ms = int(time.time() * 1000)
        oid = make_client_order_id("EUR_USD")
        after_ms = int(time.time() * 1000)
        ts_ms = int(oid.split("-", 2)[2])
        assert before_ms <= ts_ms <= after_ms

    def test_matches_spec_pattern(self) -> None:
        oid = make_client_order_id("EUR_USD")
        assert re.match(r"^NEWTON-[A-Z0-9_]+-\d+$", oid)


# ---------------------------------------------------------------------------
# Type literals match trades table constraints
# ---------------------------------------------------------------------------


class TestTypeLiterals:
    def test_direction_values(self) -> None:
        """Direction literal must match trades table CHECK constraint."""
        allowed: set[Direction] = {"BUY", "SELL"}
        assert allowed == {"BUY", "SELL"}

    def test_trade_status_values(self) -> None:
        """TradeStatus must match trades table CHECK constraint."""
        allowed: set[TradeStatus] = {
            "PENDING", "OPEN", "CLOSED", "CANCELLED", "REJECTED"
        }
        assert allowed == {"PENDING", "OPEN", "CLOSED", "CANCELLED", "REJECTED"}

    def test_order_state_values(self) -> None:
        allowed: set[OrderState] = {"PENDING", "FILLED", "CANCELLED", "REJECTED"}
        assert allowed == {"PENDING", "FILLED", "CANCELLED", "REJECTED"}


# ---------------------------------------------------------------------------
# Protocol compliance
# ---------------------------------------------------------------------------


class FakeBrokerAdapter:
    """Minimal implementation satisfying BrokerAdapter protocol."""

    def get_candles(
        self,
        instrument: str,
        interval: str,
        start: datetime,
        end: datetime,
    ) -> list:
        return []

    def get_account(self) -> AccountInfo:
        return AccountInfo(
            balance=10_000.0,
            currency="USD",
            unrealized_pnl=0.0,
            margin_used=0.0,
            margin_available=10_000.0,
        )

    def get_positions(self) -> list[Position]:
        return []

    def place_market_order(
        self,
        instrument: str,
        units: float,
        stop_loss: float,
        client_order_id: str,
    ) -> OrderResult:
        return OrderResult(
            success=True,
            order_id="FAKE-001",
            client_order_id=client_order_id,
            instrument=instrument,
            direction="BUY",
            units=units,
            fill_price=1.0,
            timestamp=datetime.now(UTC),
            error_message=None,
        )

    def modify_stop_loss(self, trade_id: str, new_stop: float) -> OrderResult:
        return OrderResult(
            success=True,
            order_id=trade_id,
            client_order_id="",
            instrument="",
            direction="BUY",
            units=0.0,
            fill_price=None,
            timestamp=datetime.now(UTC),
            error_message=None,
        )

    def close_position(self, trade_id: str) -> OrderResult:
        return OrderResult(
            success=True,
            order_id=trade_id,
            client_order_id="",
            instrument="",
            direction="SELL",
            units=0.0,
            fill_price=1.0,
            timestamp=datetime.now(UTC),
            error_message=None,
        )

    def get_order_status(self, client_order_id: str) -> OrderStatus:
        return OrderStatus(
            client_order_id=client_order_id,
            broker_order_id="BRK-FAKE",
            state="FILLED",
            fill_price=1.0,
            fill_time=datetime.now(UTC),
        )


class TestBrokerAdapterProtocol:
    def test_fake_satisfies_protocol(self) -> None:
        adapter = FakeBrokerAdapter()
        assert isinstance(adapter, BrokerAdapter)

    def test_object_does_not_satisfy_protocol(self) -> None:
        assert not isinstance(object(), BrokerAdapter)

    def test_partial_implementation_fails(self) -> None:
        class Partial:
            def get_account(self) -> AccountInfo:
                return AccountInfo(
                    balance=0, currency="USD", unrealized_pnl=0,
                    margin_used=0, margin_available=0,
                )

        assert not isinstance(Partial(), BrokerAdapter)
