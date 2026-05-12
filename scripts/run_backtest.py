"""Run a forex strategy backtest from historical CSV data."""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Literal

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from forex_bot.backtest import BacktestConfig, BacktestEngine
from forex_bot.backtest.engine import BacktestResult, Trade
from forex_bot.bot import classify_session
from forex_bot.config import load_config
from forex_bot.data import Candle, CurrencyPair, Quote
from forex_bot.data.models import to_decimal
from forex_bot.monitoring.reporting import ReportTrade, build_performance_report, decimal_to_json
from forex_bot.strategies import TrendPullbackParameters, TrendPullbackStrategy
from forex_bot.strategies.base import Strategy

DataKind = Literal["quotes", "candles"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a forex backtest from CSV data.")
    parser.add_argument("--data", required=True, help="CSV file with quote or candle history.")
    parser.add_argument(
        "--data-kind",
        choices=["auto", "quotes", "candles"],
        default="auto",
        help="Input data type. Auto detects from CSV headers by default.",
    )
    parser.add_argument("--config", default="config/bot.yaml", help="Bot config YAML path.")
    parser.add_argument(
        "--strategy",
        choices=["trend_pullback"],
        default="trend_pullback",
        help="Strategy to run.",
    )
    parser.add_argument(
        "--pairs",
        help="Comma-separated allowed pairs. Defaults to config pairs or pairs in data.",
    )
    parser.add_argument("--output-dir", default="reports/backtest", help="Directory for outputs.")
    parser.add_argument("--initial-balance", default="10000")
    parser.add_argument("--units", default="10000")
    parser.add_argument("--spread-pips", default="1.0", help="Assumed spread for candle data.")
    parser.add_argument("--slippage-pips", default="0")
    parser.add_argument("--commission-per-trade", default="0")
    parser.add_argument("--swap-cost-per-trade", default="0")
    parser.add_argument("--trend-ma-period", type=int, default=5)
    parser.add_argument("--pullback-lookback", type=int, default=3)
    parser.add_argument("--atr-period", type=int, default=3)
    parser.add_argument("--atr-multiplier", default="1.5")
    parser.add_argument("--reward-r-multiple", default="2.0")
    parser.add_argument("--min-confidence", type=float, default=0.6)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = load_config(args.config)
    data_kind, market_data = load_historical_data(Path(args.data), args.data_kind)
    allowed_pairs = parse_pairs(args.pairs) or config.pairs or pairs_from_data(market_data)
    strategy = build_strategy(args.strategy, args, allowed_pairs)
    engine = BacktestEngine(
        BacktestConfig(
            initial_balance=to_decimal(args.initial_balance),
            units=to_decimal(args.units),
            commission_per_trade=to_decimal(args.commission_per_trade),
            slippage_pips=to_decimal(args.slippage_pips),
            swap_cost_per_trade=to_decimal(args.swap_cost_per_trade),
        )
    )

    if data_kind == "candles":
        result = engine.run_candles(
            market_data,
            strategy,
            spread_pips=to_decimal(args.spread_pips),
        )
        assumed_spread_pips = to_decimal(args.spread_pips)
    else:
        result = engine.run(market_data, strategy)
        assumed_spread_pips = average_quote_spread(market_data)

    report_trades = report_trades_from_backtest(
        result.trades,
        strategy_name=args.strategy,
        spread_pips=assumed_spread_pips,
        slippage_pips=to_decimal(args.slippage_pips),
    )
    report = build_performance_report(equity_curve=result.equity_curve, trades=report_trades)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    write_backtest_trades(result.trades, output_dir / "backtest_trades.csv", args.strategy)
    report.export_json(output_dir / "performance_report.json")
    report.export_csv(output_dir)

    print_summary(result, report)
    return 0


def load_historical_data(path: Path, data_kind: str = "auto") -> tuple[DataKind, list[Quote] | list[Candle]]:
    with path.open("r", newline="", encoding="utf-8") as csv_file:
        rows = [{key.strip().lower(): value.strip() for key, value in row.items()} for row in csv.DictReader(csv_file)]
    if not rows:
        raise ValueError(f"no rows found in {path}")

    detected_kind = detect_data_kind(rows[0].keys()) if data_kind == "auto" else data_kind
    if detected_kind == "quotes":
        quotes = [
            Quote(
                pair=row.get("pair") or row.get("symbol") or "",
                bid=row["bid"],
                ask=row["ask"],
                timestamp=parse_timestamp(row["timestamp"]),
            )
            for row in rows
        ]
        return "quotes", sorted(quotes, key=lambda quote: quote.timestamp)
    if detected_kind == "candles":
        candles = [
            Candle(
                pair=row.get("pair") or row.get("symbol") or "",
                open=row["open"],
                high=row["high"],
                low=row["low"],
                close=row["close"],
                volume=row.get("volume", "0") or "0",
                timestamp=parse_timestamp(row["timestamp"]),
            )
            for row in rows
        ]
        return "candles", sorted(candles, key=lambda candle: candle.timestamp)
    raise ValueError(f"unsupported data kind: {data_kind}")


def detect_data_kind(headers) -> DataKind:
    header_set = set(headers)
    if {"timestamp", "bid", "ask"}.issubset(header_set) and ("pair" in header_set or "symbol" in header_set):
        return "quotes"
    if {"timestamp", "open", "high", "low", "close"}.issubset(header_set) and (
        "pair" in header_set or "symbol" in header_set
    ):
        return "candles"
    raise ValueError("CSV must contain quote columns or candle columns")


def parse_timestamp(value: str) -> datetime:
    timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return timestamp if timestamp.tzinfo else timestamp.replace(tzinfo=timezone.utc)


def parse_pairs(value: str | None) -> list[str] | None:
    if not value:
        return None
    return [CurrencyPair.parse(pair.strip()).symbol for pair in value.split(",") if pair.strip()]


def pairs_from_data(market_data: list[Quote] | list[Candle]) -> list[str]:
    return sorted({event.pair.symbol for event in market_data})


def build_strategy(name: str, args: argparse.Namespace, allowed_pairs: list[str]) -> Strategy:
    if name == "trend_pullback":
        return TrendPullbackStrategy(
            TrendPullbackParameters(
                allowed_pairs=allowed_pairs,
                trend_ma_period=args.trend_ma_period,
                pullback_lookback=args.pullback_lookback,
                atr_period=args.atr_period,
                atr_multiplier=to_decimal(args.atr_multiplier),
                reward_r_multiple=to_decimal(args.reward_r_multiple),
                min_confidence=args.min_confidence,
            )
        )
    raise ValueError(f"unsupported strategy: {name}")


def average_quote_spread(quotes: list[Quote] | list[Candle]) -> Decimal:
    quote_rows = [quote for quote in quotes if isinstance(quote, Quote)]
    if not quote_rows:
        return Decimal("0")
    return sum((quote.spread_pips for quote in quote_rows), Decimal("0")) / Decimal(len(quote_rows))


def report_trades_from_backtest(
    trades: list[Trade],
    *,
    strategy_name: str,
    spread_pips: Decimal,
    slippage_pips: Decimal,
) -> list[ReportTrade]:
    return [
        ReportTrade(
            pair=trade.pair.symbol,
            strategy=strategy_name,
            session=classify_session(trade.closed_at),
            opened_at=trade.opened_at,
            closed_at=trade.closed_at,
            pnl=trade.net_pnl,
            spread_pips=spread_pips,
            slippage_pips=slippage_pips,
        )
        for trade in trades
    ]


def write_backtest_trades(trades: list[Trade], path: Path, strategy_name: str) -> None:
    rows = [
        {
            "pair": trade.pair.symbol,
            "strategy": strategy_name,
            "direction": trade.direction,
            "units": trade.units,
            "entry_price": trade.entry_price,
            "exit_price": trade.exit_price,
            "opened_at": trade.opened_at,
            "closed_at": trade.closed_at,
            "exit_reason": trade.exit_reason,
            "gross_pnl": trade.gross_pnl,
            "commission": trade.commission,
            "swap": trade.swap,
            "net_pnl": trade.net_pnl,
        }
        for trade in trades
    ]
    write_csv(path, rows)


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    normalized = [decimal_to_json(row) for row in rows]
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=list(normalized[0].keys()))
        writer.writeheader()
        writer.writerows(normalized)


def print_summary(result: BacktestResult, report) -> None:
    print("Backtest complete")
    print(f"Trades: {len(result.trades)}")
    print(f"Total return: {report.total_return}")
    print(f"Max drawdown: {report.max_drawdown}")
    print(f"Win rate: {report.win_rate}")
    print(f"Profit factor: {report.profit_factor}")
    print(f"Expectancy: {report.expectancy}")
    print(f"Average trade: {report.average_trade}")
    print(f"Average spread paid: {report.average_spread_paid}")
    print(f"Average slippage: {report.average_slippage}")


if __name__ == "__main__":
    raise SystemExit(main())
