"""Simple trend-pullback strategy."""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from pydantic import Field, field_validator

from forex_bot.data.models import Candle, CurrencyPair, Quote, to_decimal
from forex_bot.risk.filters import FilterDecision, TradingFilters
from forex_bot.strategies.base import Strategy, StrategyParameters, TradeSignal


class TrendPullbackParameters(StrategyParameters):
    allowed_pairs: list[str]
    trend_ma_period: int = Field(default=5, ge=2)
    pullback_lookback: int = Field(default=3, ge=1)
    atr_period: int = Field(default=3, ge=1)
    atr_multiplier: Decimal = Field(default=Decimal("1.5"), gt=0)
    reward_r_multiple: Decimal = Field(default=Decimal("2.0"), gt=0)
    min_confidence: float = Field(default=0.6, ge=0, le=1)

    @field_validator("allowed_pairs")
    @classmethod
    def normalize_pairs(cls, values: list[str]) -> list[str]:
        return [CurrencyPair.parse(value).symbol for value in values]

    @field_validator("atr_multiplier", "reward_r_multiple", mode="before")
    @classmethod
    def parse_decimal(cls, value: Decimal | float | int | str) -> Decimal:
        return to_decimal(value)


class TrendPullbackStrategy(Strategy):
    def __init__(
        self,
        parameters: TrendPullbackParameters,
        trading_filters: TradingFilters | None = None,
    ) -> None:
        self.parameters = parameters
        self.trading_filters = trading_filters
        self._candles: dict[str, list[Candle]] = defaultdict(list)

    def required_timeframes(self) -> tuple[str, ...]:
        return ("trend", "entry")

    def on_candle(self, candle: Candle, quote: Quote | None = None) -> TradeSignal | None:
        pair = candle.pair.symbol
        self._candles[pair].append(candle)
        if pair not in self.parameters.allowed_pairs:
            return None
        if quote is not None and self.trading_filters is not None:
            decision = self.trading_filters.evaluate(quote=quote, at=candle.timestamp)
            if not decision.allowed:
                return None
        return self.generate_signal(candle)

    def generate_signal(self, event: Quote | Candle) -> TradeSignal | None:
        if not isinstance(event, Candle):
            return None
        candles = self._candles[event.pair.symbol]
        required = max(self.parameters.trend_ma_period, self.parameters.atr_period + 1) + 1
        if len(candles) < required:
            return None

        trend_ma = self._simple_moving_average(candles[-self.parameters.trend_ma_period :])
        atr = self._atr(candles[-(self.parameters.atr_period + 1) :])
        previous = candles[-2]
        current = candles[-1]
        recent = candles[-(self.parameters.pullback_lookback + 1) : -1]

        if current.close > trend_ma and previous.low <= trend_ma and current.close > previous.high:
            stop = current.close - (atr * self.parameters.atr_multiplier)
            risk = current.close - stop
            take_profit = current.close + (risk * self.parameters.reward_r_multiple)
            return TradeSignal(
                pair=current.pair,
                direction="long",
                confidence=self.parameters.min_confidence,
                entry_reason="trend_pullback_continuation",
                proposed_stop_loss=stop,
                proposed_take_profit=take_profit,
                expected_holding_period=timedelta(hours=8),
                metadata={"trend_ma": trend_ma, "atr": atr, "pullback_candles": len(recent)},
            )

        if current.close < trend_ma and previous.high >= trend_ma and current.close < previous.low:
            stop = current.close + (atr * self.parameters.atr_multiplier)
            risk = stop - current.close
            take_profit = current.close - (risk * self.parameters.reward_r_multiple)
            return TradeSignal(
                pair=current.pair,
                direction="short",
                confidence=self.parameters.min_confidence,
                entry_reason="trend_pullback_continuation",
                proposed_stop_loss=stop,
                proposed_take_profit=take_profit,
                expected_holding_period=timedelta(hours=8),
                metadata={"trend_ma": trend_ma, "atr": atr, "pullback_candles": len(recent)},
            )

        return None

    def _simple_moving_average(self, candles: list[Candle]) -> Decimal:
        return sum((candle.close for candle in candles), Decimal("0")) / Decimal(len(candles))

    def _atr(self, candles: list[Candle]) -> Decimal:
        ranges: list[Decimal] = []
        for previous, current in zip(candles, candles[1:]):
            ranges.append(
                max(
                    current.high - current.low,
                    abs(current.high - previous.close),
                    abs(current.low - previous.close),
                )
            )
        return sum(ranges, Decimal("0")) / Decimal(len(ranges))
