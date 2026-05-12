from datetime import datetime, timezone
from decimal import Decimal

from forex_bot.bot import DecisionResult, MonitoringState
from forex_bot.broker.base import OrderResult
from forex_bot.config import BotConfig
from forex_bot.data import Quote
from forex_bot.paper import PaperBroker
from forex_bot.risk.engine import RiskDecision
from forex_bot.status import build_status_snapshot, render_status


def config() -> BotConfig:
    return BotConfig.model_validate(
        {
            "mode": "paper",
            "base_currency": "USD",
            "pairs": ["EUR_USD"],
            "max_spread_pips": {"EUR_USD": 2.0},
            "risk": {
                "risk_per_trade_pct": 0.25,
                "max_daily_loss_pct": 1.0,
                "max_weekly_loss_pct": 3.0,
                "max_drawdown_pct": 8.0,
                "max_open_trades": 2,
                "max_leverage": 30.0,
            },
            "broker": {"type": "paper"},
            "execution": {"max_slippage_pips": 1.0, "require_stop_loss": True},
            "filters": {
                "avoid_news_minutes_before": 30,
                "avoid_news_minutes_after": 30,
                "avoid_rollover": True,
                "avoid_friday_close": True,
            },
        }
    )


def test_status_snapshot_and_render_includes_required_fields() -> None:
    broker = PaperBroker(starting_balance=10000)
    broker.update_quote(
        Quote("EUR_USD", bid="1.1000", ask="1.1002", timestamp=datetime.now(timezone.utc))
    )
    monitoring_state = MonitoringState(
        decisions=[
            DecisionResult(
                pair="EUR_USD",
                signal=None,
                filter_status="allowed",
                risk_decision=RiskDecision(
                    approved=False,
                    reason="Rejected: max_spread",
                    calculated_position_size=Decimal("0"),
                    rejected_checks=["max_spread"],
                ),
                order_result=None,
                skipped_reason="Rejected: max_spread",
            )
        ],
        pause_reasons=["abnormal_spread"],
    )

    snapshot = build_status_snapshot(
        config=config(),
        broker=broker,
        monitoring_state=monitoring_state,
    )
    output = render_status(snapshot)

    assert snapshot.rejected_signals_count == 1
    assert "Mode: paper" in output
    assert "Account equity: 10000" in output
    assert "Active kill switches: abnormal_spread" in output
    assert "EUR_USD: 2" in output
    assert "Rejected signals count: 1" in output


def test_status_handles_missing_quotes() -> None:
    snapshot = build_status_snapshot(config=config(), broker=PaperBroker())

    assert snapshot.latest_spread_per_pair["EUR_USD"] is None
    assert "EUR_USD: n/a" in render_status(snapshot)
