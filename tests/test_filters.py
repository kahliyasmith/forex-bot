from datetime import datetime, timezone
from decimal import Decimal

from forex_bot.data import Quote
from forex_bot.risk.filters import NewsEvent, SessionRule, TradingFilterConfig, TradingFilters


def filters_with_news() -> TradingFilters:
    return TradingFilters(
        TradingFilterConfig(
            max_spread_pips={"EUR_USD": Decimal("1.0")},
            news_events=[
                NewsEvent(
                    currency="USD",
                    impact="high",
                    starts_at=datetime(2026, 1, 2, 13, 30, tzinfo=timezone.utc),
                    blackout_minutes_before=30,
                    blackout_minutes_after=30,
                )
            ],
        )
    )


def quote_at(timestamp: datetime, spread_pips: str = "0.8") -> Quote:
    return Quote.from_mid("EUR_USD", "1.1000", spread_pips, timestamp)


def test_rejects_spread_above_pair_max() -> None:
    decision = filters_with_news().evaluate(
        quote=quote_at(datetime(2026, 1, 5, 14, 0, tzinfo=timezone.utc), "1.5")
    )

    assert decision.allowed is False
    assert "max_spread" in decision.rejected_filters


def test_rejects_rollover_window() -> None:
    decision = filters_with_news().evaluate(
        quote=quote_at(datetime(2026, 1, 5, 21, 58, tzinfo=timezone.utc))
    )

    assert "rollover_window" in decision.rejected_filters


def test_rejects_friday_close() -> None:
    decision = filters_with_news().evaluate(
        quote=quote_at(datetime(2026, 1, 2, 21, 30, tzinfo=timezone.utc))
    )

    assert "friday_close" in decision.rejected_filters


def test_rejects_sunday_open() -> None:
    decision = filters_with_news().evaluate(
        quote=quote_at(datetime(2026, 1, 4, 22, 30, tzinfo=timezone.utc))
    )

    assert "sunday_open" in decision.rejected_filters


def test_rejects_news_blackout() -> None:
    decision = filters_with_news().evaluate(
        quote=quote_at(datetime(2026, 1, 2, 13, 15, tzinfo=timezone.utc))
    )

    assert "news_blackout" in decision.rejected_filters


def test_rejects_strategy_session_rule() -> None:
    decision = filters_with_news().evaluate(
        quote=quote_at(datetime(2026, 1, 5, 14, 0, tzinfo=timezone.utc)),
        session_rule=SessionRule(allowed_weekdays={1}),
    )

    assert "strategy_session_rule" in decision.rejected_filters
