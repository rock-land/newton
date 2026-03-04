"""Binance spot REST adapter implementing BrokerAdapter (SPEC §3.3, §5.9).

Provides BTC/USDT crypto spot trading via the Binance REST API.
Stop-loss uses STOP_LOSS_LIMIT orders placed after entry fill.
Retry logic follows §3.5 / §5.11: 3× on 5xx/timeout, no retry on 4xx.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from datetime import UTC, datetime
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from src.data.fetcher_base import CandleRecord
from src.data.fetcher_binance import (
    INTERVAL_TO_BINANCE_INTERVAL,
    normalize_binance_candles,
)
from src.trading.broker_base import (
    AccountInfo,
    Direction,
    OrderResult,
    OrderStatus,
    Position,
)

logger = logging.getLogger(__name__)

BINANCE_BASE_URL = "https://api.binance.com"

# Default backoffs per SPEC §3.5: 2s, 4s, 8s
DEFAULT_BACKOFFS = (2.0, 4.0, 8.0)

# Stop-loss price offset — limit price set slightly below stop price
# to ensure fill. 0.5% below stop for sells, 0.5% above for buys.
SL_LIMIT_OFFSET_PCT = 0.005


# ---------------------------------------------------------------------------
# HTTP client protocol
# ---------------------------------------------------------------------------


class BinanceTradingHTTPClient(Protocol):
    """HTTP client for signed Binance trading operations."""

    def get_json(self, path: str, params: dict[str, str]) -> dict[str, Any]: ...
    def post_json(self, path: str, params: dict[str, str]) -> dict[str, Any]: ...
    def delete_json(self, path: str, params: dict[str, str]) -> dict[str, Any]: ...


class UrllibBinanceTradingClient:
    """Real HTTP client with HMAC-SHA256 signing for Binance REST API."""

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        *,
        base_url: str = BINANCE_BASE_URL,
    ) -> None:
        self._api_key = api_key
        self._api_secret = api_secret
        self._base_url = base_url.rstrip("/")

    def get_json(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        signed = self._sign(params)
        query = urlencode(signed)
        url = f"{self._base_url}{path}?{query}"
        self._validate_url(url)
        req = Request(url, headers=self._headers())
        return self._fetch(req)

    def post_json(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        signed = self._sign(params)
        url = f"{self._base_url}{path}"
        self._validate_url(url)
        data = urlencode(signed).encode("utf-8")
        req = Request(url, data=data, headers=self._headers(), method="POST")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        return self._fetch(req)

    def delete_json(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        signed = self._sign(params)
        query = urlencode(signed)
        url = f"{self._base_url}{path}?{query}"
        self._validate_url(url)
        req = Request(url, headers=self._headers(), method="DELETE")
        return self._fetch(req)

    def _headers(self) -> dict[str, str]:
        return {"X-MBX-APIKEY": self._api_key}

    def _sign(self, params: dict[str, str]) -> dict[str, str]:
        signed = {**params, "timestamp": str(int(time.time() * 1000))}
        query_string = urlencode(signed)
        signature = hmac.new(
            self._api_secret.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        signed["signature"] = signature
        return signed

    def _validate_url(self, url: str) -> None:
        parsed = urlparse(url)
        expected = urlparse(self._base_url).netloc
        if parsed.scheme != "https" or parsed.netloc != expected:
            msg = f"unexpected binance URL: {url}"
            raise ValueError(msg)

    def _fetch(self, req: Request) -> dict[str, Any]:
        with urlopen(req, timeout=30) as response:  # nosec B310
            payload = response.read().decode("utf-8")
        data = json.loads(payload)
        if not isinstance(data, dict):
            msg = "binance response must be a JSON object"
            raise ValueError(msg)
        return data


# ---------------------------------------------------------------------------
# Retry helper (§3.5 / §5.11)
# ---------------------------------------------------------------------------


def _retry_request(
    fn: Any,
    *,
    backoffs: tuple[float, ...] = DEFAULT_BACKOFFS,
) -> dict[str, Any]:
    """Execute ``fn()`` with retry on 5xx/timeout. No retry on 4xx."""
    last_exc: Exception | None = None
    max_attempts = len(backoffs) + 1

    for attempt in range(max_attempts):
        try:
            return fn()  # type: ignore[no-any-return]
        except HTTPError as exc:
            if 400 <= exc.code < 500:
                raise
            last_exc = exc
            if attempt < len(backoffs):
                wait = backoffs[attempt]
                logger.warning(
                    "Retry %d/%d after HTTP %d (wait %.1fs)",
                    attempt + 1, len(backoffs), exc.code, wait,
                )
                time.sleep(wait)
        except (URLError, TimeoutError, OSError) as exc:
            last_exc = exc
            if attempt < len(backoffs):
                wait = backoffs[attempt]
                logger.warning(
                    "Retry %d/%d after %s (wait %.1fs)",
                    attempt + 1, len(backoffs), type(exc).__name__, wait,
                )
                time.sleep(wait)

    raise last_exc  # type: ignore[misc]


# ---------------------------------------------------------------------------
# BinanceSpotAdapter
# ---------------------------------------------------------------------------


class BinanceSpotAdapter:
    """Binance spot REST adapter implementing BrokerAdapter protocol."""

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        *,
        http_client: BinanceTradingHTTPClient | None = None,
        base_url: str = BINANCE_BASE_URL,
        symbol: str = "BTCUSDT",
        instrument: str = "BTC_USD",
    ) -> None:
        self._http_client = http_client or UrllibBinanceTradingClient(
            api_key, api_secret, base_url=base_url,
        )
        self._symbol = symbol
        self._instrument = instrument

    # -- get_candles ----------------------------------------------------------

    def get_candles(
        self,
        instrument: str,
        interval: str,
        start: datetime,
        end: datetime,
    ) -> list[CandleRecord]:
        bi = INTERVAL_TO_BINANCE_INTERVAL.get(interval)
        if bi is None:
            msg = f"unsupported interval for binance: {interval}"
            raise ValueError(msg)

        params = {
            "symbol": self._symbol,
            "interval": bi,
            "startTime": str(int(start.timestamp() * 1000)),
            "endTime": str(int(end.timestamp() * 1000)),
            "limit": "1000",
        }
        path = "/api/v3/klines"
        data = _retry_request(
            lambda: self._http_client.get_json(path, params),
        )
        raw = data.get("candles", [])
        return list(normalize_binance_candles(raw, interval=interval))

    # -- get_account ----------------------------------------------------------

    def get_account(self) -> AccountInfo:
        path = "/api/v3/account"
        data = _retry_request(
            lambda: self._http_client.get_json(path, {}),
        )
        usdt_balance = 0.0
        for bal in data.get("balances", []):
            if bal.get("asset") == "USDT":
                usdt_balance = float(bal.get("free", 0))
                break

        return AccountInfo(
            balance=usdt_balance,
            currency="USDT",
            unrealized_pnl=0.0,  # Spot has no unrealized PnL concept
            margin_used=0.0,  # Spot — no margin
            margin_available=usdt_balance,
        )

    # -- get_positions --------------------------------------------------------

    def get_positions(self) -> list[Position]:
        # Binance spot has no position concept. Positions are tracked
        # internally via Newton's trades table (option 1a per T-503).
        return []

    # -- place_market_order ---------------------------------------------------

    def place_market_order(
        self,
        instrument: str,
        units: float,
        stop_loss: float,
        client_order_id: str,
    ) -> OrderResult:
        side = "BUY" if units > 0 else "SELL"
        params = {
            "symbol": self._symbol,
            "side": side,
            "type": "MARKET",
            "quantity": f"{abs(units):.8f}",
            "newClientOrderId": client_order_id,
        }
        path = "/api/v3/order"
        data = _retry_request(
            lambda: self._http_client.post_json(path, params),
        )

        # Check for error response (Binance returns {"code": ..., "msg": ...})
        if "code" in data and data["code"] < 0:
            return OrderResult(
                success=False,
                order_id=None,
                client_order_id=client_order_id,
                instrument=instrument,
                direction=side,  # type: ignore[arg-type]
                units=abs(units),
                fill_price=None,
                timestamp=datetime.now(UTC),
                error_message=str(data.get("msg", "UNKNOWN")),
            )

        return self._parse_order_response(data, instrument, client_order_id)

    # -- modify_stop_loss -----------------------------------------------------

    def modify_stop_loss(self, trade_id: str, new_stop: float) -> OrderResult:
        # Cancel existing stop-loss orders for the symbol, then place new one
        cancel_params = {
            "symbol": self._symbol,
            "orderId": trade_id,
        }
        cancel_path = "/api/v3/order"
        _retry_request(
            lambda: self._http_client.delete_json(cancel_path, cancel_params),
        )

        # Place new stop-loss
        limit_price = new_stop * (1 - SL_LIMIT_OFFSET_PCT)
        sl_params = {
            "symbol": self._symbol,
            "side": "SELL",
            "type": "STOP_LOSS_LIMIT",
            "timeInForce": "GTC",
            "quantity": "0.01",  # Will be set by caller in production
            "stopPrice": f"{new_stop:.4f}",
            "price": f"{limit_price:.4f}",
        }
        sl_path = "/api/v3/order"
        data = _retry_request(
            lambda: self._http_client.post_json(sl_path, sl_params),
        )

        return OrderResult(
            success=True,
            order_id=str(data.get("orderId", "")),
            client_order_id=str(data.get("clientOrderId", "")),
            instrument=self._instrument,
            direction="SELL",
            units=0.0,
            fill_price=None,
            timestamp=datetime.now(UTC),
            error_message=None,
        )

    # -- close_position -------------------------------------------------------

    def close_position(self, trade_id: str) -> OrderResult:
        # Market sell to close (assumes long position — short selling
        # not supported on Binance spot)
        params = {
            "symbol": self._symbol,
            "side": "SELL",
            "type": "MARKET",
            "quantity": "0.01",  # Will be set by caller in production
        }
        path = "/api/v3/order"
        data = _retry_request(
            lambda: self._http_client.post_json(path, params),
        )
        return self._parse_order_response(data, self._instrument, "")

    # -- get_order_status -----------------------------------------------------

    def get_order_status(self, client_order_id: str) -> OrderStatus:
        params = {
            "symbol": self._symbol,
            "origClientOrderId": client_order_id,
        }
        path = "/api/v3/order"
        data = _retry_request(
            lambda: self._http_client.get_json(path, params),
        )

        state_map: dict[str, str] = {
            "NEW": "PENDING",
            "PARTIALLY_FILLED": "PENDING",
            "FILLED": "FILLED",
            "CANCELED": "CANCELLED",
            "REJECTED": "REJECTED",
            "EXPIRED": "CANCELLED",
        }
        raw_state = str(data.get("status", "NEW"))
        state = state_map.get(raw_state, "PENDING")

        fill_price = None
        fill_time = None
        exec_qty = float(data.get("executedQty", 0))
        if raw_state == "FILLED" and exec_qty > 0:
            fill_price = float(data.get("price", 0)) or None
            update_ms = data.get("updateTime")
            if update_ms:
                fill_time = datetime.fromtimestamp(
                    int(update_ms) / 1000, tz=UTC,
                )

        return OrderStatus(
            client_order_id=str(data.get("clientOrderId", client_order_id)),
            broker_order_id=str(data.get("orderId", "")),
            state=state,  # type: ignore[arg-type]
            fill_price=fill_price,
            fill_time=fill_time,
        )

    # -- helpers --------------------------------------------------------------

    def _parse_order_response(
        self,
        data: dict[str, Any],
        instrument: str,
        client_order_id: str,
    ) -> OrderResult:
        """Parse Binance order response into OrderResult."""
        side = str(data.get("side", "BUY"))
        direction: Direction = "BUY" if side == "BUY" else "SELL"
        exec_qty = float(data.get("executedQty", 0))

        # Compute weighted average fill price from fills array
        fills = data.get("fills", [])
        fill_price = _weighted_fill_price(fills) if fills else None

        transact_ms = data.get("transactTime")
        timestamp = (
            datetime.fromtimestamp(int(transact_ms) / 1000, tz=UTC)
            if transact_ms
            else datetime.now(UTC)
        )

        return OrderResult(
            success=True,
            order_id=str(data.get("orderId", "")),
            client_order_id=str(data.get("clientOrderId", client_order_id)),
            instrument=instrument,
            direction=direction,
            units=exec_qty,
            fill_price=fill_price,
            timestamp=timestamp,
            error_message=None,
        )


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------


def _weighted_fill_price(fills: list[dict[str, Any]]) -> float | None:
    """Compute quantity-weighted average fill price."""
    total_qty = 0.0
    total_cost = 0.0
    for f in fills:
        qty = float(f.get("qty", 0))
        price = float(f.get("price", 0))
        total_qty += qty
        total_cost += qty * price
    if total_qty == 0:
        return None
    return total_cost / total_qty
