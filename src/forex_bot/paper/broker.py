"""Paper broker that simulates forex fills, positions, and P&L."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from itertools import count

from forex_bot.broker.base import Account, Broker, Order, OrderResult, Position, TradeHistoryRecord
from forex_bot.data.models import CurrencyPair, Quote, to_decimal


class PaperBroker(Broker):
    def __init__(
        self,
        *,
        starting_balance: Decimal | float | int | str = Decimal("10000"),
        max_leverage: Decimal | float | int | str = Decimal("30"),
        slippage_pips: Decimal | float | int | str = Decimal("0"),
    ) -> None:
        self.balance = to_decimal(starting_balance)
        self.realized_pnl = Decimal("0")
        self.max_leverage = to_decimal(max_leverage)
        self.slippage_pips = to_decimal(slippage_pips)
        self.quotes: dict[str, Quote] = {}
        self.positions: dict[str, Position] = {}
        self.pending_orders: dict[str, Order] = {}
        self.trade_history: list[TradeHistoryRecord] = []
        self._ids = count(1)
        self._peak_equity = self.balance

    def update_quote(self, quote: Quote) -> None:
        self.quotes[quote.pair.symbol] = quote
        self._update_unrealized_pnl(quote.pair)
        self._process_pending_orders(quote)
        self._process_position_exits(quote)

    def get_quote(self, pair: CurrencyPair | str) -> Quote:
        parsed_pair = CurrencyPair.parse(pair)
        try:
            return self.quotes[parsed_pair.symbol]
        except KeyError as exc:
            raise KeyError(f"no quote available for {parsed_pair.symbol}") from exc

    def get_account(self) -> Account:
        unrealized = sum((position.unrealized_pnl for position in self.positions.values()), Decimal("0"))
        equity = self.balance + unrealized
        self._peak_equity = max(self._peak_equity, equity)
        used_margin = sum(
            (
                position.pair.notional_usd(position.units, position.entry_price) / self.max_leverage
                for position in self.positions.values()
            ),
            Decimal("0"),
        )
        return Account(
            balance=self.balance,
            equity=equity,
            available_margin=max(equity - used_margin, Decimal("0")),
            used_margin=used_margin,
            realized_pnl=self.realized_pnl,
            unrealized_pnl=unrealized,
            daily_pnl=self.realized_pnl,
            weekly_pnl=self.realized_pnl,
            peak_equity=self._peak_equity,
        )

    def place_order(self, order: Order) -> OrderResult:
        if order.stop_loss is None:
            return OrderResult(
                order_id=self._next_id("order"),
                status="rejected",
                reason="stop_loss_required",
            )
        if order.order_type != "market":
            order_id = self._next_id("order")
            self.pending_orders[order_id] = order
            return OrderResult(order_id=order_id, status="pending", reason="pending")
        return self._fill_market_order(order)

    def close_position(self, position_id: str) -> OrderResult:
        position = self.positions.get(position_id)
        if position is None:
            return OrderResult(
                order_id=self._next_id("close"),
                status="rejected",
                reason="position_not_found",
                position_id=position_id,
            )
        quote = self.get_quote(position.pair)
        return self._close_position(position, quote, "manual_close")

    def get_positions(self) -> list[Position]:
        return list(self.positions.values())

    def get_pending_orders(self) -> list[Order]:
        return list(self.pending_orders.values())

    def get_trade_history(self) -> list[TradeHistoryRecord]:
        return list(self.trade_history)

    def _fill_market_order(self, order: Order) -> OrderResult:
        quote = self.get_quote(order.pair)
        fill_price = quote.entry_price(order.direction, self.slippage_pips)
        position_id = self._next_id("pos")
        position = Position(
            id=position_id,
            pair=order.pair,
            direction=order.direction,
            units=order.units,
            entry_price=fill_price,
            opened_at=quote.timestamp,
            stop_loss=order.stop_loss,
            take_profit=order.take_profit,
            strategy=order.strategy,
        )
        self.positions[position_id] = position
        return OrderResult(
            order_id=self._next_id("order"),
            status="filled",
            reason="filled",
            position_id=position_id,
            fill_price=fill_price,
            filled_units=order.units,
            spread_pips=quote.spread_pips,
            slippage_pips=self.slippage_pips,
            timestamp=quote.timestamp,
        )

    def _close_position(self, position: Position, quote: Quote, reason: str) -> OrderResult:
        exit_price = quote.exit_price(position.direction, self.slippage_pips)
        pnl = position.pair.pnl_usd(position.direction, position.entry_price, exit_price, position.units)
        self.balance += pnl
        self.realized_pnl += pnl
        self.positions.pop(position.id, None)
        self.trade_history.append(
            TradeHistoryRecord(
                pair=position.pair,
                direction=position.direction,
                units=position.units,
                entry_price=position.entry_price,
                exit_price=exit_price,
                opened_at=position.opened_at,
                closed_at=quote.timestamp,
                reason=reason,
                realized_pnl=pnl,
                spread_pips=quote.spread_pips,
                slippage_pips=self.slippage_pips,
                strategy=position.strategy,
            )
        )
        return OrderResult(
            order_id=self._next_id("close"),
            status="closed",
            reason=reason,
            position_id=position.id,
            fill_price=exit_price,
            filled_units=position.units,
            spread_pips=quote.spread_pips,
            slippage_pips=self.slippage_pips,
            timestamp=quote.timestamp,
        )

    def _process_pending_orders(self, quote: Quote) -> None:
        filled: list[str] = []
        for order_id, order in self.pending_orders.items():
            if order.pair != quote.pair or order.limit_price is None:
                continue
            should_fill = (
                order.side == "buy"
                and quote.ask <= order.limit_price
                or order.side == "sell"
                and quote.bid >= order.limit_price
            )
            if should_fill:
                self._fill_market_order(order)
                filled.append(order_id)
        for order_id in filled:
            self.pending_orders.pop(order_id, None)

    def _process_position_exits(self, quote: Quote) -> None:
        for position in list(self.positions.values()):
            if position.pair != quote.pair:
                continue
            if position.direction == "long":
                if position.stop_loss is not None and quote.bid <= position.stop_loss:
                    self._close_position(position, quote, "stop_loss")
                elif position.take_profit is not None and quote.bid >= position.take_profit:
                    self._close_position(position, quote, "take_profit")
            else:
                if position.stop_loss is not None and quote.ask >= position.stop_loss:
                    self._close_position(position, quote, "stop_loss")
                elif position.take_profit is not None and quote.ask <= position.take_profit:
                    self._close_position(position, quote, "take_profit")

    def _update_unrealized_pnl(self, pair: CurrencyPair) -> None:
        quote = self.get_quote(pair)
        for position in list(self.positions.values()):
            if position.pair != pair:
                continue
            exit_price = quote.exit_price(position.direction)
            pnl = position.pair.pnl_usd(position.direction, position.entry_price, exit_price, position.units)
            self.positions[position.id] = replace(position, unrealized_pnl=pnl)

    def _next_id(self, prefix: str) -> str:
        return f"{prefix}-{next(self._ids)}"
