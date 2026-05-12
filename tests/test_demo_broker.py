from datetime import datetime, timezone
from decimal import Decimal

import pytest

from forex_bot.broker import Order
from forex_bot.broker.demo import (
    BrokerApiError,
    DemoBrokerAdapter,
    DemoBrokerSettings,
    DemoTradingSafetyError,
    RetryableBrokerApiError,
)


class FakeDemoClient:
    def __init__(self) -> None:
        self.order_keys: list[str] = []
        self.order_payloads: list[dict] = []
        self.create_order_failures = 0

    def get_account(self, account_id: str):
        return {
            "account": {
                "balance": "10000",
                "NAV": "10050",
                "marginAvailable": "9000",
                "marginUsed": "1000",
                "pl": "50",
                "unrealizedPL": "25",
                "dailyPL": "10",
                "weeklyPL": "30",
                "peakNAV": "10100",
            }
        }

    def get_quote(self, account_id: str, pair: str):
        return {
            "prices": [
                {
                    "instrument": pair,
                    "bids": [{"price": "1.1000"}],
                    "asks": [{"price": "1.1002"}],
                    "time": "2026-01-05T14:00:00Z",
                }
            ]
        }

    def get_positions(self, account_id: str):
        return [
            {
                "instrument": "EUR_USD",
                "long": {
                    "units": "10000",
                    "averagePrice": "1.1002",
                    "unrealizedPL": "8",
                    "stopLoss": "1.0977",
                    "takeProfit": "1.1050",
                    "tradeOpenedAt": "2026-01-05T14:00:00Z",
                },
                "short": {"units": "0"},
            }
        ]

    def create_order(self, account_id: str, payload, idempotency_key: str):
        self.order_keys.append(idempotency_key)
        self.order_payloads.append(payload)
        if self.create_order_failures:
            self.create_order_failures -= 1
            raise RetryableBrokerApiError("timeout")
        return {
            "orderFillTransaction": {
                "id": "fill-1",
                "reason": "MARKET_ORDER",
                "price": "1.1002",
                "units": "10000",
                "time": "2026-01-05T14:00:01Z",
            }
        }

    def close_position(self, account_id: str, position_id: str):
        return {
            "closed": {
                "id": "close-1",
                "reason": "CLIENT_REQUEST",
                "price": "1.1010",
                "units": "10000",
                "time": "2026-01-05T14:05:00Z",
            }
        }


def demo_broker(client: FakeDemoClient) -> DemoBrokerAdapter:
    return DemoBrokerAdapter(
        client=client,
        account_id="demo-account",
        environ={"BROKER_ENV": "demo"},
        settings=DemoBrokerSettings(max_retries=2),
    )


def test_demo_broker_fetches_account_quote_and_positions() -> None:
    broker = demo_broker(FakeDemoClient())

    account = broker.get_account()
    quote = broker.get_quote("EUR_USD")
    positions = broker.get_positions()

    assert account.equity == Decimal("10050")
    assert account.daily_pnl == Decimal("10")
    assert quote.bid == Decimal("1.1000")
    assert quote.ask == Decimal("1.1002")
    assert positions[0].id == "EUR_USD:long"
    assert positions[0].stop_loss == Decimal("1.0977")


def test_demo_broker_places_and_closes_demo_order() -> None:
    client = FakeDemoClient()
    broker = demo_broker(client)

    result = broker.place_order(
        Order(
            "EUR_USD",
            side="buy",
            units=10000,
            stop_loss="1.0977",
            take_profit="1.1050",
            strategy="test",
            metadata={"idempotency_key": "signal-1"},
        )
    )
    close_result = broker.close_position("EUR_USD:long")

    assert result.status == "filled"
    assert result.position_id == "EUR_USD:long"
    assert client.order_payloads[0]["order"]["stopLossOnFill"]["price"] == "1.0977"
    assert client.order_keys == ["signal-1"]
    assert close_result.status == "closed"
    assert close_result.fill_price == Decimal("1.1010")


def test_demo_broker_retries_with_same_idempotency_key_without_duplicate_order() -> None:
    client = FakeDemoClient()
    client.create_order_failures = 1
    broker = demo_broker(client)
    order = Order(
        "EUR_USD",
        side="buy",
        units=10000,
        stop_loss="1.0977",
        metadata={"idempotency_key": "signal-2"},
    )

    first_result = broker.place_order(order)
    second_result = broker.place_order(order)

    assert first_result.status == "filled"
    assert second_result == first_result
    assert client.order_keys == ["signal-2", "signal-2"]


def test_demo_broker_reconciles_positions() -> None:
    broker = demo_broker(FakeDemoClient())

    report = broker.reconcile_positions({"EUR_USD:long", "GBP_USD:short"})

    assert report.in_sync is False
    assert report.matched_position_ids == {"EUR_USD:long"}
    assert report.missing_broker_position_ids == {"GBP_USD:short"}


def test_demo_broker_wraps_api_errors() -> None:
    class BrokenClient(FakeDemoClient):
        def get_account(self, account_id: str):
            raise RuntimeError("network down")

    broker = demo_broker(BrokenClient())

    with pytest.raises(BrokerApiError, match="network down"):
        broker.get_account()


def test_demo_broker_never_accepts_live_environment() -> None:
    with pytest.raises(DemoTradingSafetyError):
        DemoBrokerAdapter(
            client=FakeDemoClient(),
            account_id="real-account",
            environ={"BROKER_ENV": "live"},
        )
