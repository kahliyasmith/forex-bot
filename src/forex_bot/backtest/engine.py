"""Event-driven, bid/ask-aware forex backtesting engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from math import sqrt
from statistics import mean, pstdev
from typing import Iterable

from forex_bot.data.models import Candle, CurrencyPair, Quote, to_decimal
from forex_bot.strategies.base import Strategy, TradeSignal


@dataclass(frozen=True)
class BacktestConfig:
    initial_balance: Decimal = Decimal("10000")
    units: Decimal = Decimal("10000")
    commission_per_trade: Decimal = Decimal("0")
    slippage_pips: Decimal = Decimal("0")
    swap_cost_per_trade: Decimal = Decimal("0")


@dataclass(frozen=True)
class Position:
    pair: CurrencyPair
    direction: str
    units: Decimal
    entry_price: Decimal
    stop_loss: Decimal
    take_profit: Decimal
    opened_at: object
    entry_reason: str


@dataclass(frozen=True)
class Trade:
    pair: CurrencyPair
    direction: str
    units: Decimal
    entry_price: Decimal
    exit_price: Decimal
    opened_at: object
    closed_at: object
    exit_reason: str
    gross_pnl: Decimal
    commission: Decimal
    swap: Decimal
    net_pnl: Decimal


@dataclass(frozen=True)
class BacktestMetrics:
    total_return: Decimal
    max_drawdown: Decimal
    win_rate: Decimal
    profit_factor: Decimal
    average_win: Decimal
    average_loss: Decimal
    expectancy: Decimal
    sharpe_like_ratio: Decimal


@dataclass(frozen=True)
class BacktestResult:
    trades: list[Trade]
    metrics: BacktestMetrics
    equity_curve: list[Decimal] = field(default_factory=list)


class BacktestEngine:
    def __init__(self, config: BacktestConfig | None = None) -> None:
        self.config = config or BacktestConfig()

    def run(self, quotes: Iterable[Quote], strategy: Strategy) -> BacktestResult:
        position: Position | None = None
        trades: list[Trade] = []
        equity = self.config.initial_balance
        equity_curve = [equity]

        for quote in quotes:
            if position is not None:
                maybe_trade = self._maybe_exit(position, quote)
                if maybe_trade is not None:
                    trades.append(maybe_trade)
                    equity += maybe_trade.net_pnl
                    equity_curve.append(equity)
                    position = None
                    continue

            if position is None:
                signal = strategy.on_tick(quote)
                if signal is not None:
                    position = self._open_position(signal, quote)

        if position is not None:
            last_quote = quote
            trade = self._close_position(position, last_quote, "end_of_data")
            trades.append(trade)
            equity += trade.net_pnl
            equity_curve.append(equity)

        return BacktestResult(
            trades=trades,
            metrics=self._calculate_metrics(trades, equity_curve),
            equity_curve=equity_curve,
        )

    def run_candles(
        self,
        candles: Iterable[Candle],
        strategy: Strategy,
        *,
        spread_pips: Decimal = Decimal("1"),
    ) -> BacktestResult:
        position: Position | None = None
        trades: list[Trade] = []
        equity = self.config.initial_balance
        equity_curve = [equity]

        for candle in candles:
            quote = Quote.from_mid(candle.pair, candle.close, spread_pips, candle.timestamp)
            if position is not None:
                maybe_trade = self._maybe_exit(position, quote)
                if maybe_trade is not None:
                    trades.append(maybe_trade)
                    equity += maybe_trade.net_pnl
                    equity_curve.append(equity)
                    position = None
                    continue

            if position is None:
                signal = strategy.on_candle(candle)  # type: ignore[call-arg]
                if signal is not None:
                    position = self._open_position(signal, quote)

        if position is not None:
            trade = self._close_position(position, quote, "end_of_data")
            trades.append(trade)
            equity += trade.net_pnl
            equity_curve.append(equity)

        return BacktestResult(
            trades=trades,
            metrics=self._calculate_metrics(trades, equity_curve),
            equity_curve=equity_curve,
        )

    def _open_position(self, signal: TradeSignal, quote: Quote) -> Position:
        slippage = self.config.slippage_pips
        entry_price = quote.entry_price(signal.direction, slippage)
        return Position(
            pair=signal.pair,
            direction=signal.direction,
            units=self.config.units,
            entry_price=entry_price,
            stop_loss=signal.proposed_stop_loss,
            take_profit=signal.proposed_take_profit,
            opened_at=quote.timestamp,
            entry_reason=signal.entry_reason,
        )

    def _maybe_exit(self, position: Position, quote: Quote) -> Trade | None:
        if position.direction == "long":
            if quote.bid <= position.stop_loss:
                return self._close_position(position, quote, "stop_loss")
            if quote.bid >= position.take_profit:
                return self._close_position(position, quote, "take_profit")
        else:
            if quote.ask >= position.stop_loss:
                return self._close_position(position, quote, "stop_loss")
            if quote.ask <= position.take_profit:
                return self._close_position(position, quote, "take_profit")
        return None

    def _close_position(self, position: Position, quote: Quote, exit_reason: str) -> Trade:
        exit_price = quote.exit_price(position.direction, self.config.slippage_pips)
        gross_pnl = position.pair.pnl_usd(
            position.direction,
            position.entry_price,
            exit_price,
            position.units,
        )
        commission = self.config.commission_per_trade * Decimal("2")
        swap = self.config.swap_cost_per_trade
        net_pnl = gross_pnl - commission - swap
        return Trade(
            pair=position.pair,
            direction=position.direction,
            units=position.units,
            entry_price=position.entry_price,
            exit_price=exit_price,
            opened_at=position.opened_at,
            closed_at=quote.timestamp,
            exit_reason=exit_reason,
            gross_pnl=gross_pnl,
            commission=commission,
            swap=swap,
            net_pnl=net_pnl,
        )

    def _calculate_metrics(self, trades: list[Trade], equity_curve: list[Decimal]) -> BacktestMetrics:
        final_equity = equity_curve[-1]
        total_return = (final_equity - self.config.initial_balance) / self.config.initial_balance
        wins = [trade.net_pnl for trade in trades if trade.net_pnl > 0]
        losses = [trade.net_pnl for trade in trades if trade.net_pnl < 0]
        gross_profit = sum(wins, Decimal("0"))
        gross_loss = abs(sum(losses, Decimal("0")))
        pnl_values = [trade.net_pnl for trade in trades]
        returns = [float(pnl / self.config.initial_balance) for pnl in pnl_values]

        if gross_loss == 0:
            profit_factor = Decimal("Infinity") if gross_profit > 0 else Decimal("0")
        else:
            profit_factor = gross_profit / gross_loss

        sharpe_like = Decimal("0")
        if len(returns) > 1 and pstdev(returns) > 0:
            sharpe_like = Decimal(str((mean(returns) / pstdev(returns)) * sqrt(len(returns))))

        return BacktestMetrics(
            total_return=total_return,
            max_drawdown=self._max_drawdown(equity_curve),
            win_rate=Decimal(len(wins)) / Decimal(len(trades)) if trades else Decimal("0"),
            profit_factor=profit_factor,
            average_win=(gross_profit / Decimal(len(wins))) if wins else Decimal("0"),
            average_loss=(sum(losses, Decimal("0")) / Decimal(len(losses))) if losses else Decimal("0"),
            expectancy=(sum(pnl_values, Decimal("0")) / Decimal(len(pnl_values))) if pnl_values else Decimal("0"),
            sharpe_like_ratio=sharpe_like,
        )

    def _max_drawdown(self, equity_curve: list[Decimal]) -> Decimal:
        peak = equity_curve[0]
        max_drawdown = Decimal("0")
        for equity in equity_curve:
            if equity > peak:
                peak = equity
            if peak > 0:
                drawdown = (peak - equity) / peak
                max_drawdown = max(max_drawdown, drawdown)
        return max_drawdown
