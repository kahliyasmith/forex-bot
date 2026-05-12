from datetime import datetime, timedelta, timezone
from decimal import Decimal

from forex_bot.backtest import BacktestConfig, BacktestEngine
from forex_bot.data import Quote
from forex_bot.strategies.base import Strategy, TradeSignal


class OneSignalStrategy(Strategy):
    def __init__(self, signal: TradeSignal) -> None:
        self.signal = signal
        self.sent = False

    def required_timeframes(self) -> tuple[str, ...]:
        return ("tick",)

    def generate_signal(self, event):
        if self.sent:
            return None
        self.sent = True
        return self.signal


def test_long_entry_at_ask_exit_at_bid_take_profit() -> None:
    start = datetime(2026, 1, 5, 14, tzinfo=timezone.utc)
    quotes = [
        Quote("EUR_USD", bid="1.1000", ask="1.1002", timestamp=start),
        Quote("EUR_USD", bid="1.1012", ask="1.1014", timestamp=start + timedelta(minutes=1)),
    ]
    signal = TradeSignal(
        pair="EUR_USD",
        direction="long",
        confidence=0.8,
        entry_reason="test",
        proposed_stop_loss="1.0990",
        proposed_take_profit="1.1010",
    )

    result = BacktestEngine(BacktestConfig(units=Decimal("10000"))).run(
        quotes, OneSignalStrategy(signal)
    )

    trade = result.trades[0]
    assert trade.entry_price == Decimal("1.1002")
    assert trade.exit_price == Decimal("1.1012")
    assert trade.exit_reason == "take_profit"
    assert trade.net_pnl == Decimal("10.0000")
    assert result.metrics.win_rate == Decimal("1")


def test_short_entry_at_bid_exit_at_ask_take_profit() -> None:
    start = datetime(2026, 1, 5, 14, tzinfo=timezone.utc)
    quotes = [
        Quote("GBP_USD", bid="1.2500", ask="1.2502", timestamp=start),
        Quote("GBP_USD", bid="1.2488", ask="1.2490", timestamp=start + timedelta(minutes=1)),
    ]
    signal = TradeSignal(
        pair="GBP_USD",
        direction="short",
        confidence=0.8,
        entry_reason="test",
        proposed_stop_loss="1.2510",
        proposed_take_profit="1.2490",
    )

    result = BacktestEngine(BacktestConfig(units=Decimal("10000"))).run(
        quotes, OneSignalStrategy(signal)
    )

    trade = result.trades[0]
    assert trade.entry_price == Decimal("1.2500")
    assert trade.exit_price == Decimal("1.2490")
    assert trade.exit_reason == "take_profit"
    assert trade.net_pnl == Decimal("10.0000")


def test_commission_slippage_and_swap_reduce_pnl() -> None:
    start = datetime(2026, 1, 5, 14, tzinfo=timezone.utc)
    quotes = [
        Quote("EUR_USD", bid="1.1000", ask="1.1002", timestamp=start),
        Quote("EUR_USD", bid="1.1012", ask="1.1014", timestamp=start + timedelta(minutes=1)),
    ]
    signal = TradeSignal(
        pair="EUR_USD",
        direction="long",
        confidence=0.8,
        entry_reason="test",
        proposed_stop_loss="1.0990",
        proposed_take_profit="1.1010",
    )

    result = BacktestEngine(
        BacktestConfig(
            units=Decimal("10000"),
            slippage_pips=Decimal("1"),
            commission_per_trade=Decimal("1"),
            swap_cost_per_trade=Decimal("0.5"),
        )
    ).run(quotes, OneSignalStrategy(signal))

    trade = result.trades[0]
    assert trade.entry_price == Decimal("1.1003")
    assert trade.exit_price == Decimal("1.1011")
    assert trade.net_pnl == Decimal("5.5000")
