"""Guarded live broker adapter placeholder.

This adapter deliberately does not implement real order transport yet.
"""

from __future__ import annotations

import os
from decimal import Decimal
from typing import Mapping

from forex_bot.broker.base import Account, Broker, Order, OrderResult, Position
from forex_bot.config import TRUE_VALUES
from forex_bot.data.models import CurrencyPair, Quote
from forex_bot.risk.engine import RiskEngine, RiskState, TradeProposal


class LiveTradingDisabledError(RuntimeError):
    """Raised when code attempts live trading without explicit enablement."""


class LiveBrokerAdapter(Broker):
    def __init__(
        self,
        *,
        environ: Mapping[str, str] | None = None,
        risk_engine: RiskEngine | None = None,
        risk_state: RiskState | None = None,
    ) -> None:
        self.environ = os.environ if environ is None else environ
        self.api_key = self.environ.get("BROKER_API_KEY")
        self.account_id = self.environ.get("BROKER_ACCOUNT_ID")
        self.broker_env = self.environ.get("BROKER_ENV", "demo")
        self.risk_engine = risk_engine
        self.risk_state = risk_state

    @property
    def live_trading_enabled(self) -> bool:
        return self.environ.get("LIVE_TRADING_ENABLED", "").strip().lower() in TRUE_VALUES

    def get_quote(self, pair: CurrencyPair | str) -> Quote:
        raise NotImplementedError("live quotes are not implemented yet")

    def get_account(self) -> Account:
        raise NotImplementedError("live accounts are not implemented yet")

    def place_order(self, order: Order) -> OrderResult:
        if not self.live_trading_enabled:
            raise LiveTradingDisabledError("LIVE_TRADING_ENABLED=true is required for live orders")
        if order.stop_loss is None:
            raise ValueError("live orders must include stop_loss")
        if self.risk_engine is not None:
            if self.risk_state is None:
                raise ValueError("risk_state is required when risk_engine is configured")
            quote = self.get_quote(order.pair)
            decision = self.risk_engine.evaluate(
                TradeProposal(
                    pair=order.pair,
                    direction=order.direction,
                    entry_price=quote.entry_price(order.direction),
                    stop_loss=Decimal(order.stop_loss),
                    requested_units=Decimal(order.units),
                    quote=quote,
                ),
                self.risk_state,
            )
            if not decision.approved:
                raise ValueError(f"risk rejected live order: {decision.reason}")
        raise NotImplementedError("live order placement is not implemented")

    def close_position(self, position_id: str) -> OrderResult:
        raise LiveTradingDisabledError("live position closing is disabled")

    def get_positions(self) -> list[Position]:
        raise NotImplementedError("live positions are not implemented yet")
