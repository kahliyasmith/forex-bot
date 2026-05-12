from datetime import datetime, timezone
from decimal import Decimal

import pytest

from forex_bot.data import Quote
from forex_bot.risk.engine import (
    OpenRiskPosition,
    RiskEngine,
    RiskLimits,
    RiskState,
    TradeProposal,
)


def limits(**overrides) -> RiskLimits:
    values = {
        "risk_per_trade_pct": Decimal("0.25"),
        "max_daily_loss_pct": Decimal("1.0"),
        "max_weekly_loss_pct": Decimal("3.0"),
        "max_drawdown_pct": Decimal("8.0"),
        "max_open_trades": 2,
        "max_pair_exposure": Decimal("1000000"),
        "max_total_exposure": Decimal("1000000"),
        "max_leverage": Decimal("30"),
        "max_correlated_usd_exposure": Decimal("1000000"),
        "max_spread_pips": {"EUR_USD": Decimal("2.0")},
        "max_slippage_pips": Decimal("1.0"),
    }
    values.update(overrides)
    return RiskLimits(**values)


def state(**overrides) -> RiskState:
    values = {
        "account_equity": Decimal("10000"),
        "peak_equity": Decimal("10000"),
        "available_margin": Decimal("10000"),
    }
    values.update(overrides)
    return RiskState(**values)


def proposal(**overrides) -> TradeProposal:
    quote = overrides.pop(
        "quote",
        Quote("EUR_USD", bid="1.1000", ask="1.1002", timestamp=datetime.now(timezone.utc)),
    )
    values = {
        "pair": "EUR_USD",
        "direction": "long",
        "entry_price": Decimal("1.1002"),
        "stop_loss": Decimal("1.0977"),
        "requested_units": Decimal("5000"),
        "quote": quote,
        "expected_slippage_pips": Decimal("0.5"),
    }
    values.update(overrides)
    return TradeProposal(**values)


def assert_rejected(check: str, engine: RiskEngine, trade: TradeProposal, risk_state: RiskState) -> None:
    decision = engine.evaluate(trade, risk_state)
    assert decision.approved is False
    assert check in decision.rejected_checks


def test_approves_valid_trade() -> None:
    decision = RiskEngine(limits()).evaluate(proposal(), state())

    assert decision.approved is True
    assert decision.calculated_position_size == Decimal("5000")
    assert decision.risk_amount == Decimal("25.000")


def test_resizes_trade_to_risk_budget() -> None:
    decision = RiskEngine(limits()).evaluate(proposal(requested_units=Decimal("50000")), state())

    assert decision.approved is True
    assert decision.reason == "approved_resized"
    assert decision.calculated_position_size == Decimal("10000")


def test_rejects_missing_stop_loss() -> None:
    assert_rejected("stop_loss_required", RiskEngine(limits()), proposal(stop_loss=None), state())


def test_rejects_zero_stop_distance_as_risk_per_trade_failure() -> None:
    assert_rejected(
        "risk_per_trade",
        RiskEngine(limits()),
        proposal(stop_loss=Decimal("1.1002")),
        state(),
    )


def test_rejects_max_daily_loss() -> None:
    assert_rejected(
        "max_daily_loss",
        RiskEngine(limits()),
        proposal(),
        state(daily_pnl=Decimal("-100")),
    )


def test_rejects_max_weekly_loss() -> None:
    assert_rejected(
        "max_weekly_loss",
        RiskEngine(limits()),
        proposal(),
        state(weekly_pnl=Decimal("-300")),
    )


def test_rejects_max_drawdown() -> None:
    assert_rejected(
        "max_drawdown",
        RiskEngine(limits()),
        proposal(),
        state(account_equity=Decimal("9200"), peak_equity=Decimal("10000")),
    )


def test_rejects_max_open_trades() -> None:
    open_positions = (
        OpenRiskPosition("EUR_USD", "long", Decimal("1000"), Decimal("1.1000")),
        OpenRiskPosition("GBP_USD", "short", Decimal("1000"), Decimal("1.2500")),
    )
    assert_rejected(
        "max_open_trades",
        RiskEngine(limits()),
        proposal(),
        state(open_positions=open_positions),
    )


def test_rejects_max_pair_exposure() -> None:
    assert_rejected(
        "max_pair_exposure",
        RiskEngine(limits(max_pair_exposure=Decimal("1000"))),
        proposal(),
        state(),
    )


def test_rejects_max_total_exposure() -> None:
    assert_rejected(
        "max_total_exposure",
        RiskEngine(limits(max_total_exposure=Decimal("1000"))),
        proposal(),
        state(),
    )


def test_rejects_max_leverage() -> None:
    open_positions = (OpenRiskPosition("EUR_USD", "long", Decimal("40000"), Decimal("1.1000")),)
    assert_rejected(
        "max_leverage",
        RiskEngine(limits(max_leverage=Decimal("3"), max_total_exposure=Decimal("1000000"))),
        proposal(requested_units=Decimal("1000")),
        state(open_positions=open_positions),
    )


def test_rejects_margin_estimate() -> None:
    assert_rejected(
        "margin_estimate",
        RiskEngine(limits()),
        proposal(),
        state(available_margin=Decimal("0")),
    )


def test_rejects_correlated_usd_exposure() -> None:
    assert_rejected(
        "correlated_usd_exposure",
        RiskEngine(limits(max_correlated_usd_exposure=Decimal("1000"))),
        proposal(),
        state(),
    )


def test_rejects_max_spread() -> None:
    wide_quote = Quote("EUR_USD", bid="1.1000", ask="1.1005", timestamp=datetime.now(timezone.utc))
    assert_rejected(
        "max_spread",
        RiskEngine(limits()),
        proposal(quote=wide_quote),
        state(),
    )


def test_rejects_max_slippage() -> None:
    assert_rejected(
        "max_slippage",
        RiskEngine(limits()),
        proposal(expected_slippage_pips=Decimal("2")),
        state(),
    )


def test_rejects_blocked_session() -> None:
    assert_rejected(
        "blocked_session",
        RiskEngine(limits()),
        proposal(),
        state(blocked_session=True),
    )


def test_rejects_news_blackout() -> None:
    assert_rejected(
        "news_blackout",
        RiskEngine(limits()),
        proposal(),
        state(news_blackout=True),
    )
