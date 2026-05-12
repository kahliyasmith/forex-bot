"""Strategy interface and signal model."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import timedelta
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from forex_bot.data.models import Candle, CurrencyPair, Quote, to_decimal


class StrategyParameters(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TradeSignal(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    pair: CurrencyPair
    direction: str = Field(pattern="^(long|short)$")
    confidence: float = Field(ge=0, le=1)
    entry_reason: str
    proposed_stop_loss: Decimal
    proposed_take_profit: Decimal
    expected_holding_period: timedelta | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("pair", mode="before")
    @classmethod
    def parse_pair(cls, value: CurrencyPair | str) -> CurrencyPair:
        return CurrencyPair.parse(value)

    @field_validator("proposed_stop_loss", "proposed_take_profit", mode="before")
    @classmethod
    def parse_decimal(cls, value: Decimal | float | int | str) -> Decimal:
        return to_decimal(value)


class Strategy(ABC):
    parameters: StrategyParameters

    def on_tick(self, quote: Quote) -> TradeSignal | None:
        return self.generate_signal(quote)

    def on_candle(self, candle: Candle) -> TradeSignal | None:
        return self.generate_signal(candle)

    @abstractmethod
    def generate_signal(self, event: Quote | Candle) -> TradeSignal | None:
        """Generate a signal from market data without placing orders."""

    @abstractmethod
    def required_timeframes(self) -> tuple[str, ...]:
        """Return the timeframes required by the strategy."""
