from datetime import datetime, timezone
from decimal import Decimal

import pytest

from forex_bot.broker import Order
from forex_bot.broker.live import LiveBrokerAdapter, LiveTradingDisabledError
from forex_bot.data import Quote
from forex_bot.risk.engine import RiskEngine, RiskLimits, RiskState


class QuoteLiveBroker(LiveBrokerAdapter):
    def get_quote(self, pair):
        return Quote(pair, bid="1.1000", ask="1.1002", timestamp=datetime.now(timezone.utc))


def test_live_broker_rejects_orders_when_live_flag_is_false() -> None:
    broker = LiveBrokerAdapter(environ={"LIVE_TRADING_ENABLED": "false"})

    with pytest.raises(LiveTradingDisabledError):
        broker.place_order(Order("EUR_USD", side="buy", units=1000, stop_loss="1.0900"))


def test_live_broker_requires_stop_loss_when_flag_true() -> None:
    broker = LiveBrokerAdapter(environ={"LIVE_TRADING_ENABLED": "true"})

    with pytest.raises(ValueError, match="stop_loss"):
        broker.place_order(Order("EUR_USD", side="buy", units=1000))


def test_live_broker_runs_risk_engine_before_any_live_transport() -> None:
    risk_engine = RiskEngine(
        RiskLimits(
            risk_per_trade_pct=Decimal("0.25"),
            max_daily_loss_pct=Decimal("1"),
            max_weekly_loss_pct=Decimal("3"),
            max_drawdown_pct=Decimal("8"),
            max_open_trades=1,
            max_pair_exposure=Decimal("100000"),
            max_total_exposure=Decimal("100000"),
            max_leverage=Decimal("30"),
            max_correlated_usd_exposure=Decimal("100000"),
            max_spread_pips={"EUR_USD": Decimal("0.1")},
            max_slippage_pips=Decimal("1"),
        )
    )
    broker = QuoteLiveBroker(
        environ={"LIVE_TRADING_ENABLED": "true"},
        risk_engine=risk_engine,
        risk_state=RiskState(
            account_equity=Decimal("10000"),
            peak_equity=Decimal("10000"),
            available_margin=Decimal("10000"),
        ),
    )

    with pytest.raises(ValueError, match="risk rejected"):
        broker.place_order(Order("EUR_USD", side="buy", units=1000, stop_loss="1.0900"))
