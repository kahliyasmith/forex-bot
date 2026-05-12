from datetime import datetime, timezone
from decimal import Decimal

from forex_bot.data import CurrencyPair, Quote


def test_eur_usd_pip_size_spread_and_value() -> None:
    pair = CurrencyPair.parse("EUR_USD")
    quote = Quote(pair, bid="1.1000", ask="1.1002", timestamp=datetime.now(timezone.utc))

    assert pair.pip_size == Decimal("0.0001")
    assert quote.spread_pips == Decimal("2")
    assert pair.pip_value_usd(units=10000, price=quote.mid) == Decimal("1.0000")


def test_gbp_usd_pip_size_and_value() -> None:
    pair = CurrencyPair.parse("GBP_USD")

    assert pair.pip_size == Decimal("0.0001")
    assert pair.pip_value_usd(units=10000, price="1.2500") == Decimal("1.0000")


def test_usd_jpy_pip_size_and_value() -> None:
    pair = CurrencyPair.parse("USD_JPY")

    assert pair.pip_size == Decimal("0.01")
    assert pair.pip_value_usd(units=15000, price="150.00") == Decimal("1.00")


def test_quote_understands_bid_ask_fill_sides() -> None:
    quote = Quote("EUR_USD", bid="1.1000", ask="1.1002", timestamp=datetime.now(timezone.utc))

    assert quote.entry_price("long") == Decimal("1.1002")
    assert quote.exit_price("long") == Decimal("1.1000")
    assert quote.entry_price("short") == Decimal("1.1000")
    assert quote.exit_price("short") == Decimal("1.1002")
