"""Text status snapshot for the forex bot."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from forex_bot.broker.base import Broker
from forex_bot.config import BotConfig
from forex_bot.data.models import CurrencyPair


@dataclass(frozen=True)
class StatusSnapshot:
    mode: str
    account_equity: Decimal
    open_positions: int
    daily_pnl: Decimal
    weekly_pnl: Decimal
    current_drawdown_pct: Decimal
    active_kill_switches: list[str]
    latest_spread_per_pair: dict[str, Decimal | None]
    latest_trade_decisions: list[str]
    rejected_signals_count: int


def build_status_snapshot(
    *,
    config: BotConfig,
    broker: Broker,
    monitoring_state=None,
    pairs: Iterable[str] | None = None,
) -> StatusSnapshot:
    account = broker.get_account()
    peak_equity = account.peak_equity or account.equity
    drawdown = (
        ((peak_equity - account.equity) / peak_equity) * Decimal("100")
        if peak_equity
        else Decimal("0")
    )
    requested_pairs = [CurrencyPair.parse(pair).symbol for pair in (pairs or config.pairs)]
    spreads: dict[str, Decimal | None] = {}
    for pair in requested_pairs:
        try:
            spreads[pair] = broker.get_quote(pair).spread_pips
        except Exception:
            spreads[pair] = None

    decisions = list(getattr(monitoring_state, "decisions", []) or [])
    latest_decisions = [_format_decision(decision) for decision in decisions[-5:]]
    rejected_signals = sum(1 for decision in decisions if _decision_rejected(decision))
    active_kill_switches = list(getattr(monitoring_state, "pause_reasons", []) or [])

    return StatusSnapshot(
        mode=config.mode.value,
        account_equity=account.equity,
        open_positions=len(broker.get_positions()),
        daily_pnl=account.daily_pnl,
        weekly_pnl=account.weekly_pnl,
        current_drawdown_pct=drawdown,
        active_kill_switches=active_kill_switches,
        latest_spread_per_pair=spreads,
        latest_trade_decisions=latest_decisions,
        rejected_signals_count=rejected_signals,
    )


def render_status(snapshot: StatusSnapshot) -> str:
    lines = [
        f"Mode: {snapshot.mode}",
        f"Account equity: {snapshot.account_equity}",
        f"Open positions: {snapshot.open_positions}",
        f"Daily P&L: {snapshot.daily_pnl}",
        f"Weekly P&L: {snapshot.weekly_pnl}",
        f"Current drawdown: {snapshot.current_drawdown_pct:.2f}%",
        "Active kill switches: "
        + (", ".join(snapshot.active_kill_switches) if snapshot.active_kill_switches else "none"),
        "Latest spread per pair:",
    ]
    for pair, spread in snapshot.latest_spread_per_pair.items():
        lines.append(f"  {pair}: {spread if spread is not None else 'n/a'}")
    lines.append("Latest trade decisions:")
    if snapshot.latest_trade_decisions:
        lines.extend(f"  {decision}" for decision in snapshot.latest_trade_decisions)
    else:
        lines.append("  none")
    lines.append(f"Rejected signals count: {snapshot.rejected_signals_count}")
    return "\n".join(lines)


def _format_decision(decision) -> str:
    order_status = decision.order_result.status if decision.order_result else "not_sent"
    risk_status = decision.risk_decision.reason if decision.risk_decision else "not_run"
    skipped = f", skipped={decision.skipped_reason}" if decision.skipped_reason else ""
    return f"{decision.pair}: risk={risk_status}, order={order_status}{skipped}"


def _decision_rejected(decision) -> bool:
    if decision.risk_decision is not None and not decision.risk_decision.approved:
        return True
    return decision.skipped_reason not in {None, "no_signal"}
