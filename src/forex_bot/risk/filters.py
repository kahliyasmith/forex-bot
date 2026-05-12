"""Trading filters for spread, sessions, and news blackouts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml

from forex_bot.data.models import CurrencyPair, Quote, to_decimal

NEW_YORK = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class NewsEvent:
    currency: str
    impact: str
    starts_at: datetime
    blackout_minutes_before: int = 30
    blackout_minutes_after: int = 30

    def __post_init__(self) -> None:
        starts_at = self.starts_at
        if starts_at.tzinfo is None:
            starts_at = starts_at.replace(tzinfo=timezone.utc)
        object.__setattr__(self, "currency", self.currency.upper())
        object.__setattr__(self, "impact", self.impact.lower())
        object.__setattr__(self, "starts_at", starts_at.astimezone(timezone.utc))

    def affects(self, pair: CurrencyPair, at: datetime) -> bool:
        if self.impact != "high":
            return False
        if self.currency not in {pair.base, pair.quote}:
            return False
        at_utc = at.astimezone(timezone.utc)
        starts = self.starts_at
        begins = starts - timedelta(minutes=self.blackout_minutes_before)
        ends = starts + timedelta(minutes=self.blackout_minutes_after)
        return begins <= at_utc <= ends


@dataclass(frozen=True)
class SessionRule:
    allowed_weekdays: set[int] | None = None
    start_hour_utc: int | None = None
    end_hour_utc: int | None = None

    def allows(self, at: datetime) -> bool:
        at_utc = at.astimezone(timezone.utc)
        if self.allowed_weekdays is not None and at_utc.weekday() not in self.allowed_weekdays:
            return False
        if self.start_hour_utc is None or self.end_hour_utc is None:
            return True
        hour = at_utc.hour
        if self.start_hour_utc <= self.end_hour_utc:
            return self.start_hour_utc <= hour < self.end_hour_utc
        return hour >= self.start_hour_utc or hour < self.end_hour_utc


@dataclass(frozen=True)
class FilterDecision:
    allowed: bool
    reason: str
    rejected_filters: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class TradingFilterConfig:
    max_spread_pips: dict[str, Decimal]
    news_events: list[NewsEvent] = field(default_factory=list)
    rollover_start: time = time(16, 55)
    rollover_end: time = time(17, 10)
    friday_close_starts: time = time(16, 0)
    sunday_open_ends: time = time(18, 0)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "max_spread_pips",
            {pair.upper(): to_decimal(value) for pair, value in self.max_spread_pips.items()},
        )


class TradingFilters:
    def __init__(self, config: TradingFilterConfig) -> None:
        self.config = config

    def evaluate(
        self,
        *,
        quote: Quote,
        at: datetime | None = None,
        session_rule: SessionRule | None = None,
    ) -> FilterDecision:
        now = quote.timestamp if at is None else at
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        rejected: list[str] = []
        pair = quote.pair

        max_spread = self.config.max_spread_pips.get(pair.symbol)
        if max_spread is not None and quote.spread_pips > max_spread:
            rejected.append("max_spread")

        ny_time = now.astimezone(NEW_YORK)
        if self._in_rollover(ny_time):
            rejected.append("rollover_window")
        if self._near_friday_close(ny_time):
            rejected.append("friday_close")
        if self._in_sunday_open(ny_time):
            rejected.append("sunday_open")
        if any(event.affects(pair, now) for event in self.config.news_events):
            rejected.append("news_blackout")
        if session_rule is not None and not session_rule.allows(now):
            rejected.append("strategy_session_rule")

        if rejected:
            return FilterDecision(
                allowed=False,
                reason=f"Rejected by filters: {', '.join(rejected)}",
                rejected_filters=rejected,
            )
        return FilterDecision(allowed=True, reason="allowed")

    def _in_rollover(self, at_ny: datetime) -> bool:
        current = at_ny.time()
        return self.config.rollover_start <= current <= self.config.rollover_end

    def _near_friday_close(self, at_ny: datetime) -> bool:
        return at_ny.weekday() == 4 and at_ny.time() >= self.config.friday_close_starts

    def _in_sunday_open(self, at_ny: datetime) -> bool:
        return at_ny.weekday() == 6 and time(17, 0) <= at_ny.time() <= self.config.sunday_open_ends


def load_news_events(path: str | Path) -> list[NewsEvent]:
    with Path(path).open("r", encoding="utf-8") as event_file:
        raw: Any = yaml.safe_load(event_file) or {}
    events = raw.get("events", [])
    return [
        NewsEvent(
            currency=event["currency"],
            impact=event["impact"],
            starts_at=datetime.fromisoformat(event["starts_at"].replace("Z", "+00:00")),
            blackout_minutes_before=event.get("blackout_minutes_before", 30),
            blackout_minutes_after=event.get("blackout_minutes_after", 30),
        )
        for event in events
    ]


def build_filter_config(
    *,
    max_spread_pips: dict[str, Decimal | float | int | str],
    news_events_path: str | Path | None = None,
) -> TradingFilterConfig:
    return TradingFilterConfig(
        max_spread_pips={pair.upper(): to_decimal(value) for pair, value in max_spread_pips.items()},
        news_events=load_news_events(news_events_path) if news_events_path else [],
    )
