"""Forex position sizing helpers."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from forex_bot.data.models import CurrencyPair, floor_units, to_decimal


@dataclass(frozen=True)
class PositionSize:
    position_size_units: int
    estimated_pip_value: Decimal
    notional_exposure: Decimal
    required_margin_estimate: Decimal
    risk_dollars: Decimal


def calculate_position_size(
    *,
    account_equity: Decimal | float | int | str,
    risk_per_trade_pct: Decimal | float | int | str,
    stop_distance_pips: Decimal | float | int | str,
    pair: CurrencyPair | str,
    price: Decimal | float | int | str,
    max_leverage: Decimal | float | int | str,
    available_margin: Decimal | float | int | str,
) -> PositionSize:
    parsed_pair = CurrencyPair.parse(pair)
    equity = to_decimal(account_equity)
    risk_pct = to_decimal(risk_per_trade_pct)
    stop_pips = to_decimal(stop_distance_pips)
    current_price = to_decimal(price)
    leverage = to_decimal(max_leverage)
    margin_available = to_decimal(available_margin)

    if equity <= 0:
        raise ValueError("account_equity must be positive")
    if risk_pct <= 0:
        raise ValueError("risk_per_trade_pct must be positive")
    if stop_pips <= 0:
        raise ValueError("stop_distance_pips must be positive")
    if leverage <= 0:
        raise ValueError("max_leverage must be positive")
    if margin_available < 0:
        raise ValueError("available_margin must be non-negative")

    risk_dollars = equity * (risk_pct / Decimal("100"))
    pip_value_per_unit = parsed_pair.pip_value_usd(units=1, price=current_price)
    if pip_value_per_unit is None:
        raise ValueError(f"pip value requires a USD conversion rate for {parsed_pair.symbol}")

    stop_distance_value = stop_pips * pip_value_per_unit
    risk_sized_units = risk_dollars / stop_distance_value

    notional_per_unit = parsed_pair.notional_usd(units=1, price=current_price)
    max_units_by_margin = (margin_available * leverage) / notional_per_unit
    units = floor_units(min(risk_sized_units, max_units_by_margin))

    estimated_pip_value = pip_value_per_unit * Decimal(units)
    notional_exposure = parsed_pair.notional_usd(units=units, price=current_price)
    required_margin = notional_exposure / leverage

    return PositionSize(
        position_size_units=units,
        estimated_pip_value=estimated_pip_value,
        notional_exposure=notional_exposure,
        required_margin_estimate=required_margin,
        risk_dollars=risk_dollars,
    )
