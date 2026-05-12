"""Risk engine for approving, rejecting, or resizing proposed trades."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from forex_bot.data.models import CurrencyPair, Quote, floor_units, to_decimal
from forex_bot.risk.position_sizing import calculate_position_size


@dataclass(frozen=True)
class RiskLimits:
    risk_per_trade_pct: Decimal
    max_daily_loss_pct: Decimal
    max_weekly_loss_pct: Decimal
    max_drawdown_pct: Decimal
    max_open_trades: int
    max_pair_exposure: Decimal
    max_total_exposure: Decimal
    max_leverage: Decimal
    max_correlated_usd_exposure: Decimal
    max_spread_pips: dict[str, Decimal]
    max_slippage_pips: Decimal


@dataclass(frozen=True)
class OpenRiskPosition:
    pair: CurrencyPair | str
    direction: str
    units: Decimal
    entry_price: Decimal

    def __post_init__(self) -> None:
        object.__setattr__(self, "pair", CurrencyPair.parse(self.pair))
        object.__setattr__(self, "units", to_decimal(self.units))
        object.__setattr__(self, "entry_price", to_decimal(self.entry_price))

    @property
    def notional_usd(self) -> Decimal:
        return self.pair.notional_usd(self.units, self.entry_price)


@dataclass(frozen=True)
class RiskState:
    account_equity: Decimal
    peak_equity: Decimal
    available_margin: Decimal
    daily_pnl: Decimal = Decimal("0")
    weekly_pnl: Decimal = Decimal("0")
    open_positions: tuple[OpenRiskPosition, ...] = ()
    blocked_session: bool = False
    news_blackout: bool = False


@dataclass(frozen=True)
class TradeProposal:
    pair: CurrencyPair | str
    direction: str
    entry_price: Decimal
    stop_loss: Decimal | None
    requested_units: Decimal | None
    quote: Quote
    expected_slippage_pips: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        object.__setattr__(self, "pair", CurrencyPair.parse(self.pair))
        object.__setattr__(self, "entry_price", to_decimal(self.entry_price))
        if self.stop_loss is not None:
            object.__setattr__(self, "stop_loss", to_decimal(self.stop_loss))
        if self.requested_units is not None:
            object.__setattr__(self, "requested_units", to_decimal(self.requested_units))
        object.__setattr__(self, "expected_slippage_pips", to_decimal(self.expected_slippage_pips))


@dataclass(frozen=True)
class RiskDecision:
    approved: bool
    reason: str
    calculated_position_size: Decimal
    rejected_checks: list[str] = field(default_factory=list)
    risk_amount: Decimal = Decimal("0")
    estimated_loss_if_stop_hit: Decimal = Decimal("0")


class RiskEngine:
    def __init__(self, limits: RiskLimits) -> None:
        self.limits = limits

    def evaluate(self, proposal: TradeProposal, state: RiskState) -> RiskDecision:
        rejected: list[str] = []
        risk_amount = state.account_equity * (self.limits.risk_per_trade_pct / Decimal("100"))
        calculated_units = Decimal("0")
        estimated_loss = Decimal("0")

        if proposal.stop_loss is None:
            rejected.append("stop_loss_required")
        else:
            stop_distance_pips = proposal.pair.pips_between(proposal.entry_price, proposal.stop_loss)
            if stop_distance_pips <= 0:
                rejected.append("risk_per_trade")
            else:
                size = calculate_position_size(
                    account_equity=state.account_equity,
                    risk_per_trade_pct=self.limits.risk_per_trade_pct,
                    stop_distance_pips=stop_distance_pips,
                    pair=proposal.pair,
                    price=proposal.entry_price,
                    max_leverage=self.limits.max_leverage,
                    available_margin=state.available_margin,
                )
                calculated_units = Decimal(size.position_size_units)
                if proposal.requested_units is not None:
                    calculated_units = min(calculated_units, proposal.requested_units)
                if calculated_units <= 0:
                    rejected.append("margin_estimate")
                estimated_loss = self._estimated_stop_loss(proposal, calculated_units)
                if estimated_loss > risk_amount:
                    rejected.append("risk_per_trade")

        if state.daily_pnl <= -(state.account_equity * self.limits.max_daily_loss_pct / Decimal("100")):
            rejected.append("max_daily_loss")
        if state.weekly_pnl <= -(state.account_equity * self.limits.max_weekly_loss_pct / Decimal("100")):
            rejected.append("max_weekly_loss")
        if state.peak_equity > 0:
            drawdown = (state.peak_equity - state.account_equity) / state.peak_equity * Decimal("100")
            if drawdown >= self.limits.max_drawdown_pct:
                rejected.append("max_drawdown")
        if len(state.open_positions) >= self.limits.max_open_trades:
            rejected.append("max_open_trades")

        proposed_notional = proposal.pair.notional_usd(calculated_units, proposal.entry_price)
        pair_exposure = self._pair_exposure(state, proposal.pair) + proposed_notional
        total_exposure = self._total_exposure(state) + proposed_notional
        correlated_usd_exposure = self._correlated_usd_exposure(state) + self._usd_exposure(
            proposal.pair,
            proposed_notional,
        )

        if pair_exposure > self.limits.max_pair_exposure:
            rejected.append("max_pair_exposure")
        if total_exposure > self.limits.max_total_exposure:
            rejected.append("max_total_exposure")
        if state.account_equity > 0 and (total_exposure / state.account_equity) > self.limits.max_leverage:
            rejected.append("max_leverage")

        required_margin = proposed_notional / self.limits.max_leverage if self.limits.max_leverage > 0 else proposed_notional
        if required_margin > state.available_margin:
            rejected.append("margin_estimate")

        if correlated_usd_exposure > self.limits.max_correlated_usd_exposure:
            rejected.append("correlated_usd_exposure")

        max_spread = self.limits.max_spread_pips.get(proposal.pair.symbol)
        if max_spread is not None and proposal.quote.spread_pips > max_spread:
            rejected.append("max_spread")
        if proposal.expected_slippage_pips > self.limits.max_slippage_pips:
            rejected.append("max_slippage")
        if state.blocked_session:
            rejected.append("blocked_session")
        if state.news_blackout:
            rejected.append("news_blackout")

        if rejected:
            return RiskDecision(
                approved=False,
                reason=f"Rejected: {', '.join(rejected)}",
                calculated_position_size=calculated_units,
                rejected_checks=rejected,
                risk_amount=risk_amount,
                estimated_loss_if_stop_hit=estimated_loss,
            )

        if proposal.requested_units is not None and calculated_units < proposal.requested_units:
            reason = "approved_resized"
        else:
            reason = "approved"
        return RiskDecision(
            approved=True,
            reason=reason,
            calculated_position_size=calculated_units,
            risk_amount=risk_amount,
            estimated_loss_if_stop_hit=estimated_loss,
        )

    def _estimated_stop_loss(self, proposal: TradeProposal, units: Decimal) -> Decimal:
        if proposal.stop_loss is None:
            return Decimal("0")
        return abs(
            proposal.pair.pnl_usd(
                proposal.direction, proposal.entry_price, proposal.stop_loss, units
            )
        )

    def _pair_exposure(self, state: RiskState, pair: CurrencyPair) -> Decimal:
        return sum(
            (position.notional_usd for position in state.open_positions if position.pair == pair),
            Decimal("0"),
        )

    def _total_exposure(self, state: RiskState) -> Decimal:
        return sum((position.notional_usd for position in state.open_positions), Decimal("0"))

    def _correlated_usd_exposure(self, state: RiskState) -> Decimal:
        return sum(
            (
                self._usd_exposure(position.pair, position.notional_usd)
                for position in state.open_positions
            ),
            Decimal("0"),
        )

    def _usd_exposure(self, pair: CurrencyPair, notional: Decimal) -> Decimal:
        return notional if "USD" in {pair.base, pair.quote} else Decimal("0")
