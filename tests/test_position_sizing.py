from decimal import Decimal

from forex_bot.risk.position_sizing import calculate_position_size


def test_eur_usd_position_size_for_25_dollar_risk() -> None:
    size = calculate_position_size(
        account_equity=10000,
        risk_per_trade_pct=0.25,
        stop_distance_pips=25,
        pair="EUR_USD",
        price="1.1000",
        max_leverage=30,
        available_margin=10000,
    )

    assert size.risk_dollars == Decimal("25.000")
    assert size.position_size_units == 10000
    assert size.estimated_pip_value == Decimal("1.0000")
    assert size.required_margin_estimate == Decimal("366.6666666666666666666666667")


def test_usd_jpy_position_size_for_25_dollar_risk() -> None:
    size = calculate_position_size(
        account_equity=10000,
        risk_per_trade_pct=0.25,
        stop_distance_pips=25,
        pair="USD_JPY",
        price="150.00",
        max_leverage=30,
        available_margin=10000,
    )

    assert size.risk_dollars == Decimal("25.000")
    assert size.position_size_units == 15000
    assert size.estimated_pip_value == Decimal("1.00")
    assert size.required_margin_estimate == Decimal("500")
