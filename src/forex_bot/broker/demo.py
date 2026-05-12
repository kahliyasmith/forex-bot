"""Demo-account broker adapter.

The default transport is shaped for an OANDA practice account, but the adapter
depends on a small injectable client protocol so tests and future broker
providers can reuse the same Broker interface.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Mapping, Protocol
from uuid import uuid4

from forex_bot.broker.base import Account, Broker, Order, OrderResult, Position
from forex_bot.data.models import CurrencyPair, Quote, to_decimal

DEMO_ENVS = {"demo", "practice", "sandbox"}
OANDA_DEMO_URL = "https://api-fxpractice.oanda.com/v3"


class DemoTradingSafetyError(RuntimeError):
    """Raised when demo integration is pointed at a non-demo environment."""


class BrokerApiError(RuntimeError):
    """Non-retryable broker API failure."""


class RetryableBrokerApiError(BrokerApiError):
    """Broker API failure that can be retried safely with idempotency."""


class DemoBrokerClient(Protocol):
    def get_account(self, account_id: str) -> Mapping[str, Any]:
        ...

    def get_quote(self, account_id: str, pair: str) -> Mapping[str, Any]:
        ...

    def get_positions(self, account_id: str) -> list[Mapping[str, Any]]:
        ...

    def create_order(
        self,
        account_id: str,
        payload: Mapping[str, Any],
        idempotency_key: str,
    ) -> Mapping[str, Any]:
        ...

    def close_position(self, account_id: str, position_id: str) -> Mapping[str, Any]:
        ...


@dataclass(frozen=True)
class DemoBrokerSettings:
    max_retries: int = 2
    retry_backoff_seconds: float = 0


class DemoBrokerAdapter(Broker):
    def __init__(
        self,
        *,
        client: DemoBrokerClient | None = None,
        account_id: str | None = None,
        api_key: str | None = None,
        environ: Mapping[str, str] | None = None,
        settings: DemoBrokerSettings | None = None,
    ) -> None:
        env = os.environ if environ is None else environ
        self.broker_env = env.get("BROKER_ENV", "demo").strip().lower()
        if self.broker_env not in DEMO_ENVS:
            raise DemoTradingSafetyError("DemoBrokerAdapter only supports demo/practice/sandbox environments")

        self.account_id = account_id or env.get("BROKER_ACCOUNT_ID")
        self.api_key = api_key or env.get("BROKER_API_KEY")
        if not self.account_id:
            raise ValueError("BROKER_ACCOUNT_ID is required for demo broker integration")
        if client is None and not self.api_key:
            raise ValueError("BROKER_API_KEY is required when no demo client is injected")

        self.client = client or UrllibOandaDemoClient(api_key=self.api_key or "")
        self.settings = settings or DemoBrokerSettings()
        self._order_results_by_key: dict[str, OrderResult] = {}

    def get_account(self) -> Account:
        raw = self._api_call(lambda: self.client.get_account(self.account_id))
        account = raw.get("account", raw)
        balance = _decimal_field(account, "balance", "0")
        equity = _decimal_field(account, "NAV", str(balance))
        used_margin = _decimal_field(account, "marginUsed", "0")
        available_margin = _decimal_field(account, "marginAvailable", str(max(equity - used_margin, Decimal("0"))))
        realized_pnl = _decimal_field(account, "pl", "0")
        unrealized_pnl = _decimal_field(account, "unrealizedPL", "0")
        return Account(
            balance=balance,
            equity=equity,
            available_margin=available_margin,
            used_margin=used_margin,
            realized_pnl=realized_pnl,
            unrealized_pnl=unrealized_pnl,
            daily_pnl=_decimal_field(account, "dailyPL", str(realized_pnl)),
            weekly_pnl=_decimal_field(account, "weeklyPL", str(realized_pnl)),
            peak_equity=_decimal_field(account, "peakNAV", str(equity)),
        )

    def get_quote(self, pair: CurrencyPair | str) -> Quote:
        parsed_pair = CurrencyPair.parse(pair)
        raw = self._api_call(lambda: self.client.get_quote(self.account_id, parsed_pair.symbol))
        price = raw.get("price", raw.get("prices", [raw])[0])
        bid = price.get("bid") or price.get("bids", [{"price": None}])[0]["price"]
        ask = price.get("ask") or price.get("asks", [{"price": None}])[0]["price"]
        timestamp_raw = price.get("time") or price.get("timestamp")
        timestamp = _parse_timestamp(timestamp_raw)
        return Quote(pair=parsed_pair, bid=bid, ask=ask, timestamp=timestamp)

    def get_positions(self) -> list[Position]:
        raw_positions = self._api_call(lambda: self.client.get_positions(self.account_id))
        return [position for raw in raw_positions for position in _positions_from_raw(raw)]

    def place_order(self, order: Order) -> OrderResult:
        if order.stop_loss is None:
            return OrderResult(order_id="", status="rejected", reason="stop_loss_required")

        idempotency_key = str(order.metadata.get("idempotency_key") or uuid4())
        if idempotency_key in self._order_results_by_key:
            return self._order_results_by_key[idempotency_key]

        payload = self._order_payload(order, idempotency_key)
        response = self._retry_order_create(payload, idempotency_key)
        result = _order_result_from_response(response, order, idempotency_key)
        self._order_results_by_key[idempotency_key] = result
        return result

    def close_position(self, position_id: str) -> OrderResult:
        response = self._api_call(lambda: self.client.close_position(self.account_id, position_id))
        closed = response.get("closed", response)
        return OrderResult(
            order_id=str(closed.get("orderID") or closed.get("id") or position_id),
            status="closed",
            reason=str(closed.get("reason", "closed")),
            position_id=position_id,
            fill_price=to_decimal(closed["price"]) if closed.get("price") is not None else None,
            filled_units=to_decimal(closed.get("units", "0")),
            timestamp=_parse_timestamp(closed.get("time")),
        )

    def _retry_order_create(
        self,
        payload: Mapping[str, Any],
        idempotency_key: str,
    ) -> Mapping[str, Any]:
        attempts = self.settings.max_retries + 1
        last_error: RetryableBrokerApiError | None = None
        for attempt in range(attempts):
            try:
                return self.client.create_order(self.account_id, payload, idempotency_key)
            except RetryableBrokerApiError as exc:
                last_error = exc
                if attempt == attempts - 1:
                    break
                if self.settings.retry_backoff_seconds:
                    time.sleep(self.settings.retry_backoff_seconds)
        raise last_error or RetryableBrokerApiError("demo order create failed")

    def _api_call(self, call):
        try:
            return call()
        except RetryableBrokerApiError:
            raise
        except BrokerApiError:
            raise
        except Exception as exc:
            raise BrokerApiError(str(exc)) from exc

    def _order_payload(self, order: Order, idempotency_key: str) -> dict[str, Any]:
        units = order.units if order.side == "buy" else -order.units
        order_body: dict[str, Any] = {
            "type": "MARKET",
            "instrument": order.pair.symbol,
            "units": str(units),
            "timeInForce": "FOK",
            "positionFill": "DEFAULT",
            "clientExtensions": {"id": idempotency_key, "tag": order.strategy},
        }
        if order.stop_loss is not None:
            order_body["stopLossOnFill"] = {"price": str(order.stop_loss)}
        if order.take_profit is not None:
            order_body["takeProfitOnFill"] = {"price": str(order.take_profit)}
        return {"order": order_body}


class UrllibOandaDemoClient:
    def __init__(self, *, api_key: str, base_url: str = OANDA_DEMO_URL, timeout_seconds: int = 10) -> None:
        if "fxpractice" not in base_url and "practice" not in base_url:
            raise DemoTradingSafetyError("demo client must use a practice/demo endpoint")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def get_account(self, account_id: str) -> Mapping[str, Any]:
        return self._request("GET", f"/accounts/{account_id}/summary")

    def get_quote(self, account_id: str, pair: str) -> Mapping[str, Any]:
        query = urllib.parse.urlencode({"instruments": pair})
        return self._request("GET", f"/accounts/{account_id}/pricing?{query}")

    def get_positions(self, account_id: str) -> list[Mapping[str, Any]]:
        payload = self._request("GET", f"/accounts/{account_id}/openPositions")
        return list(payload.get("positions", []))

    def create_order(
        self,
        account_id: str,
        payload: Mapping[str, Any],
        idempotency_key: str,
    ) -> Mapping[str, Any]:
        return self._request(
            "POST",
            f"/accounts/{account_id}/orders",
            payload=payload,
            headers={"X-Request-ID": idempotency_key},
        )

    def close_position(self, account_id: str, position_id: str) -> Mapping[str, Any]:
        instrument, side = _split_position_id(position_id)
        units_key = "longUnits" if side == "long" else "shortUnits"
        return self._request(
            "PUT",
            f"/accounts/{account_id}/positions/{instrument}/close",
            payload={units_key: "ALL"},
        )

    def _request(
        self,
        method: str,
        path: str,
        *,
        payload: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> Mapping[str, Any]:
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=body,
            method=method,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                **dict(headers or {}),
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body_text = exc.read().decode("utf-8", errors="replace")
            if exc.code in {408, 429, 500, 502, 503, 504}:
                raise RetryableBrokerApiError(body_text) from exc
            raise BrokerApiError(body_text) from exc
        except urllib.error.URLError as exc:
            raise RetryableBrokerApiError(str(exc)) from exc


def _decimal_field(payload: Mapping[str, Any], key: str, default: str) -> Decimal:
    return to_decimal(payload.get(key, default))


def _parse_timestamp(value: Any) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _positions_from_raw(raw: Mapping[str, Any]) -> list[Position]:
    pair = CurrencyPair.parse(str(raw.get("instrument")))
    positions: list[Position] = []
    for direction, side in (("long", raw.get("long", {})), ("short", raw.get("short", {}))):
        units = abs(to_decimal(side.get("units", "0")))
        if units == 0:
            continue
        entry_price = to_decimal(side.get("averagePrice", raw.get("price", "0")))
        positions.append(
            Position(
                id=f"{pair.symbol}:{direction}",
                pair=pair,
                direction=direction,
                units=units,
                entry_price=entry_price,
                opened_at=_parse_timestamp(side.get("tradeOpenedAt") or raw.get("time")),
                stop_loss=to_decimal(side["stopLoss"]) if side.get("stopLoss") is not None else None,
                take_profit=to_decimal(side["takeProfit"]) if side.get("takeProfit") is not None else None,
                unrealized_pnl=to_decimal(side.get("unrealizedPL", "0")),
            )
        )
    return positions


def _order_result_from_response(
    response: Mapping[str, Any],
    order: Order,
    idempotency_key: str,
) -> OrderResult:
    fill = response.get("orderFillTransaction")
    reject = response.get("orderRejectTransaction")
    create = response.get("orderCreateTransaction", {})
    if reject:
        return OrderResult(
            order_id=str(reject.get("id", idempotency_key)),
            status="rejected",
            reason=str(reject.get("rejectReason", "rejected")),
            timestamp=_parse_timestamp(reject.get("time")),
        )
    if fill:
        return OrderResult(
            order_id=str(fill.get("id", idempotency_key)),
            status="filled",
            reason=str(fill.get("reason", "filled")),
            position_id=f"{order.pair.symbol}:{order.direction}",
            fill_price=to_decimal(fill.get("price", "0")),
            filled_units=abs(to_decimal(fill.get("units", order.units))),
            timestamp=_parse_timestamp(fill.get("time")),
        )
    return OrderResult(
        order_id=str(create.get("id", idempotency_key)),
        status="pending",
        reason="pending",
        position_id=None,
    )


def _split_position_id(position_id: str) -> tuple[str, str]:
    parts = position_id.split(":")
    if len(parts) != 2 or parts[1] not in {"long", "short"}:
        raise ValueError("position_id must look like EUR_USD:long or EUR_USD:short")
    return parts[0], parts[1]
