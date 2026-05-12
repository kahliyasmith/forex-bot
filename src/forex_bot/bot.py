"""Main forex bot loop orchestration."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Iterable

from forex_bot.broker.base import Broker, Order, OrderResult, Position
from forex_bot.broker.demo import DemoBrokerAdapter
from forex_bot.broker.live import LiveBrokerAdapter
from forex_bot.config import BotConfig, BrokerType
from forex_bot.data.models import CurrencyPair, Quote, to_decimal
from forex_bot.monitoring.journal import TradeJournal, make_decision_record
from forex_bot.monitoring.kill_switch import KillSwitch, KillSwitchState
from forex_bot.paper import PaperBroker
from forex_bot.risk.engine import (
    OpenRiskPosition,
    RiskDecision,
    RiskEngine,
    RiskLimits,
    RiskState,
    TradeProposal,
)
from forex_bot.risk.filters import TradingFilters
from forex_bot.strategies.base import Strategy, TradeSignal

LOGGER = logging.getLogger("forex_bot.loop")


@dataclass(frozen=True)
class BotLoopSettings:
    max_quote_age_seconds: int = 60
    default_account_balance: Decimal = Decimal("10000")
    max_pair_exposure_multiplier: Decimal = Decimal("1")
    max_total_exposure_multiplier: Decimal = Decimal("1")
    max_correlated_usd_exposure_multiplier: Decimal = Decimal("1")


@dataclass(frozen=True)
class DecisionResult:
    pair: str
    signal: TradeSignal | None
    filter_status: str
    risk_decision: RiskDecision | None
    order_result: OrderResult | None
    skipped_reason: str | None = None


@dataclass
class MonitoringState:
    decisions: list[DecisionResult] = field(default_factory=list)
    order_reject_count: int = 0
    api_error_count: int = 0
    internal_position_ids: set[str] = field(default_factory=set)
    trading_paused: bool = False
    pause_reasons: list[str] = field(default_factory=list)


class ForexBot:
    def __init__(
        self,
        *,
        config: BotConfig,
        broker: Broker,
        strategy: Strategy,
        risk_engine: RiskEngine,
        trading_filters: TradingFilters,
        journal: TradeJournal | None = None,
        kill_switch: KillSwitch | None = None,
        settings: BotLoopSettings | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.config = config
        self.broker = broker
        self.strategy = strategy
        self.risk_engine = risk_engine
        self.trading_filters = trading_filters
        self.journal = journal
        self.kill_switch = kill_switch
        self.settings = settings or BotLoopSettings()
        self.logger = logger or LOGGER
        self.monitoring_state = MonitoringState()

    def run_once(self, *, now: datetime | None = None) -> list[DecisionResult]:
        current_time = now or datetime.now(timezone.utc)
        account = self.broker.get_account()
        pairs = [CurrencyPair.parse(pair) for pair in self.config.pairs]
        results: list[DecisionResult] = []

        for pair in pairs:
            quote = self.broker.get_quote(pair)
            stale_reason = self._validate_quote_freshness(quote, current_time)
            if stale_reason is not None:
                result = DecisionResult(pair=pair.symbol, signal=None, filter_status="not_run", risk_decision=None, order_result=None, skipped_reason=stale_reason)
                self._record_skip(result, quote, stale_reason)
                results.append(result)
                continue

            kill_decision = self._evaluate_kill_switch(quote, current_time)
            if kill_decision is not None:
                result = DecisionResult(pair=pair.symbol, signal=None, filter_status="not_run", risk_decision=None, order_result=None, skipped_reason="kill_switch")
                self._record_skip(result, quote, ", ".join(kill_decision))
                results.append(result)
                continue

            filter_decision = self.trading_filters.evaluate(quote=quote, at=current_time)
            if not filter_decision.allowed:
                result = DecisionResult(pair=pair.symbol, signal=None, filter_status=filter_decision.reason, risk_decision=None, order_result=None, skipped_reason=filter_decision.reason)
                self._record_skip(result, quote, filter_decision.reason)
                results.append(result)
                continue

            signal = self.strategy.on_tick(quote)
            if signal is None:
                result = DecisionResult(pair=pair.symbol, signal=None, filter_status="allowed", risk_decision=None, order_result=None, skipped_reason="no_signal")
                results.append(result)
                continue

            risk_state = self._risk_state_from_account(account)
            proposal = TradeProposal(
                pair=signal.pair,
                direction=signal.direction,
                entry_price=quote.entry_price(signal.direction),
                stop_loss=signal.proposed_stop_loss,
                requested_units=None,
                quote=quote,
            )
            risk_decision = self.risk_engine.evaluate(proposal, risk_state)
            if not risk_decision.approved:
                result = DecisionResult(pair=pair.symbol, signal=signal, filter_status="allowed", risk_decision=risk_decision, order_result=None, skipped_reason=risk_decision.reason)
                self._record_decision(result, quote)
                results.append(result)
                continue

            order = self._order_from_signal(signal, risk_decision)
            if order.stop_loss is None:
                raise RuntimeError("approved orders must include stop_loss")
            order_result = self.broker.place_order(order)
            if order_result.status == "rejected":
                self.monitoring_state.order_reject_count += 1
            if order_result.position_id is not None:
                self.monitoring_state.internal_position_ids.add(order_result.position_id)

            result = DecisionResult(pair=pair.symbol, signal=signal, filter_status="allowed", risk_decision=risk_decision, order_result=order_result)
            self._record_decision(result, quote)
            results.append(result)

        self.monitoring_state.decisions.extend(results)
        return results

    def _validate_quote_freshness(self, quote: Quote, now: datetime) -> str | None:
        if now - quote.timestamp > timedelta(seconds=self.settings.max_quote_age_seconds):
            return "stale_data_feed"
        return None

    def _evaluate_kill_switch(self, quote: Quote, now: datetime) -> list[str] | None:
        if self.kill_switch is None:
            return None
        account = self.broker.get_account()
        decision = self.kill_switch.evaluate(
            KillSwitchState(
                account_equity=account.equity,
                peak_equity=account.peak_equity or account.equity,
                daily_pnl=account.daily_pnl,
                weekly_pnl=account.weekly_pnl,
                latest_quote=quote,
                broker_positions=self.broker.get_positions(),
                internal_position_ids=self.monitoring_state.internal_position_ids,
                order_reject_count=self.monitoring_state.order_reject_count,
                api_error_count=self.monitoring_state.api_error_count,
                now=now,
            )
        )
        self.monitoring_state.trading_paused = decision.trading_paused
        self.monitoring_state.pause_reasons = decision.reasons
        return decision.reasons if decision.trading_paused else None

    def _risk_state_from_account(self, account) -> RiskState:
        return RiskState(
            account_equity=account.equity,
            peak_equity=account.peak_equity or account.equity,
            available_margin=account.available_margin,
            daily_pnl=account.daily_pnl,
            weekly_pnl=account.weekly_pnl,
            open_positions=tuple(
                OpenRiskPosition(
                    pair=position.pair,
                    direction=position.direction,
                    units=position.units,
                    entry_price=position.entry_price,
                )
                for position in self.broker.get_positions()
            ),
        )

    def _order_from_signal(self, signal: TradeSignal, decision: RiskDecision) -> Order:
        return Order(
            pair=signal.pair,
            side="buy" if signal.direction == "long" else "sell",
            units=decision.calculated_position_size,
            stop_loss=signal.proposed_stop_loss,
            take_profit=signal.proposed_take_profit,
            strategy=self.strategy.__class__.__name__,
            metadata={"entry_reason": signal.entry_reason, "confidence": signal.confidence},
        )

    def _record_skip(self, result: DecisionResult, quote: Quote, reason: str) -> None:
        self.logger.info(
            "trade decision skipped",
            extra={"pair": result.pair, "reason": reason, "bid": str(quote.bid), "ask": str(quote.ask)},
        )
        if self.journal is not None:
            self.journal.record(
                make_decision_record(
                    pair=result.pair,
                    strategy=self.strategy.__class__.__name__,
                    signal=None,
                    bid=quote.bid,
                    ask=quote.ask,
                    spread=quote.spread_pips,
                    session=classify_session(quote.timestamp),
                    news_filter_status=result.filter_status,
                    risk_decision="not_run",
                    position_size=Decimal("0"),
                    order_result="not_sent",
                    stop_loss=None,
                    take_profit=None,
                    rejection_reason=reason,
                    timestamp=quote.timestamp,
                )
            )

    def _record_decision(self, result: DecisionResult, quote: Quote) -> None:
        signal = result.signal
        risk_status = result.risk_decision.reason if result.risk_decision else "not_run"
        order_status = result.order_result.status if result.order_result else "not_sent"
        position_size = (
            result.risk_decision.calculated_position_size if result.risk_decision else Decimal("0")
        )
        self.logger.info(
            "trade decision",
            extra={
                "pair": result.pair,
                "strategy": self.strategy.__class__.__name__,
                "risk_decision": risk_status,
                "order_result": order_status,
            },
        )
        if self.journal is not None:
            self.journal.record(
                make_decision_record(
                    pair=result.pair,
                    strategy=self.strategy.__class__.__name__,
                    signal=signal.direction if signal else None,
                    bid=quote.bid,
                    ask=quote.ask,
                    spread=quote.spread_pips,
                    session=classify_session(quote.timestamp),
                    news_filter_status=result.filter_status,
                    risk_decision=risk_status,
                    position_size=position_size,
                    order_result=order_status,
                    stop_loss=signal.proposed_stop_loss if signal else None,
                    take_profit=signal.proposed_take_profit if signal else None,
                    rejection_reason=result.skipped_reason,
                    timestamp=quote.timestamp,
                )
            )


def classify_session(timestamp: datetime) -> str:
    hour = timestamp.astimezone(timezone.utc).hour
    if 21 <= hour or hour < 6:
        return "asian"
    if 6 <= hour < 12:
        return "london"
    if 12 <= hour < 21:
        return "new_york"
    return "unknown"


def create_broker(config: BotConfig) -> Broker:
    if config.broker.type is BrokerType.DEMO:
        return DemoBrokerAdapter()
    if config.broker.type is BrokerType.LIVE:
        return LiveBrokerAdapter()
    return PaperBroker()


def risk_limits_from_config(config: BotConfig, *, account_equity: Decimal = Decimal("10000")) -> RiskLimits:
    max_leverage = to_decimal(config.risk.max_leverage)
    total_exposure = account_equity * max_leverage
    return RiskLimits(
        risk_per_trade_pct=to_decimal(config.risk.risk_per_trade_pct),
        max_daily_loss_pct=to_decimal(config.risk.max_daily_loss_pct),
        max_weekly_loss_pct=to_decimal(config.risk.max_weekly_loss_pct),
        max_drawdown_pct=to_decimal(config.risk.max_drawdown_pct),
        max_open_trades=config.risk.max_open_trades,
        max_pair_exposure=total_exposure,
        max_total_exposure=total_exposure,
        max_leverage=max_leverage,
        max_correlated_usd_exposure=total_exposure,
        max_spread_pips={pair: to_decimal(value) for pair, value in config.max_spread_pips.items()},
        max_slippage_pips=to_decimal(config.execution.max_slippage_pips),
    )
