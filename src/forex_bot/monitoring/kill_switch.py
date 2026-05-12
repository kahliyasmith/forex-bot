"""Kill switches that pause trading under unsafe conditions."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from forex_bot.broker.base import Position
from forex_bot.data.models import Quote


@dataclass(frozen=True)
class KillSwitchConfig:
    max_daily_loss_pct: Decimal
    max_weekly_loss_pct: Decimal
    max_drawdown_pct: Decimal
    max_spread_pips: Decimal
    max_slippage_pips: Decimal
    max_data_age_seconds: int = 60
    max_order_rejects: int = 3
    max_api_errors: int = 3


@dataclass(frozen=True)
class KillSwitchState:
    account_equity: Decimal
    peak_equity: Decimal
    daily_pnl: Decimal = Decimal("0")
    weekly_pnl: Decimal = Decimal("0")
    latest_quote: Quote | None = None
    observed_slippage_pips: Decimal = Decimal("0")
    broker_positions: list[Position] = field(default_factory=list)
    internal_position_ids: set[str] = field(default_factory=set)
    order_reject_count: int = 0
    api_error_count: int = 0
    now: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class KillSwitchDecision:
    trading_paused: bool
    reasons: list[str]


class KillSwitch:
    def __init__(self, config: KillSwitchConfig) -> None:
        self.config = config

    def evaluate(self, state: KillSwitchState) -> KillSwitchDecision:
        reasons: list[str] = []
        equity = state.account_equity
        if state.daily_pnl <= -(equity * self.config.max_daily_loss_pct / Decimal("100")):
            reasons.append("daily_loss_exceeded")
        if state.weekly_pnl <= -(equity * self.config.max_weekly_loss_pct / Decimal("100")):
            reasons.append("weekly_loss_exceeded")
        if state.peak_equity > 0:
            drawdown_pct = (state.peak_equity - equity) / state.peak_equity * Decimal("100")
            if drawdown_pct >= self.config.max_drawdown_pct:
                reasons.append("drawdown_exceeded")
        if state.latest_quote is not None:
            if state.latest_quote.spread_pips > self.config.max_spread_pips:
                reasons.append("abnormal_spread")
            if state.now - state.latest_quote.timestamp > timedelta(seconds=self.config.max_data_age_seconds):
                reasons.append("stale_data_feed")
        if state.observed_slippage_pips > self.config.max_slippage_pips:
            reasons.append("abnormal_slippage")
        broker_ids = {position.id for position in state.broker_positions}
        if broker_ids != state.internal_position_ids:
            reasons.append("position_mismatch")
        if any(position.stop_loss is None for position in state.broker_positions):
            reasons.append("missing_stop_loss")
        if state.order_reject_count >= self.config.max_order_rejects:
            reasons.append("too_many_order_rejects")
        if state.api_error_count >= self.config.max_api_errors:
            reasons.append("too_many_api_errors")
        return KillSwitchDecision(trading_paused=bool(reasons), reasons=reasons)
