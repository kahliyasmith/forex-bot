"""Broker interface shared by paper and live adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal

from forex_bot.data.models import CurrencyPair, Quote, to_decimal

OrderSide = Literal["buy", "sell"]
OrderType = Literal["market", "limit", "stop"]
OrderStatus = Literal["pending", "filled", "rejected", "closed"]


@dataclass(frozen=True)
class Account:
    balance: Decimal
    equity: Decimal
    available_margin: Decimal
    used_margin: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")
    daily_pnl: Decimal = Decimal("0")
    weekly_pnl: Decimal = Decimal("0")
    peak_equity: Decimal | None = None


@dataclass(frozen=True)
class Order:
    pair: CurrencyPair | str
    side: OrderSide
    units: Decimal | float | int | str
    order_type: OrderType = "market"
    stop_loss: Decimal | float | int | str | None = None
    take_profit: Decimal | float | int | str | None = None
    limit_price: Decimal | float | int | str | None = None
    strategy: str = "manual"
    metadata: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "pair", CurrencyPair.parse(self.pair))
        object.__setattr__(self, "units", to_decimal(self.units))
        if self.stop_loss is not None:
            object.__setattr__(self, "stop_loss", to_decimal(self.stop_loss))
        if self.take_profit is not None:
            object.__setattr__(self, "take_profit", to_decimal(self.take_profit))
        if self.limit_price is not None:
            object.__setattr__(self, "limit_price", to_decimal(self.limit_price))

    @property
    def direction(self) -> str:
        return "long" if self.side == "buy" else "short"


@dataclass(frozen=True)
class Position:
    id: str
    pair: CurrencyPair
    direction: str
    units: Decimal
    entry_price: Decimal
    opened_at: datetime
    stop_loss: Decimal | None
    take_profit: Decimal | None
    strategy: str = "manual"
    unrealized_pnl: Decimal = Decimal("0")


@dataclass(frozen=True)
class OrderResult:
    order_id: str
    status: OrderStatus
    reason: str
    position_id: str | None = None
    fill_price: Decimal | None = None
    filled_units: Decimal = Decimal("0")
    spread_pips: Decimal = Decimal("0")
    slippage_pips: Decimal = Decimal("0")
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class TradeHistoryRecord:
    pair: CurrencyPair
    direction: str
    units: Decimal
    entry_price: Decimal
    exit_price: Decimal
    opened_at: datetime
    closed_at: datetime
    reason: str
    realized_pnl: Decimal
    spread_pips: Decimal
    slippage_pips: Decimal
    strategy: str = "manual"
    session: str = "unknown"
    news_window: bool = False
    rollover_exposure: bool = False


class Broker(ABC):
    @abstractmethod
    def get_quote(self, pair: CurrencyPair | str) -> Quote:
        """Return the latest bid/ask quote for a pair."""

    @abstractmethod
    def get_account(self) -> Account:
        """Return account balance, equity, and margin state."""

    @abstractmethod
    def place_order(self, order: Order) -> OrderResult:
        """Place an order."""

    @abstractmethod
    def close_position(self, position_id: str) -> OrderResult:
        """Close an open position by id."""

    @abstractmethod
    def get_positions(self) -> list[Position]:
        """Return open positions."""
