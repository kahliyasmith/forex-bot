from datetime import datetime, timedelta, timezone
from decimal import Decimal

from forex_bot.broker import Order
from forex_bot.data import Quote
from forex_bot.paper import PaperBroker


def test_paper_broker_fills_long_at_ask_and_tracks_unrealized_pnl() -> None:
    broker = PaperBroker(slippage_pips=Decimal("0.5"))
    now = datetime(2026, 1, 5, 14, tzinfo=timezone.utc)
    broker.update_quote(Quote("EUR_USD", bid="1.1000", ask="1.1002", timestamp=now))

    result = broker.place_order(
        Order("EUR_USD", side="buy", units=10000, stop_loss="1.0975", take_profit="1.1020")
    )

    assert result.status == "filled"
    assert result.fill_price == Decimal("1.10025")
    assert broker.get_positions()[0].entry_price == Decimal("1.10025")

    broker.update_quote(
        Quote("EUR_USD", bid="1.1010", ask="1.1012", timestamp=now + timedelta(minutes=1))
    )

    assert broker.get_account().unrealized_pnl == Decimal("7.50000")


def test_paper_broker_closes_take_profit_and_records_history() -> None:
    broker = PaperBroker()
    now = datetime(2026, 1, 5, 14, tzinfo=timezone.utc)
    broker.update_quote(Quote("EUR_USD", bid="1.1000", ask="1.1002", timestamp=now))
    broker.place_order(
        Order("EUR_USD", side="buy", units=10000, stop_loss="1.0975", take_profit="1.1010")
    )

    broker.update_quote(
        Quote("EUR_USD", bid="1.1010", ask="1.1012", timestamp=now + timedelta(minutes=5))
    )

    assert broker.get_positions() == []
    assert broker.get_trade_history()[0].reason == "take_profit"
    assert broker.get_trade_history()[0].realized_pnl == Decimal("8.0000")


def test_paper_broker_rejects_orders_without_stop_loss() -> None:
    broker = PaperBroker()
    broker.update_quote(Quote("GBP_USD", bid="1.2500", ask="1.2503", timestamp=datetime.now(timezone.utc)))

    result = broker.place_order(Order("GBP_USD", side="sell", units=10000))

    assert result.status == "rejected"
    assert result.reason == "stop_loss_required"


def test_paper_broker_tracks_pending_orders() -> None:
    broker = PaperBroker()
    now = datetime(2026, 1, 5, 14, tzinfo=timezone.utc)
    broker.update_quote(Quote("EUR_USD", bid="1.1000", ask="1.1002", timestamp=now))

    result = broker.place_order(
        Order(
            "EUR_USD",
            side="buy",
            units=10000,
            order_type="limit",
            limit_price="1.0990",
            stop_loss="1.0970",
        )
    )

    assert result.status == "pending"
    assert len(broker.get_pending_orders()) == 1
