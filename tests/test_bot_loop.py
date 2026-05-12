from datetime import datetime, timezone
from decimal import Decimal

from forex_bot.bot import ForexBot, risk_limits_from_config
from forex_bot.config import BotConfig
from forex_bot.data import Quote
from forex_bot.monitoring.journal import TradeJournal
from forex_bot.paper import PaperBroker
from forex_bot.risk.engine import RiskEngine
from forex_bot.risk.filters import TradingFilterConfig, TradingFilters
from forex_bot.strategies.base import Strategy, TradeSignal


class StaticSignalStrategy(Strategy):
    def __init__(self, signal: TradeSignal | None) -> None:
        self.signal = signal

    def required_timeframes(self) -> tuple[str, ...]:
        return ("tick",)

    def generate_signal(self, event):
        return self.signal


def bot_config() -> BotConfig:
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


def test_bot_loop_routes_signal_through_risk_to_paper_order(tmp_path) -> None:
    config = bot_config()
    now = datetime(2026, 1, 5, 14, tzinfo=timezone.utc)
    broker = PaperBroker()
    broker.update_quote(Quote("EUR_USD", bid="1.1000", ask="1.1002", timestamp=now))
    strategy = StaticSignalStrategy(
        TradeSignal(
            pair="EUR_USD",
            direction="long",
            confidence=0.8,
            entry_reason="test",
            proposed_stop_loss="1.0977",
            proposed_take_profit="1.1050",
        )
    )
    journal = TradeJournal(tmp_path / "journal.jsonl", tmp_path / "journal.csv")
    bot = ForexBot(
        config=config,
        broker=broker,
        strategy=strategy,
        risk_engine=RiskEngine(risk_limits_from_config(config)),
        trading_filters=TradingFilters(TradingFilterConfig(max_spread_pips={"EUR_USD": Decimal("2")})),
        journal=journal,
    )

    results = bot.run_once(now=now)

    assert results[0].order_result is not None
    assert results[0].order_result.status == "filled"
    assert broker.get_positions()[0].stop_loss == Decimal("1.0977")
    assert "filled" in (tmp_path / "journal.csv").read_text(encoding="utf-8")


def test_bot_loop_skips_stale_data() -> None:
    config = bot_config()
    now = datetime(2026, 1, 5, 14, tzinfo=timezone.utc)
    broker = PaperBroker()
    broker.update_quote(Quote("EUR_USD", bid="1.1000", ask="1.1002", timestamp=datetime(2026, 1, 5, 13, 58, tzinfo=timezone.utc)))
    bot = ForexBot(
        config=config,
        broker=broker,
        strategy=StaticSignalStrategy(None),
        risk_engine=RiskEngine(risk_limits_from_config(config)),
        trading_filters=TradingFilters(TradingFilterConfig(max_spread_pips={"EUR_USD": Decimal("2")})),
    )

    results = bot.run_once(now=now)

    assert results[0].skipped_reason == "stale_data_feed"
