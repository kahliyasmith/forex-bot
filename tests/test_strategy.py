from datetime import datetime, timedelta, timezone

from forex_bot.backtest import BacktestConfig, BacktestEngine
from forex_bot.data import Candle, Quote
from forex_bot.risk.filters import TradingFilterConfig, TradingFilters
from forex_bot.strategies import TrendPullbackParameters, TrendPullbackStrategy


def candles() -> list[Candle]:
    start = datetime(2026, 1, 5, 14, tzinfo=timezone.utc)
    values = [
        ("1.1000", "1.1010", "1.0990", "1.1000"),
        ("1.1000", "1.1020", "1.1000", "1.1010"),
        ("1.1010", "1.1030", "1.1010", "1.1020"),
        ("1.1020", "1.1040", "1.1020", "1.1030"),
        ("1.1030", "1.1035", "1.1015", "1.1020"),
        ("1.1020", "1.1050", "1.1020", "1.1045"),
        ("1.1045", "1.1080", "1.1040", "1.1070"),
    ]
    return [
        Candle("EUR_USD", open=o, high=h, low=l, close=c, volume=1000, timestamp=start + timedelta(hours=i))
        for i, (o, h, l, c) in enumerate(values)
    ]


def test_trend_pullback_generates_long_signal() -> None:
    strategy = TrendPullbackStrategy(
        TrendPullbackParameters(
            allowed_pairs=["EUR_USD"],
            trend_ma_period=3,
            atr_period=2,
            pullback_lookback=2,
        )
    )

    signal = None
    for candle in candles()[:-1]:
        signal = strategy.on_candle(candle)

    assert signal is not None
    assert signal.direction == "long"
    assert signal.pair.symbol == "EUR_USD"
    assert signal.proposed_stop_loss < candles()[-2].close
    assert signal.proposed_take_profit > candles()[-2].close


def test_trend_pullback_respects_filters() -> None:
    strategy = TrendPullbackStrategy(
        TrendPullbackParameters(
            allowed_pairs=["EUR_USD"],
            trend_ma_period=3,
            atr_period=2,
            pullback_lookback=2,
        ),
        trading_filters=TradingFilters(TradingFilterConfig(max_spread_pips={"EUR_USD": 0.5})),
    )

    signal = None
    for candle in candles()[:-1]:
        quote = Quote.from_mid("EUR_USD", candle.close, 2, candle.timestamp)
        signal = strategy.on_candle(candle, quote)

    assert signal is None


def test_trend_pullback_backtest_integration() -> None:
    strategy = TrendPullbackStrategy(
        TrendPullbackParameters(
            allowed_pairs=["EUR_USD"],
            trend_ma_period=3,
            atr_period=2,
            pullback_lookback=2,
        )
    )

    result = BacktestEngine(BacktestConfig(units=10000)).run_candles(candles(), strategy)

    assert len(result.trades) == 1
    assert result.trades[0].direction == "long"
