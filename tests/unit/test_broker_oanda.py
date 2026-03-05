"""Tests for Oanda broker adapter (T-502)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

import pytest

from src.trading.broker_base import (
    AccountInfo,
    BrokerAdapter,
    OrderResult,
    OrderStatus,
    Position,
)
from src.trading.broker_oanda import (
    OandaAdapter,
    _retry_request,
)


# ---------------------------------------------------------------------------
# Fake HTTP client
# ---------------------------------------------------------------------------

ACCOUNT_SUMMARY_RESPONSE: dict[str, Any] = {
    "account": {
        "balance": "10000.0000",
        "currency": "USD",
        "unrealizedPL": "150.5000",
        "marginUsed": "500.0000",
        "marginAvailable": "9500.0000",
    }
}

OPEN_POSITIONS_RESPONSE: dict[str, Any] = {
    "positions": [
        {
            "instrument": "EUR_USD",
            "long": {
                "units": "1000",
                "averagePrice": "1.10500",
                "unrealizedPL": "25.0000",
                "tradeIDs": ["T-100"],
            },
            "short": {"units": "0"},
        }
    ]
}

OPEN_TRADES_RESPONSE: dict[str, Any] = {
    "trades": [
        {
            "id": "T-100",
            "instrument": "EUR_USD",
            "currentUnits": "1000",
            "price": "1.10500",
            "unrealizedPL": "25.0000",
            "stopLossOrder": {"price": "1.10000"},
        }
    ]
}

ORDER_FILL_RESPONSE: dict[str, Any] = {
    "orderCreateTransaction": {
        "id": "TXN-001",
        "type": "MARKET_ORDER",
        "instrument": "EUR_USD",
        "units": "1000",
        "clientExtensions": {"id": "NEWTON-EUR_USD-1234567890"},
    },
    "orderFillTransaction": {
        "id": "TXN-002",
        "type": "ORDER_FILL",
        "instrument": "EUR_USD",
        "units": "1000",
        "price": "1.10500",
        "time": "2026-03-04T12:00:00.000000000Z",
        "tradeOpened": {"tradeID": "T-100"},
    },
}

ORDER_REJECT_RESPONSE: dict[str, Any] = {
    "orderRejectTransaction": {
        "id": "TXN-003",
        "type": "MARKET_ORDER_REJECT",
        "rejectReason": "INSUFFICIENT_MARGIN",
    }
}

TRADE_CLOSE_RESPONSE: dict[str, Any] = {
    "orderCreateTransaction": {"id": "TXN-010", "type": "MARKET_ORDER"},
    "orderFillTransaction": {
        "id": "TXN-011",
        "type": "ORDER_FILL",
        "instrument": "EUR_USD",
        "units": "-1000",
        "price": "1.10600",
        "time": "2026-03-04T13:00:00.000000000Z",
        "tradesClosed": [{"tradeID": "T-100"}],
    },
}

STOP_LOSS_REPLACE_RESPONSE: dict[str, Any] = {
    "stopLossOrderTransaction": {
        "id": "TXN-020",
        "type": "STOP_LOSS_ORDER",
        "tradeID": "T-100",
        "price": "1.09500",
        "time": "2026-03-04T14:00:00.000000000Z",
    }
}

ORDER_STATUS_FILLED: dict[str, Any] = {
    "order": {
        "id": "ORD-001",
        "clientExtensions": {"id": "NEWTON-EUR_USD-1234567890"},
        "state": "FILLED",
        "fillingTransaction": {
            "price": "1.10500",
            "time": "2026-03-04T12:00:00.000000000Z",
        },
    }
}

ORDER_STATUS_PENDING: dict[str, Any] = {
    "order": {
        "id": "ORD-002",
        "clientExtensions": {"id": "NEWTON-EUR_USD-9999999999"},
        "state": "PENDING",
    }
}

CANDLES_RESPONSE: dict[str, Any] = {
    "candles": [
        {
            "complete": True,
            "time": "2026-03-04T12:00:00.000000000Z",
            "mid": {"o": "1.1050", "h": "1.1060", "l": "1.1040", "c": "1.1055"},
            "volume": 1000,
        }
    ]
}


class FakeOandaTradingClient:
    """Fake HTTP client returning canned Oanda v20 responses."""

    def __init__(self) -> None:
        self.last_method: str = ""
        self.last_path: str = ""
        self.last_params: dict[str, str] = {}
        self.last_body: dict[str, Any] | None = None
        self._responses: dict[str, dict[str, Any]] = {}

    def set_response(self, key: str, response: dict[str, Any]) -> None:
        self._responses[key] = response

    def get_json(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        self.last_method = "GET"
        self.last_path = path
        self.last_params = params
        for key, resp in self._responses.items():
            if key in path:
                return resp
        return {}

    def post_json(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        self.last_method = "POST"
        self.last_path = path
        self.last_body = body
        for key, resp in self._responses.items():
            if key in path:
                return resp
        return {}

    def put_json(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        self.last_method = "PUT"
        self.last_path = path
        self.last_body = body
        for key, resp in self._responses.items():
            if key in path:
                return resp
        return {}


def _make_adapter(client: FakeOandaTradingClient | None = None) -> OandaAdapter:
    c = client or FakeOandaTradingClient()
    return OandaAdapter(account_id="101-001-123", api_key="test-key", http_client=c)


# ---------------------------------------------------------------------------
# Protocol compliance
# ---------------------------------------------------------------------------


class TestProtocolCompliance:
    def test_satisfies_broker_adapter(self) -> None:
        adapter = _make_adapter()
        assert isinstance(adapter, BrokerAdapter)


# ---------------------------------------------------------------------------
# get_account
# ---------------------------------------------------------------------------


class TestGetAccount:
    def test_parses_account_summary(self) -> None:
        client = FakeOandaTradingClient()
        client.set_response("summary", ACCOUNT_SUMMARY_RESPONSE)
        adapter = _make_adapter(client)
        info = adapter.get_account()
        assert isinstance(info, AccountInfo)
        assert info.balance == 10_000.0
        assert info.currency == "USD"
        assert info.unrealized_pnl == 150.5
        assert info.margin_used == 500.0
        assert info.margin_available == 9_500.0

    def test_calls_correct_endpoint(self) -> None:
        client = FakeOandaTradingClient()
        client.set_response("summary", ACCOUNT_SUMMARY_RESPONSE)
        adapter = _make_adapter(client)
        adapter.get_account()
        assert "101-001-123" in client.last_path
        assert "summary" in client.last_path


# ---------------------------------------------------------------------------
# get_positions
# ---------------------------------------------------------------------------


class TestGetPositions:
    def test_parses_open_trades(self) -> None:
        client = FakeOandaTradingClient()
        client.set_response("openTrades", OPEN_TRADES_RESPONSE)
        adapter = _make_adapter(client)
        positions = adapter.get_positions()
        assert len(positions) == 1
        pos = positions[0]
        assert isinstance(pos, Position)
        assert pos.instrument == "EUR_USD"
        assert pos.direction == "BUY"
        assert pos.units == 1000.0
        assert pos.entry_price == 1.105
        assert pos.unrealized_pnl == 25.0
        assert pos.stop_loss == 1.1
        assert pos.trade_id == "T-100"

    def test_empty_positions(self) -> None:
        client = FakeOandaTradingClient()
        client.set_response("openTrades", {"trades": []})
        adapter = _make_adapter(client)
        positions = adapter.get_positions()
        assert positions == []

    def test_short_position(self) -> None:
        client = FakeOandaTradingClient()
        client.set_response("openTrades", {
            "trades": [{
                "id": "T-200",
                "instrument": "EUR_USD",
                "currentUnits": "-500",
                "price": "1.11000",
                "unrealizedPL": "-10.0000",
                "stopLossOrder": {"price": "1.12000"},
            }]
        })
        adapter = _make_adapter(client)
        positions = adapter.get_positions()
        assert len(positions) == 1
        assert positions[0].direction == "SELL"
        assert positions[0].units == 500.0

    def test_no_stop_loss(self) -> None:
        client = FakeOandaTradingClient()
        client.set_response("openTrades", {
            "trades": [{
                "id": "T-300",
                "instrument": "EUR_USD",
                "currentUnits": "100",
                "price": "1.10000",
                "unrealizedPL": "0.0",
            }]
        })
        adapter = _make_adapter(client)
        positions = adapter.get_positions()
        assert positions[0].stop_loss is None


# ---------------------------------------------------------------------------
# place_market_order
# ---------------------------------------------------------------------------


class TestPlaceMarketOrder:
    def test_successful_order(self) -> None:
        client = FakeOandaTradingClient()
        client.set_response("orders", ORDER_FILL_RESPONSE)
        adapter = _make_adapter(client)
        result = adapter.place_market_order(
            instrument="EUR_USD",
            units=1000.0,
            stop_loss=1.1000,
            client_order_id="NEWTON-EUR_USD-1234567890",
        )
        assert isinstance(result, OrderResult)
        assert result.success is True
        assert result.order_id == "T-100"
        assert result.fill_price == 1.105
        assert result.instrument == "EUR_USD"
        assert result.direction == "BUY"
        assert result.units == 1000.0
        assert result.error_message is None

    def test_order_payload_has_stop_loss_on_fill(self) -> None:
        client = FakeOandaTradingClient()
        client.set_response("orders", ORDER_FILL_RESPONSE)
        adapter = _make_adapter(client)
        adapter.place_market_order(
            instrument="EUR_USD",
            units=1000.0,
            stop_loss=1.1000,
            client_order_id="NEWTON-EUR_USD-1234567890",
        )
        body = client.last_body
        assert body is not None
        order = body["order"]
        assert order["type"] == "MARKET"
        assert order["instrument"] == "EUR_USD"
        assert order["units"] == "1000"
        assert order["stopLossOnFill"]["price"] == "1.1000"
        assert order["clientExtensions"]["id"] == "NEWTON-EUR_USD-1234567890"

    def test_sell_order_negative_units(self) -> None:
        client = FakeOandaTradingClient()
        sell_response = {
            "orderCreateTransaction": {
                "id": "TXN-005",
                "type": "MARKET_ORDER",
                "instrument": "EUR_USD",
                "units": "-500",
                "clientExtensions": {"id": "NEWTON-EUR_USD-9999"},
            },
            "orderFillTransaction": {
                "id": "TXN-006",
                "type": "ORDER_FILL",
                "instrument": "EUR_USD",
                "units": "-500",
                "price": "1.10400",
                "time": "2026-03-04T12:00:00.000000000Z",
                "tradeOpened": {"tradeID": "T-200"},
            },
        }
        client.set_response("orders", sell_response)
        adapter = _make_adapter(client)
        result = adapter.place_market_order(
            instrument="EUR_USD",
            units=-500.0,
            stop_loss=1.1100,
            client_order_id="NEWTON-EUR_USD-9999",
        )
        assert result.success is True
        assert result.direction == "SELL"
        assert result.units == 500.0

    def test_rejected_order(self) -> None:
        client = FakeOandaTradingClient()
        client.set_response("orders", ORDER_REJECT_RESPONSE)
        adapter = _make_adapter(client)
        result = adapter.place_market_order(
            instrument="EUR_USD",
            units=1000.0,
            stop_loss=1.1000,
            client_order_id="NEWTON-EUR_USD-1234567890",
        )
        assert result.success is False
        assert result.fill_price is None
        assert result.error_message == "INSUFFICIENT_MARGIN"


# ---------------------------------------------------------------------------
# modify_stop_loss
# ---------------------------------------------------------------------------


class TestModifyStopLoss:
    def test_successful_modification(self) -> None:
        client = FakeOandaTradingClient()
        client.set_response("orders", STOP_LOSS_REPLACE_RESPONSE)
        adapter = _make_adapter(client)
        result = adapter.modify_stop_loss("T-100", 1.095)
        assert isinstance(result, OrderResult)
        assert result.success is True

    def test_sends_correct_payload(self) -> None:
        client = FakeOandaTradingClient()
        client.set_response("orders", STOP_LOSS_REPLACE_RESPONSE)
        adapter = _make_adapter(client)
        adapter.modify_stop_loss("T-100", 1.095)
        assert client.last_method == "PUT"
        assert "T-100" in client.last_path
        body = client.last_body
        assert body is not None
        assert body["stopLoss"]["price"] == "1.0950"


# ---------------------------------------------------------------------------
# close_position
# ---------------------------------------------------------------------------


class TestClosePosition:
    def test_successful_close(self) -> None:
        client = FakeOandaTradingClient()
        client.set_response("close", TRADE_CLOSE_RESPONSE)
        adapter = _make_adapter(client)
        result = adapter.close_position("T-100")
        assert isinstance(result, OrderResult)
        assert result.success is True
        assert result.fill_price == 1.106

    def test_sends_close_all_units(self) -> None:
        client = FakeOandaTradingClient()
        client.set_response("close", TRADE_CLOSE_RESPONSE)
        adapter = _make_adapter(client)
        adapter.close_position("T-100")
        assert client.last_method == "PUT"
        assert "close" in client.last_path
        body = client.last_body
        assert body is not None
        assert body["units"] == "ALL"


# ---------------------------------------------------------------------------
# get_order_status
# ---------------------------------------------------------------------------


class TestGetOrderStatus:
    def test_filled_order(self) -> None:
        client = FakeOandaTradingClient()
        client.set_response("orders", ORDER_STATUS_FILLED)
        adapter = _make_adapter(client)
        status = adapter.get_order_status("NEWTON-EUR_USD-1234567890")
        assert isinstance(status, OrderStatus)
        assert status.client_order_id == "NEWTON-EUR_USD-1234567890"
        assert status.broker_order_id == "ORD-001"
        assert status.state == "FILLED"
        assert status.fill_price == 1.105

    def test_pending_order(self) -> None:
        client = FakeOandaTradingClient()
        client.set_response("orders", ORDER_STATUS_PENDING)
        adapter = _make_adapter(client)
        status = adapter.get_order_status("NEWTON-EUR_USD-9999999999")
        assert status.state == "PENDING"
        assert status.fill_price is None
        assert status.fill_time is None


# ---------------------------------------------------------------------------
# get_candles
# ---------------------------------------------------------------------------


class TestGetCandles:
    def test_returns_candle_records(self) -> None:
        client = FakeOandaTradingClient()
        client.set_response("candles", CANDLES_RESPONSE)
        adapter = _make_adapter(client)
        candles = adapter.get_candles(
            instrument="EUR_USD",
            interval="1h",
            start=datetime(2026, 3, 4, tzinfo=UTC),
            end=datetime(2026, 3, 5, tzinfo=UTC),
        )
        assert len(candles) == 1
        assert candles[0].instrument == "EUR_USD"
        assert candles[0].open == 1.105


# ---------------------------------------------------------------------------
# Retry logic
# ---------------------------------------------------------------------------


class TestRetryLogic:
    def test_retries_on_5xx(self) -> None:
        call_count = 0

        def flaky_fn() -> dict[str, Any]:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise _make_http_error(500)
            return {"ok": True}

        result = _retry_request(flaky_fn, backoffs=(0.0, 0.0, 0.0))
        assert result == {"ok": True}
        assert call_count == 3

    def test_no_retry_on_4xx(self) -> None:
        call_count = 0

        def bad_request_fn() -> dict[str, Any]:
            nonlocal call_count
            call_count += 1
            raise _make_http_error(400)

        with pytest.raises(Exception):
            _retry_request(bad_request_fn, backoffs=(0.0, 0.0, 0.0))
        assert call_count == 1

    def test_raises_after_max_retries(self) -> None:
        def always_fail() -> dict[str, Any]:
            raise _make_http_error(503)

        with pytest.raises(Exception):
            _retry_request(always_fail, backoffs=(0.0, 0.0, 0.0))

    def test_retries_on_timeout(self) -> None:
        call_count = 0

        def timeout_then_ok() -> dict[str, Any]:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise TimeoutError("connection timed out")
            return {"ok": True}

        result = _retry_request(timeout_then_ok, backoffs=(0.0, 0.0, 0.0))
        assert result == {"ok": True}
        assert call_count == 2

    def test_logs_retry_attempts(self, caplog: pytest.LogCaptureFixture) -> None:
        call_count = 0

        def fail_once() -> dict[str, Any]:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise _make_http_error(500)
            return {"ok": True}

        with caplog.at_level(logging.WARNING, logger="src.trading.broker_oanda"):
            _retry_request(fail_once, backoffs=(0.0, 0.0, 0.0))
        assert any("Retry" in r.message for r in caplog.records)


def _make_http_error(code: int) -> Exception:
    """Create an HTTPError-like exception with a .code attribute."""
    from urllib.error import HTTPError
    from io import BytesIO

    return HTTPError(
        url="https://api-fxpractice.oanda.com/v3/test",
        code=code,
        msg=f"HTTP {code}",
        hdrs=MagicMock(),  # type: ignore[arg-type]
        fp=BytesIO(b"error"),
    )
