"""Forex market data models and pip helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_FLOOR
from typing import Literal

TradeDirection = Literal["long", "short"]


def to_decimal(value: Decimal | float | int | str) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


@dataclass(frozen=True)
class CurrencyPair:
    """A normalized currency pair such as EUR_USD or USD_JPY."""

    base: str
    quote: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "base", self.base.upper())
        object.__setattr__(self, "quote", self.quote.upper())
        if len(self.base) != 3 or len(self.quote) != 3:
            raise ValueError("currency codes must be three letters")

    @classmethod
    def parse(cls, value: "CurrencyPair | str") -> "CurrencyPair":
        if isinstance(value, CurrencyPair):
            return value
        normalized = value.upper()
        if "_" not in normalized and len(normalized) == 6:
            normalized = f"{normalized[:3]}_{normalized[3:]}"
        parts = normalized.split("_")
        if len(parts) != 2:
            raise ValueError(f"invalid currency pair: {value}")
        return cls(base=parts[0], quote=parts[1])

    @property
    def symbol(self) -> str:
        return f"{self.base}_{self.quote}"

    @property
    def pip_size(self) -> Decimal:
        return Decimal("0.01") if self.quote == "JPY" else Decimal("0.0001")

    def pips_between(
        self,
        first: Decimal | float | int | str,
        second: Decimal | float | int | str,
    ) -> Decimal:
        return abs(to_decimal(first) - to_decimal(second)) / self.pip_size

    def pip_value_usd(
        self,
        units: Decimal | float | int | str = 1,
        price: Decimal | float | int | str | None = None,
    ) -> Decimal | None:
        """Return the estimated USD value of one pip for the given unit count.

        For USD-quoted pairs like EUR_USD, pip value is direct. For USD_JPY,
        the JPY pip value is converted back to USD using the current price.
        Other crosses need a conversion rate and return None for now.
        """

        unit_count = to_decimal(units)
        if self.quote == "USD":
            return self.pip_size * unit_count
        if self.base == "USD" and price is not None:
            return (self.pip_size * unit_count) / to_decimal(price)
        return None

    def notional_usd(
        self,
        units: Decimal | float | int | str,
        price: Decimal | float | int | str,
    ) -> Decimal:
        unit_count = to_decimal(units)
        current_price = to_decimal(price)
        if self.quote == "USD":
            return unit_count * current_price
        if self.base == "USD":
            return unit_count
        return unit_count * current_price

    def pnl_usd(
        self,
        direction: TradeDirection,
        entry_price: Decimal | float | int | str,
        exit_price: Decimal | float | int | str,
        units: Decimal | float | int | str,
    ) -> Decimal:
        entry = to_decimal(entry_price)
        exit_ = to_decimal(exit_price)
        unit_count = to_decimal(units)
        price_delta = exit_ - entry if direction == "long" else entry - exit_
        pnl_quote = price_delta * unit_count
        if self.quote == "USD":
            return pnl_quote
        if self.base == "USD" and exit_ != 0:
            return pnl_quote / exit_
        return pnl_quote


@dataclass(frozen=True)
class Quote:
    """Bid/ask quote.

    Trading convention:
    - Long entry fills at ask.
    - Long exit fills at bid.
    - Short entry fills at bid.
    - Short exit fills at ask.
    """

    pair: CurrencyPair | str
    bid: Decimal | float | int | str
    ask: Decimal | float | int | str
    timestamp: datetime

    def __post_init__(self) -> None:
        pair = CurrencyPair.parse(self.pair)
        bid = to_decimal(self.bid)
        ask = to_decimal(self.ask)
        if ask < bid:
            raise ValueError("ask must be greater than or equal to bid")
        ts = self.timestamp
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        object.__setattr__(self, "pair", pair)
        object.__setattr__(self, "bid", bid)
        object.__setattr__(self, "ask", ask)
        object.__setattr__(self, "timestamp", ts)

    @classmethod
    def from_mid(
        cls,
        pair: CurrencyPair | str,
        mid: Decimal | float | int | str,
        spread_pips: Decimal | float | int | str,
        timestamp: datetime,
    ) -> "Quote":
        parsed_pair = CurrencyPair.parse(pair)
        half_spread = to_decimal(spread_pips) * parsed_pair.pip_size / Decimal("2")
        mid_price = to_decimal(mid)
        return cls(
            pair=parsed_pair,
            bid=mid_price - half_spread,
            ask=mid_price + half_spread,
            timestamp=timestamp,
        )

    @property
    def spread(self) -> Decimal:
        return self.ask - self.bid

    @property
    def spread_pips(self) -> Decimal:
        return self.spread / self.pair.pip_size

    @property
    def mid(self) -> Decimal:
        return (self.bid + self.ask) / Decimal("2")

    def entry_price(self, direction: TradeDirection, slippage_pips: Decimal = Decimal("0")) -> Decimal:
        slippage = slippage_pips * self.pair.pip_size
        return self.ask + slippage if direction == "long" else self.bid - slippage

    def exit_price(self, direction: TradeDirection, slippage_pips: Decimal = Decimal("0")) -> Decimal:
        slippage = slippage_pips * self.pair.pip_size
        return self.bid - slippage if direction == "long" else self.ask + slippage


@dataclass(frozen=True)
class Candle:
    """OHLCV candle."""

    pair: CurrencyPair | str
    open: Decimal | float | int | str
    high: Decimal | float | int | str
    low: Decimal | float | int | str
    close: Decimal | float | int | str
    volume: Decimal | float | int | str
    timestamp: datetime

    def __post_init__(self) -> None:
        pair = CurrencyPair.parse(self.pair)
        open_ = to_decimal(self.open)
        high = to_decimal(self.high)
        low = to_decimal(self.low)
        close = to_decimal(self.close)
        volume = to_decimal(self.volume)
        if high < max(open_, close) or low > min(open_, close):
            raise ValueError("candle high/low must contain open and close")
        if volume < 0:
            raise ValueError("volume must be non-negative")
        ts = self.timestamp
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        object.__setattr__(self, "pair", pair)
        object.__setattr__(self, "open", open_)
        object.__setattr__(self, "high", high)
        object.__setattr__(self, "low", low)
        object.__setattr__(self, "close", close)
        object.__setattr__(self, "volume", volume)
        object.__setattr__(self, "timestamp", ts)


@dataclass(frozen=True)
class BidAskCandle:
    """Bid/ask OHLCV candle.

    Backtest runner code can normalize this into a mid-price candle plus a
    measured spread assumption without changing strategy logic.
    """

    pair: CurrencyPair | str
    bid_open: Decimal | float | int | str
    bid_high: Decimal | float | int | str
    bid_low: Decimal | float | int | str
    bid_close: Decimal | float | int | str
    ask_open: Decimal | float | int | str
    ask_high: Decimal | float | int | str
    ask_low: Decimal | float | int | str
    ask_close: Decimal | float | int | str
    volume: Decimal | float | int | str
    timestamp: datetime

    def __post_init__(self) -> None:
        pair = CurrencyPair.parse(self.pair)
        prices = {
            "bid_open": to_decimal(self.bid_open),
            "bid_high": to_decimal(self.bid_high),
            "bid_low": to_decimal(self.bid_low),
            "bid_close": to_decimal(self.bid_close),
            "ask_open": to_decimal(self.ask_open),
            "ask_high": to_decimal(self.ask_high),
            "ask_low": to_decimal(self.ask_low),
            "ask_close": to_decimal(self.ask_close),
        }
        volume = to_decimal(self.volume)
        if min(prices.values()) <= 0:
            raise ValueError("bid/ask candle prices must be positive")
        if volume < 0:
            raise ValueError("volume must be non-negative")
        if prices["bid_high"] < max(prices["bid_open"], prices["bid_close"]) or prices[
            "bid_low"
        ] > min(prices["bid_open"], prices["bid_close"]):
            raise ValueError("bid high/low must contain bid open and close")
        if prices["ask_high"] < max(prices["ask_open"], prices["ask_close"]) or prices[
            "ask_low"
        ] > min(prices["ask_open"], prices["ask_close"]):
            raise ValueError("ask high/low must contain ask open and close")
        for field in ("open", "high", "low", "close"):
            if prices[f"ask_{field}"] < prices[f"bid_{field}"]:
                raise ValueError(f"ask_{field} must be greater than or equal to bid_{field}")
        ts = self.timestamp
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        object.__setattr__(self, "pair", pair)
        for name, value in prices.items():
            object.__setattr__(self, name, value)
        object.__setattr__(self, "volume", volume)
        object.__setattr__(self, "timestamp", ts)

    @property
    def spread_pips(self) -> Decimal:
        return (self.ask_close - self.bid_close) / self.pair.pip_size

    def to_mid_candle(self) -> Candle:
        return Candle(
            pair=self.pair,
            open=(self.bid_open + self.ask_open) / Decimal("2"),
            high=(self.bid_high + self.ask_high) / Decimal("2"),
            low=(self.bid_low + self.ask_low) / Decimal("2"),
            close=(self.bid_close + self.ask_close) / Decimal("2"),
            volume=self.volume,
            timestamp=self.timestamp,
        )


def floor_units(units: Decimal) -> int:
    return int(units.to_integral_value(rounding=ROUND_FLOOR))
