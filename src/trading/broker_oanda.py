"""Oanda v20 REST adapter implementing BrokerAdapter (SPEC §3.3, §5.9).

Provides EUR/USD forex spot trading via the Oanda v20 REST API.
Retry logic follows §3.5 / §5.11: 3× on 5xx/timeout, no retry on 4xx.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import UTC, datetime
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from src.data.fetcher_base import CandleRecord, INTERVAL_TO_OANDA_GRANULARITY
from src.data.fetcher_oanda import normalize_oanda_candles
from src.trading.broker_base import (
    AccountInfo,
    Direction,
    OrderResult,
    OrderStatus,
    Position,
)

logger = logging.getLogger(__name__)

OANDA_BASE_URL = "https://api-fxpractice.oanda.com"

# Default backoffs per SPEC §3.5: 2s, 4s, 8s
DEFAULT_BACKOFFS = (2.0, 4.0, 8.0)


# ---------------------------------------------------------------------------
# HTTP client protocol
# ---------------------------------------------------------------------------


class OandaTradingHTTPClient(Protocol):
    """HTTP client for Oanda trading operations (GET + POST + PUT)."""

    def get_json(self, path: str, params: dict[str, str]) -> dict[str, Any]: ...
    def post_json(self, path: str, body: dict[str, Any]) -> dict[str, Any]: ...
    def put_json(self, path: str, body: dict[str, Any]) -> dict[str, Any]: ...


class UrllibOandaTradingClient:
    """Real HTTP client using urllib for Oanda v20 REST API."""

    def __init__(self, api_key: str, *, base_url: str = OANDA_BASE_URL) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")

    def get_json(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        query = urlencode(params) if params else ""
        url = f"{self._base_url}{path}"
        if query:
            url = f"{url}?{query}"
        self._validate_url(url)
        req = Request(url, headers=self._headers())
        return self._fetch(req)

    def post_json(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        url = f"{self._base_url}{path}"
        self._validate_url(url)
        data = json.dumps(body).encode("utf-8")
        req = Request(url, data=data, headers=self._headers(), method="POST")
        req.add_header("Content-Type", "application/json")
        return self._fetch(req)

    def put_json(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        url = f"{self._base_url}{path}"
        self._validate_url(url)
        data = json.dumps(body).encode("utf-8")
        req = Request(url, data=data, headers=self._headers(), method="PUT")
        req.add_header("Content-Type", "application/json")
        return self._fetch(req)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Accept-Datetime-Format": "RFC3339",
        }

    def _validate_url(self, url: str) -> None:
        parsed = urlparse(url)
        expected = urlparse(self._base_url).netloc
        if parsed.scheme != "https" or parsed.netloc != expected:
            msg = f"unexpected oanda URL: {url}"
            raise ValueError(msg)

    def _fetch(self, req: Request) -> dict[str, Any]:
        with urlopen(req, timeout=30) as response:  # nosec B310
            payload = response.read().decode("utf-8")
        data = json.loads(payload)
        if not isinstance(data, dict):
            msg = "oanda response must be a JSON object"
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
# OandaAdapter
# ---------------------------------------------------------------------------


class OandaAdapter:
    """Oanda v20 REST adapter implementing BrokerAdapter protocol."""

    def __init__(
        self,
        account_id: str,
        api_key: str,
        *,
        http_client: OandaTradingHTTPClient | None = None,
        base_url: str = OANDA_BASE_URL,
    ) -> None:
        self._account_id = account_id
        self._http_client = http_client or UrllibOandaTradingClient(
            api_key, base_url=base_url,
        )

    # -- get_candles ----------------------------------------------------------

    def get_candles(
        self,
        instrument: str,
        interval: str,
        start: datetime,
        end: datetime,
    ) -> list[CandleRecord]:
        granularity = INTERVAL_TO_OANDA_GRANULARITY.get(interval)
        if granularity is None:
            msg = f"unsupported interval for oanda: {interval}"
            raise ValueError(msg)

        params = {
            "price": "M",
            "granularity": granularity,
            "from": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "to": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        path = f"/v3/instruments/{instrument}/candles"
        data = _retry_request(
            lambda: self._http_client.get_json(path, params),
        )
        return list(normalize_oanda_candles(data.get("candles", []), interval=interval))

    # -- get_account ----------------------------------------------------------

    def get_account(self) -> AccountInfo:
        path = f"/v3/accounts/{self._account_id}/summary"
        data = _retry_request(
            lambda: self._http_client.get_json(path, {}),
        )
        acct = data.get("account", {})
        return AccountInfo(
            balance=float(acct.get("balance", 0)),
            currency=str(acct.get("currency", "USD")),
            unrealized_pnl=float(acct.get("unrealizedPL", 0)),
            margin_used=float(acct.get("marginUsed", 0)),
            margin_available=float(acct.get("marginAvailable", 0)),
        )

    # -- get_positions --------------------------------------------------------

    def get_positions(self) -> list[Position]:
        path = f"/v3/accounts/{self._account_id}/openTrades"
        data = _retry_request(
            lambda: self._http_client.get_json(path, {}),
        )
        positions: list[Position] = []
        for trade in data.get("trades", []):
            units_raw = float(trade.get("currentUnits", 0))
            direction: Direction = "BUY" if units_raw > 0 else "SELL"

            sl_order = trade.get("stopLossOrder")
            stop_loss = float(sl_order["price"]) if sl_order else None

            positions.append(Position(
                instrument=str(trade.get("instrument", "")),
                direction=direction,
                units=abs(units_raw),
                entry_price=float(trade.get("price", 0)),
                unrealized_pnl=float(trade.get("unrealizedPL", 0)),
                stop_loss=stop_loss,
                trade_id=str(trade.get("id", "")),
            ))
        return positions

    # -- place_market_order ---------------------------------------------------

    def place_market_order(
        self,
        instrument: str,
        units: float,
        stop_loss: float,
        client_order_id: str,
    ) -> OrderResult:
        path = f"/v3/accounts/{self._account_id}/orders"
        body: dict[str, Any] = {
            "order": {
                "type": "MARKET",
                "instrument": instrument,
                "units": str(int(units)),
                "stopLossOnFill": {"price": f"{stop_loss:.4f}"},
                "clientExtensions": {"id": client_order_id},
            }
        }
        data = _retry_request(
            lambda: self._http_client.post_json(path, body),
        )
        return self._parse_order_response(data, instrument, client_order_id)

    # -- modify_stop_loss -----------------------------------------------------

    def modify_stop_loss(self, trade_id: str, new_stop: float) -> OrderResult:
        path = f"/v3/accounts/{self._account_id}/trades/{trade_id}/orders"
        body = {"stopLoss": {"price": f"{new_stop:.4f}"}}
        data = _retry_request(
            lambda: self._http_client.put_json(path, body),
        )
        sl_txn = data.get("stopLossOrderTransaction", {})
        return OrderResult(
            success=True,
            order_id=str(sl_txn.get("id", "")),
            client_order_id="",
            instrument="",
            direction="BUY",
            units=0.0,
            fill_price=None,
            timestamp=_parse_oanda_time(sl_txn.get("time", "")),
            error_message=None,
        )

    # -- close_position -------------------------------------------------------

    def close_position(self, trade_id: str) -> OrderResult:
        path = f"/v3/accounts/{self._account_id}/trades/{trade_id}/close"
        body = {"units": "ALL"}
        data = _retry_request(
            lambda: self._http_client.put_json(path, body),
        )
        return self._parse_order_response(data, "", "")

    # -- get_order_status -----------------------------------------------------

    def get_order_status(self, client_order_id: str) -> OrderStatus:
        path = f"/v3/accounts/{self._account_id}/orders/@{client_order_id}"
        data = _retry_request(
            lambda: self._http_client.get_json(path, {}),
        )
        order = data.get("order", {})
        state_map = {
            "PENDING": "PENDING",
            "FILLED": "FILLED",
            "CANCELLED": "CANCELLED",
            "TRIGGERED": "FILLED",
        }
        raw_state = str(order.get("state", "PENDING"))
        state = state_map.get(raw_state, "PENDING")

        filling = order.get("fillingTransaction", {})
        fill_price = float(filling["price"]) if "price" in filling else None
        fill_time = (
            _parse_oanda_time(filling["time"]) if "time" in filling else None
        )

        client_ext = order.get("clientExtensions", {})
        return OrderStatus(
            client_order_id=str(client_ext.get("id", client_order_id)),
            broker_order_id=str(order.get("id", "")),
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
        """Parse Oanda order create/fill response into OrderResult."""
        reject = data.get("orderRejectTransaction")
        if reject:
            return OrderResult(
                success=False,
                order_id=None,
                client_order_id=client_order_id,
                instrument=instrument,
                direction="BUY",
                units=0.0,
                fill_price=None,
                timestamp=datetime.now(UTC),
                error_message=str(reject.get("rejectReason", "UNKNOWN")),
            )

        fill = data.get("orderFillTransaction", {})
        units_raw = float(fill.get("units", 0))
        direction: Direction = "BUY" if units_raw > 0 else "SELL"

        trade_opened = fill.get("tradeOpened", {})
        trades_closed = fill.get("tradesClosed", [])
        trade_id = (
            trade_opened.get("tradeID")
            or (trades_closed[0].get("tradeID") if trades_closed else None)
            or fill.get("id", "")
        )

        create_txn = data.get("orderCreateTransaction", {})
        client_ext = create_txn.get("clientExtensions", {})

        return OrderResult(
            success=True,
            order_id=str(trade_id),
            client_order_id=str(client_ext.get("id", client_order_id)),
            instrument=instrument or str(fill.get("instrument", "")),
            direction=direction,
            units=abs(units_raw),
            fill_price=float(fill["price"]) if "price" in fill else None,
            timestamp=_parse_oanda_time(fill.get("time", "")),
            error_message=None,
        )


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------


def _parse_oanda_time(value: str) -> datetime:
    """Parse Oanda RFC3339 timestamp to UTC datetime."""
    if not value:
        return datetime.now(UTC)
    trimmed = value
    if value.endswith("Z"):
        trimmed = value[:-1] + "+00:00"
    # Oanda uses nanosecond precision — truncate to microseconds
    parts = trimmed.split(".")
    if len(parts) == 2:
        frac, tz = parts[1][:6], parts[1][6:]
        # Find timezone offset if present
        for sep in ("+", "-"):
            if sep in parts[1][1:]:
                idx = parts[1].index(sep, 1)
                frac = parts[1][:min(6, idx)]
                tz = parts[1][idx:]
                break
        trimmed = f"{parts[0]}.{frac}{tz}"
    return datetime.fromisoformat(trimmed).astimezone(UTC)
