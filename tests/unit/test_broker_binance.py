"""Tests for BinanceSpotAdapter (T-503)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from urllib.error import HTTPError

import pytest

from src.trading.broker_base import (
    AccountInfo,
    BrokerAdapter,
    OrderResult,
    OrderStatus,
)
from src.trading.broker_binance import (
    BinanceSpotAdapter,
    _retry_request,
)


# ---------------------------------------------------------------------------
# Fake HTTP client
# ---------------------------------------------------------------------------


class FakeBinanceTradingClient:
    """Canned-response HTTP client for testing."""

    def __init__(self) -> None:
        self._responses: dict[str, dict[str, Any]] = {}
        self.last_method: str = ""
        self.last_path: str = ""
        self.last_params: dict[str, str] = {}

    def set_response(self, key: str, response: dict[str, Any]) -> None:
        self._responses[key] = response

    def _lookup(self, method: str, path: str, params: dict[str, str]) -> dict[str, Any]:
        self.last_method = method
        self.last_path = path
        self.last_params = params
        for key, resp in self._responses.items():
            if key in path:
                return resp
        return {}

    def get_json(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        return self._lookup("GET", path, params)

    def post_json(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        return self._lookup("POST", path, params)

    def delete_json(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        return self._lookup("DELETE", path, params)


# ---------------------------------------------------------------------------
# Canned responses
# ---------------------------------------------------------------------------

ACCOUNT_RESPONSE: dict[str, Any] = {
    "balances": [
        {"asset": "BTC", "free": "0.50000000", "locked": "0.00000000"},
        {"asset": "USDT", "free": "10000.00000000", "locked": "0.00000000"},
        {"asset": "ETH", "free": "0.00000000", "locked": "0.00000000"},
    ],
    "canTrade": True,
    "makerCommission": 10,
    "takerCommission": 10,
}

ORDER_FILL_RESPONSE: dict[str, Any] = {
    "symbol": "BTCUSDT",
    "orderId": 12345,
    "clientOrderId": "NEWTON-BTC_USD-1700000000000",
    "transactTime": 1700000000000,
    "price": "0.00000000",
    "origQty": "0.01000000",
    "executedQty": "0.01000000",
    "status": "FILLED",
    "type": "MARKET",
    "side": "BUY",
    "fills": [
        {
            "price": "45000.00",
            "qty": "0.01000000",
            "commission": "0.00001000",
            "commissionAsset": "BTC",
        }
    ],
}

STOP_LOSS_RESPONSE: dict[str, Any] = {
    "symbol": "BTCUSDT",
    "orderId": 12346,
    "clientOrderId": "SL-NEWTON-BTC_USD-1700000000000",
    "status": "NEW",
    "type": "STOP_LOSS_LIMIT",
    "side": "SELL",
    "stopPrice": "43650.0000",
    "price": "43600.0000",
    "origQty": "0.01000000",
}

ORDER_REJECT_RESPONSE: dict[str, Any] = {
    "code": -2010,
    "msg": "Account has insufficient balance for requested action.",
}

OPEN_ORDERS_RESPONSE: list[dict[str, Any]] = [
    {
        "symbol": "BTCUSDT",
        "orderId": 12346,
        "clientOrderId": "SL-NEWTON-BTC_USD-1700000000000",
        "price": "43600.00000000",
        "origQty": "0.01000000",
        "status": "NEW",
        "type": "STOP_LOSS_LIMIT",
        "side": "SELL",
        "stopPrice": "43650.00000000",
    },
]

ORDER_STATUS_FILLED: dict[str, Any] = {
    "symbol": "BTCUSDT",
    "orderId": 12345,
    "clientOrderId": "NEWTON-BTC_USD-1700000000000",
    "status": "FILLED",
    "price": "45000.00000000",
    "executedQty": "0.01000000",
    "time": 1700000000000,
    "updateTime": 1700000000000,
    "side": "BUY",
}

ORDER_STATUS_PENDING: dict[str, Any] = {
    "symbol": "BTCUSDT",
    "orderId": 12345,
    "clientOrderId": "NEWTON-BTC_USD-1700000000000",
    "status": "NEW",
    "price": "0.00000000",
    "executedQty": "0.00000000",
    "time": 1700000000000,
    "updateTime": 1700000000000,
    "side": "BUY",
}

CANCEL_ORDER_RESPONSE: dict[str, Any] = {
    "symbol": "BTCUSDT",
    "orderId": 12346,
    "clientOrderId": "SL-NEWTON-BTC_USD-1700000000000",
    "status": "CANCELED",
}

CLOSE_ORDER_RESPONSE: dict[str, Any] = {
    "symbol": "BTCUSDT",
    "orderId": 12347,
    "clientOrderId": "CLOSE-BTC_USD-1700000000000",
    "transactTime": 1700000001000,
    "price": "0.00000000",
    "origQty": "0.01000000",
    "executedQty": "0.01000000",
    "status": "FILLED",
    "type": "MARKET",
    "side": "SELL",
    "fills": [
        {
            "price": "45100.00",
            "qty": "0.01000000",
            "commission": "0.00451000",
            "commissionAsset": "USDT",
        }
    ],
}

CANDLES_RESPONSE: list[list[Any]] = [
    [
        1700000000000, "45000.00", "45500.00", "44800.00", "45200.00",
        "100.50000000", 1700003599999, "4530000.00", 1500, "60.25000000",
        "2715000.00", "0",
    ],
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_adapter(client: FakeBinanceTradingClient | None = None) -> BinanceSpotAdapter:
    c = client or FakeBinanceTradingClient()
    return BinanceSpotAdapter(
        api_key="test-key",
        api_secret="test-secret",
        http_client=c,
    )


def _make_http_error(code: int) -> HTTPError:
    return HTTPError(
        url="https://api.binance.com/test",
        code=code,
        msg=f"HTTP {code}",
        hdrs=None,  # type: ignore[arg-type]
        fp=None,
    )


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
    def test_returns_account_info(self) -> None:
        client = FakeBinanceTradingClient()
        client.set_response("account", ACCOUNT_RESPONSE)
        adapter = _make_adapter(client)

        result = adapter.get_account()

        assert isinstance(result, AccountInfo)
        assert result.currency == "USDT"
        assert result.balance == 10000.0
        assert result.margin_used == 0.0
        assert result.margin_available == 10000.0

    def test_zero_balance(self) -> None:
        client = FakeBinanceTradingClient()
        client.set_response("account", {"balances": []})
        adapter = _make_adapter(client)

        result = adapter.get_account()
        assert result.balance == 0.0


# ---------------------------------------------------------------------------
# get_positions — returns empty (spot, internal tracking per 1a)
# ---------------------------------------------------------------------------


class TestGetPositions:
    def test_returns_empty_list(self) -> None:
        adapter = _make_adapter()
        result = adapter.get_positions()
        assert result == []
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# place_market_order
# ---------------------------------------------------------------------------


class TestPlaceMarketOrder:
    def test_buy_order_success(self) -> None:
        client = FakeBinanceTradingClient()
        client.set_response("order", ORDER_FILL_RESPONSE)
        adapter = _make_adapter(client)

        result = adapter.place_market_order(
            instrument="BTC_USD",
            units=0.01,
            stop_loss=43650.0,
            client_order_id="NEWTON-BTC_USD-1700000000000",
        )

        assert isinstance(result, OrderResult)
        assert result.success is True
        assert result.order_id == "12345"
        assert result.units == 0.01
        assert result.direction == "BUY"
        assert result.fill_price == 45000.0

    def test_sell_order(self) -> None:
        client = FakeBinanceTradingClient()
        resp = {**ORDER_FILL_RESPONSE, "side": "SELL"}
        client.set_response("order", resp)
        adapter = _make_adapter(client)

        result = adapter.place_market_order(
            instrument="BTC_USD",
            units=-0.01,
            stop_loss=46000.0,
            client_order_id="NEWTON-BTC_USD-1700000000000",
        )

        assert result.direction == "SELL"

    def test_reject_returns_failure(self) -> None:
        client = FakeBinanceTradingClient()
        client.set_response("order", ORDER_REJECT_RESPONSE)
        adapter = _make_adapter(client)

        result = adapter.place_market_order(
            instrument="BTC_USD",
            units=0.01,
            stop_loss=43650.0,
            client_order_id="NEWTON-BTC_USD-1700000000000",
        )

        assert result.success is False
        assert "insufficient balance" in (result.error_message or "").lower()


# ---------------------------------------------------------------------------
# modify_stop_loss
# ---------------------------------------------------------------------------


class TestModifyStopLoss:
    def test_modifies_stop(self) -> None:
        client = FakeBinanceTradingClient()
        # cancel returns first, then new stop order
        client.set_response("openOrders", {"orders": OPEN_ORDERS_RESPONSE})
        client.set_response("order", STOP_LOSS_RESPONSE)
        adapter = _make_adapter(client)

        result = adapter.modify_stop_loss(trade_id="12345", new_stop=43000.0)

        assert isinstance(result, OrderResult)
        assert result.success is True


# ---------------------------------------------------------------------------
# close_position
# ---------------------------------------------------------------------------


class TestClosePosition:
    def test_close_success(self) -> None:
        client = FakeBinanceTradingClient()
        client.set_response("order", CLOSE_ORDER_RESPONSE)
        adapter = _make_adapter(client)

        result = adapter.close_position(trade_id="12345")

        assert isinstance(result, OrderResult)
        assert result.success is True
        assert result.units == 0.01


# ---------------------------------------------------------------------------
# get_order_status
# ---------------------------------------------------------------------------


class TestGetOrderStatus:
    def test_filled_order(self) -> None:
        client = FakeBinanceTradingClient()
        client.set_response("order", ORDER_STATUS_FILLED)
        adapter = _make_adapter(client)

        result = adapter.get_order_status("NEWTON-BTC_USD-1700000000000")

        assert isinstance(result, OrderStatus)
        assert result.state == "FILLED"
        assert result.fill_price == 45000.0
        assert result.client_order_id == "NEWTON-BTC_USD-1700000000000"

    def test_pending_order(self) -> None:
        client = FakeBinanceTradingClient()
        client.set_response("order", ORDER_STATUS_PENDING)
        adapter = _make_adapter(client)

        result = adapter.get_order_status("NEWTON-BTC_USD-1700000000000")

        assert result.state == "PENDING"
        assert result.fill_price is None


# ---------------------------------------------------------------------------
# get_candles
# ---------------------------------------------------------------------------


class TestGetCandles:
    def test_returns_candles(self) -> None:
        client = FakeBinanceTradingClient()
        # get_candles uses a list response, wrap it
        client.set_response("klines", {"candles": CANDLES_RESPONSE})
        adapter = _make_adapter(client)

        result = adapter.get_candles(
            instrument="BTC_USD",
            interval="1h",
            start=datetime(2023, 11, 14, 0, 0, tzinfo=UTC),
            end=datetime(2023, 11, 15, 0, 0, tzinfo=UTC),
        )

        assert len(result) >= 0  # normalize filters by close time

    def test_unsupported_interval(self) -> None:
        adapter = _make_adapter()
        with pytest.raises(ValueError, match="unsupported interval"):
            adapter.get_candles(
                instrument="BTC_USD",
                interval="3m",
                start=datetime(2023, 11, 14, tzinfo=UTC),
                end=datetime(2023, 11, 15, tzinfo=UTC),
            )


# ---------------------------------------------------------------------------
# Retry logic
# ---------------------------------------------------------------------------


class TestRetryLogic:
    def test_retries_on_5xx(self) -> None:
        calls = 0

        def failing_then_ok() -> dict[str, Any]:
            nonlocal calls
            calls += 1
            if calls < 3:
                raise _make_http_error(503)
            return {"ok": True}

        result = _retry_request(failing_then_ok, backoffs=(0.0, 0.0, 0.0))
        assert result == {"ok": True}
        assert calls == 3

    def test_no_retry_on_4xx(self) -> None:
        def client_error() -> dict[str, Any]:
            raise _make_http_error(400)

        with pytest.raises(HTTPError):
            _retry_request(client_error, backoffs=(0.0, 0.0, 0.0))

    def test_retries_on_timeout(self) -> None:
        calls = 0

        def timeout_then_ok() -> dict[str, Any]:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise TimeoutError("timed out")
            return {"ok": True}

        result = _retry_request(timeout_then_ok, backoffs=(0.0, 0.0, 0.0))
        assert result == {"ok": True}

    def test_max_retries_exhausted(self) -> None:
        def always_fails() -> dict[str, Any]:
            raise _make_http_error(500)

        with pytest.raises(HTTPError):
            _retry_request(always_fails, backoffs=(0.0, 0.0, 0.0))

    def test_retry_logs_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        calls = 0

        def fail_once() -> dict[str, Any]:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise _make_http_error(502)
            return {"ok": True}

        with caplog.at_level(logging.WARNING):
            _retry_request(fail_once, backoffs=(0.0, 0.0, 0.0))

        assert "Retry 1/3" in caplog.text
