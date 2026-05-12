"""Performance reporting and exports."""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from statistics import mean, pstdev
from typing import Iterable

from forex_bot.backtest.engine import BacktestResult, Trade
from forex_bot.broker.base import TradeHistoryRecord
from forex_bot.data.models import CurrencyPair, to_decimal


def decimal_to_json(value: object) -> object:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, CurrencyPair):
        return value.symbol
    if isinstance(value, dict):
        return {key: decimal_to_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [decimal_to_json(item) for item in value]
    return value


@dataclass(frozen=True)
class ReportTrade:
    pair: str
    strategy: str
    session: str
    opened_at: datetime
    closed_at: datetime
    pnl: Decimal
    spread_pips: Decimal = Decimal("0")
    slippage_pips: Decimal = Decimal("0")
    news_window: bool = False
    rollover_exposure: bool = False

    @classmethod
    def from_backtest_trade(cls, trade: Trade) -> "ReportTrade":
        return cls(
            pair=trade.pair.symbol,
            strategy=getattr(trade, "strategy", "unknown"),
            session="unknown",
            opened_at=trade.opened_at,
            closed_at=trade.closed_at,
            pnl=trade.net_pnl,
        )

    @classmethod
    def from_history_record(cls, trade: TradeHistoryRecord) -> "ReportTrade":
        return cls(
            pair=trade.pair.symbol,
            strategy=trade.strategy,
            session=trade.session,
            opened_at=trade.opened_at,
            closed_at=trade.closed_at,
            pnl=trade.realized_pnl,
            spread_pips=trade.spread_pips,
            slippage_pips=trade.slippage_pips,
            news_window=trade.news_window,
            rollover_exposure=trade.rollover_exposure,
        )


@dataclass(frozen=True)
class PerformanceReport:
    equity_curve: list[Decimal]
    trades: list[ReportTrade]
    total_return: Decimal
    max_drawdown: Decimal
    win_rate: Decimal
    profit_factor: Decimal
    expectancy: Decimal
    average_trade: Decimal
    average_win: Decimal
    average_loss: Decimal
    average_slippage: Decimal
    average_spread_paid: Decimal
    performance_by_pair: dict[str, dict[str, Decimal]]
    performance_by_session: dict[str, dict[str, Decimal]]
    performance_by_strategy: dict[str, dict[str, Decimal]]
    news_window_losses: Decimal
    rollover_exposure: Decimal
    sharpe_like_ratio: Decimal

    def to_dict(self) -> dict[str, object]:
        return decimal_to_json(asdict(self))  # type: ignore[return-value]

    def export_json(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True), encoding="utf-8")

    def export_csv(self, directory: str | Path) -> None:
        output_dir = Path(directory)
        output_dir.mkdir(parents=True, exist_ok=True)
        self._write_csv(output_dir / "equity_curve.csv", [{"index": i, "equity": value} for i, value in enumerate(self.equity_curve)])
        self._write_csv(output_dir / "trades.csv", [decimal_to_json(asdict(trade)) for trade in self.trades])
        self._write_csv(output_dir / "summary.csv", [self._summary_row()])
        self._write_group_csv(output_dir / "performance_by_pair.csv", self.performance_by_pair, "pair")
        self._write_group_csv(output_dir / "performance_by_session.csv", self.performance_by_session, "session")
        self._write_group_csv(output_dir / "performance_by_strategy.csv", self.performance_by_strategy, "strategy")

    def _summary_row(self) -> dict[str, object]:
        return {
            "total_return": self.total_return,
            "max_drawdown": self.max_drawdown,
            "win_rate": self.win_rate,
            "profit_factor": self.profit_factor,
            "expectancy": self.expectancy,
            "average_trade": self.average_trade,
            "average_win": self.average_win,
            "average_loss": self.average_loss,
            "average_slippage": self.average_slippage,
            "average_spread_paid": self.average_spread_paid,
            "news_window_losses": self.news_window_losses,
            "rollover_exposure": self.rollover_exposure,
            "sharpe_like_ratio": self.sharpe_like_ratio,
        }

    def _write_group_csv(self, path: Path, groups: dict[str, dict[str, Decimal]], label: str) -> None:
        rows = [{label: key, **values} for key, values in groups.items()]
        self._write_csv(path, rows)

    def _write_csv(self, path: Path, rows: list[dict[str, object]]) -> None:
        if not rows:
            path.write_text("", encoding="utf-8")
            return
        normalized = [decimal_to_json(row) for row in rows]
        with path.open("w", newline="", encoding="utf-8") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=list(normalized[0].keys()))
            writer.writeheader()
            writer.writerows(normalized)


def build_performance_report(
    *,
    equity_curve: Iterable[Decimal | float | int | str],
    trades: Iterable[ReportTrade | Trade | TradeHistoryRecord],
) -> PerformanceReport:
    equity = [to_decimal(value) for value in equity_curve]
    report_trades = [_coerce_trade(trade) for trade in trades]
    initial_equity = equity[0] if equity else Decimal("0")
    final_equity = equity[-1] if equity else initial_equity
    pnls = [trade.pnl for trade in report_trades]
    wins = [pnl for pnl in pnls if pnl > 0]
    losses = [pnl for pnl in pnls if pnl < 0]
    gross_profit = sum(wins, Decimal("0"))
    gross_loss = abs(sum(losses, Decimal("0")))

    return PerformanceReport(
        equity_curve=equity,
        trades=report_trades,
        total_return=((final_equity - initial_equity) / initial_equity) if initial_equity else Decimal("0"),
        max_drawdown=_max_drawdown(equity),
        win_rate=(Decimal(len(wins)) / Decimal(len(report_trades))) if report_trades else Decimal("0"),
        profit_factor=(gross_profit / gross_loss) if gross_loss else (Decimal("Infinity") if gross_profit else Decimal("0")),
        expectancy=(sum(pnls, Decimal("0")) / Decimal(len(pnls))) if pnls else Decimal("0"),
        average_trade=(sum(pnls, Decimal("0")) / Decimal(len(pnls))) if pnls else Decimal("0"),
        average_win=(gross_profit / Decimal(len(wins))) if wins else Decimal("0"),
        average_loss=(sum(losses, Decimal("0")) / Decimal(len(losses))) if losses else Decimal("0"),
        average_slippage=_average([trade.slippage_pips for trade in report_trades]),
        average_spread_paid=_average([trade.spread_pips for trade in report_trades]),
        performance_by_pair=_group_performance(report_trades, "pair"),
        performance_by_session=_group_performance(report_trades, "session"),
        performance_by_strategy=_group_performance(report_trades, "strategy"),
        news_window_losses=sum((trade.pnl for trade in report_trades if trade.news_window and trade.pnl < 0), Decimal("0")),
        rollover_exposure=sum((abs(trade.pnl) for trade in report_trades if trade.rollover_exposure), Decimal("0")),
        sharpe_like_ratio=_sharpe_like(pnls, initial_equity),
    )


def build_report_from_backtest(result: BacktestResult) -> PerformanceReport:
    return build_performance_report(equity_curve=result.equity_curve, trades=result.trades)


def _coerce_trade(trade: ReportTrade | Trade | TradeHistoryRecord) -> ReportTrade:
    if isinstance(trade, ReportTrade):
        return trade
    if isinstance(trade, TradeHistoryRecord):
        return ReportTrade.from_history_record(trade)
    return ReportTrade.from_backtest_trade(trade)


def _average(values: list[Decimal]) -> Decimal:
    return sum(values, Decimal("0")) / Decimal(len(values)) if values else Decimal("0")


def _group_performance(trades: list[ReportTrade], field_name: str) -> dict[str, dict[str, Decimal]]:
    grouped: dict[str, list[ReportTrade]] = {}
    for trade in trades:
        grouped.setdefault(str(getattr(trade, field_name)), []).append(trade)
    return {
        key: {
            "trades": Decimal(len(items)),
            "pnl": sum((trade.pnl for trade in items), Decimal("0")),
            "win_rate": Decimal(len([trade for trade in items if trade.pnl > 0])) / Decimal(len(items)),
            "average_trade": sum((trade.pnl for trade in items), Decimal("0")) / Decimal(len(items)),
        }
        for key, items in grouped.items()
    }


def _max_drawdown(equity_curve: list[Decimal]) -> Decimal:
    if not equity_curve:
        return Decimal("0")
    peak = equity_curve[0]
    max_drawdown = Decimal("0")
    for equity in equity_curve:
        peak = max(peak, equity)
        if peak:
            max_drawdown = max(max_drawdown, (peak - equity) / peak)
    return max_drawdown


def _sharpe_like(pnls: list[Decimal], initial_equity: Decimal) -> Decimal:
    if len(pnls) < 2 or not initial_equity:
        return Decimal("0")
    returns = [float(pnl / initial_equity) for pnl in pnls]
    stddev = pstdev(returns)
    if stddev == 0:
        return Decimal("0")
    return Decimal(str(mean(returns) / stddev))
