from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from forex_bot.broker import Position
from forex_bot.data import CurrencyPair, Quote
from forex_bot.monitoring.kill_switch import KillSwitch, KillSwitchConfig, KillSwitchState


def config() -> KillSwitchConfig:
    return KillSwitchConfig(
        max_daily_loss_pct=Decimal("1"),
        max_weekly_loss_pct=Decimal("3"),
        max_drawdown_pct=Decimal("8"),
        max_spread_pips=Decimal("2"),
        max_slippage_pips=Decimal("1"),
        max_order_rejects=3,
        max_api_errors=3,
    )


def base_state(**overrides) -> KillSwitchState:
    now = datetime(2026, 1, 5, 14, tzinfo=timezone.utc)
    values = {
        "account_equity": Decimal("10000"),
        "peak_equity": Decimal("10000"),
        "latest_quote": Quote("EUR_USD", bid="1.1000", ask="1.1001", timestamp=now),
        "now": now,
    }
    values.update(overrides)
    return KillSwitchState(**values)


@pytest.mark.parametrize(
    ("reason", "overrides"),
    [
        ("daily_loss_exceeded", {"daily_pnl": Decimal("-100")}),
        ("weekly_loss_exceeded", {"weekly_pnl": Decimal("-300")}),
        ("drawdown_exceeded", {"account_equity": Decimal("9200")}),
        (
            "abnormal_spread",
            {"latest_quote": Quote("EUR_USD", bid="1.1000", ask="1.1004", timestamp=datetime(2026, 1, 5, 14, tzinfo=timezone.utc))},
        ),
        ("abnormal_slippage", {"observed_slippage_pips": Decimal("2")}),
        (
            "stale_data_feed",
            {"latest_quote": Quote("EUR_USD", bid="1.1000", ask="1.1001", timestamp=datetime(2026, 1, 5, 13, 58, tzinfo=timezone.utc))},
        ),
        (
            "position_mismatch",
            {
                "broker_positions": [
                    Position(
                        id="pos-1",
                        pair=CurrencyPair.parse("EUR_USD"),
                        direction="long",
                        units=Decimal("1000"),
                        entry_price=Decimal("1.1000"),
                        opened_at=datetime(2026, 1, 5, 14, tzinfo=timezone.utc),
                        stop_loss=Decimal("1.0900"),
                        take_profit=None,
                    )
                ],
                "internal_position_ids": set(),
            },
        ),
        (
            "missing_stop_loss",
            {
                "broker_positions": [
                    Position(
                        id="pos-1",
                        pair=CurrencyPair.parse("EUR_USD"),
                        direction="long",
                        units=Decimal("1000"),
                        entry_price=Decimal("1.1000"),
                        opened_at=datetime(2026, 1, 5, 14, tzinfo=timezone.utc),
                        stop_loss=None,
                        take_profit=None,
                    )
                ],
                "internal_position_ids": {"pos-1"},
            },
        ),
        ("too_many_order_rejects", {"order_reject_count": 3}),
        ("too_many_api_errors", {"api_error_count": 3}),
    ],
)
def test_kill_switch_pauses_for_each_condition(reason: str, overrides: dict) -> None:
    decision = KillSwitch(config()).evaluate(base_state(**overrides))

    assert decision.trading_paused is True
    assert reason in decision.reasons
