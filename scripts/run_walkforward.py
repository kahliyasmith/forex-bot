"""Run walk-forward validation for a forex strategy."""

from __future__ import annotations

import argparse
import copy
import json
import sys
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
SCRIPTS = ROOT / "scripts"
for path in (SRC, SCRIPTS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from forex_bot.backtest.engine import BacktestResult
from forex_bot.config import load_config
from forex_bot.data import Candle
from forex_bot.data.models import to_decimal
from forex_bot.monitoring.reporting import build_performance_report, decimal_to_json

from run_backtest import (
    build_strategy,
    load_historical_data,
    pairs_from_data,
    parse_pairs,
    report_trades_from_backtest,
    run_backtest,
    write_backtest_trades,
    write_csv,
)


@dataclass(frozen=True)
class Window:
    index: int
    train_start: int
    train_end: int
    test_start: int
    test_end: int
    train_data: list[Candle]
    test_data: list[Candle]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run walk-forward validation from candle CSV data.")
    parser.add_argument("--data", required=True, help="CSV file with candle history.")
    parser.add_argument("--data-kind", choices=["auto", "candles"], default="auto")
    parser.add_argument("--config", default="config/bot.yaml")
    parser.add_argument("--strategy", choices=["trend_pullback"], default="trend_pullback")
    parser.add_argument("--pairs", help="Comma-separated allowed pairs.")
    parser.add_argument("--output-dir", default="reports/walkforward")
    parser.add_argument("--train-window-size", type=int, required=True)
    parser.add_argument("--test-window-size", type=int, required=True)
    parser.add_argument("--step-size", type=int, help="Defaults to test-window-size.")
    parser.add_argument("--initial-balance", default="10000")
    parser.add_argument("--units", default="10000")
    parser.add_argument("--spread-pips", default="1.0")
    parser.add_argument("--slippage-pips", default="0")
    parser.add_argument("--commission-per-trade", default="0")
    parser.add_argument("--swap-cost-per-trade", default="0")
    parser.add_argument("--trend-ma-periods", default="5,10,20")
    parser.add_argument("--pullback-lookbacks", default="2,3,5")
    parser.add_argument("--atr-periods", default="3,5,10")
    parser.add_argument("--atr-multipliers", default="1.0,1.5,2.0")
    parser.add_argument("--reward-r-multiples", default="1.5,2.0,3.0")
    parser.add_argument("--min-confidences", default="0.6")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = load_config(args.config)
    data_kind, market_data = load_historical_data(Path(args.data), args.data_kind)
    if data_kind != "candles":
        raise ValueError("walk-forward validation currently requires candle data")

    allowed_pairs = parse_pairs(args.pairs) or config.pairs or pairs_from_data(market_data)
    windows = build_windows(
        market_data,
        train_window_size=args.train_window_size,
        test_window_size=args.test_window_size,
        step_size=args.step_size or args.test_window_size,
    )
    if not windows:
        raise ValueError("not enough data for one complete train/test window")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    parameter_sets = build_parameter_grid(args)
    window_rows: list[dict[str, object]] = []
    aggregate_trades = []
    aggregate_equity = [to_decimal(args.initial_balance)]
    tested_configs: list[dict[str, object]] = []

    for window in windows:
        window_dir = output_dir / f"window_{window.index:03d}"
        window_dir.mkdir(parents=True, exist_ok=True)
        grid_rows = evaluate_training_grid(args, window, allowed_pairs, parameter_sets)
        tested_configs.extend(
            {**row["parameters"], "window": window.index, "train_score": row["score"]}
            for row in grid_rows
        )
        write_csv(window_dir / "training_grid.csv", flatten_grid_rows(grid_rows))
        best_row = select_best_parameters(grid_rows)
        test_result, test_report = run_window_backtest(
            args=args,
            data=window.test_data,
            allowed_pairs=allowed_pairs,
            parameters=best_row["parameters"],
        )
        test_report.export_json(window_dir / "test_report.json")
        test_report.export_csv(window_dir)
        write_backtest_trades(test_result.trades, window_dir / "test_trades.csv", args.strategy)
        window_row = window_summary_row(window, best_row, test_result, test_report)
        window_rows.append(window_row)
        aggregate_trades.extend(
            report_trades_from_backtest(
                test_result.trades,
                strategy_name=args.strategy,
                spread_pips=to_decimal(args.spread_pips),
                slippage_pips=to_decimal(args.slippage_pips),
            )
        )
        aggregate_equity.extend(_stitch_equity_curve(aggregate_equity[-1], test_result.equity_curve))

    write_csv(output_dir / "walkforward_windows.csv", window_rows)
    aggregate_report = build_performance_report(equity_curve=aggregate_equity, trades=aggregate_trades)
    aggregate_report.export_json(output_dir / "walkforward_oos_report.json")
    aggregate_report.export_csv(output_dir / "aggregate_oos")
    manifest = build_manifest(args, market_data, windows, tested_configs, aggregate_report)
    (output_dir / "walkforward_summary.json").write_text(
        json.dumps(decimal_to_json(manifest), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print_summary(windows, aggregate_report)
    return 0


def build_windows(
    data: list[Candle],
    *,
    train_window_size: int,
    test_window_size: int,
    step_size: int,
) -> list[Window]:
    if min(train_window_size, test_window_size, step_size) <= 0:
        raise ValueError("window sizes and step size must be positive")
    windows: list[Window] = []
    start = 0
    index = 1
    while start + train_window_size + test_window_size <= len(data):
        train_start = start
        train_end = start + train_window_size
        test_start = train_end
        test_end = test_start + test_window_size
        windows.append(
            Window(
                index=index,
                train_start=train_start,
                train_end=train_end,
                test_start=test_start,
                test_end=test_end,
                train_data=data[train_start:train_end],
                test_data=data[test_start:test_end],
            )
        )
        start += step_size
        index += 1
    return windows


def build_parameter_grid(args: argparse.Namespace) -> list[dict[str, object]]:
    parameter_sets: list[dict[str, object]] = []
    for trend_ma_period in parse_int_list(args.trend_ma_periods):
        for pullback_lookback in parse_int_list(args.pullback_lookbacks):
            for atr_period in parse_int_list(args.atr_periods):
                for atr_multiplier in parse_decimal_list(args.atr_multipliers):
                    for reward_r_multiple in parse_decimal_list(args.reward_r_multiples):
                        for min_confidence in parse_float_list(args.min_confidences):
                            parameter_sets.append(
                                {
                                    "trend_ma_period": trend_ma_period,
                                    "pullback_lookback": pullback_lookback,
                                    "atr_period": atr_period,
                                    "atr_multiplier": atr_multiplier,
                                    "reward_r_multiple": reward_r_multiple,
                                    "min_confidence": min_confidence,
                                }
                            )
    return parameter_sets


def evaluate_training_grid(
    args: argparse.Namespace,
    window: Window,
    allowed_pairs: list[str],
    parameter_sets: list[dict[str, object]],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for parameters in parameter_sets:
        result, report = run_window_backtest(
            args=args,
            data=window.train_data,
            allowed_pairs=allowed_pairs,
            parameters=parameters,
        )
        rows.append(
            {
                "parameters": parameters,
                "score": score_report(report),
                "trades": len(result.trades),
                "total_return": report.total_return,
                "max_drawdown": report.max_drawdown,
                "profit_factor": report.profit_factor,
                "expectancy": report.expectancy,
            }
        )
    return rows


def run_window_backtest(
    *,
    args: argparse.Namespace,
    data: list[Candle],
    allowed_pairs: list[str],
    parameters: dict[str, object],
) -> tuple[BacktestResult, object]:
    window_args = copy.copy(args)
    window_args.trend_ma_period = parameters["trend_ma_period"]
    window_args.pullback_lookback = parameters["pullback_lookback"]
    window_args.atr_period = parameters["atr_period"]
    window_args.atr_multiplier = str(parameters["atr_multiplier"])
    window_args.reward_r_multiple = str(parameters["reward_r_multiple"])
    window_args.min_confidence = parameters["min_confidence"]
    return run_backtest(
        args=window_args,
        data_kind="candles",
        market_data=data,
        allowed_pairs=allowed_pairs,
        spread_pips=to_decimal(args.spread_pips),
        slippage_pips=to_decimal(args.slippage_pips),
    )


def score_report(report) -> Decimal:
    """Risk-aware score for parameter selection.

    This intentionally does not optimize only for profit. It rewards expectancy
    while penalizing drawdown.
    """

    return report.expectancy - (report.max_drawdown * Decimal("100"))


def select_best_parameters(rows: list[dict[str, object]]) -> dict[str, object]:
    return max(rows, key=lambda row: (row["score"], row["trades"]))


def flatten_grid_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    return [{**row["parameters"], **{key: value for key, value in row.items() if key != "parameters"}} for row in rows]


def window_summary_row(window: Window, best_row: dict[str, object], result: BacktestResult, report) -> dict[str, object]:
    return {
        "window": window.index,
        "train_start": window.train_data[0].timestamp,
        "train_end": window.train_data[-1].timestamp,
        "test_start": window.test_data[0].timestamp,
        "test_end": window.test_data[-1].timestamp,
        **best_row["parameters"],
        "train_score": best_row["score"],
        "test_trades": len(result.trades),
        "test_total_return": report.total_return,
        "test_max_drawdown": report.max_drawdown,
        "test_win_rate": report.win_rate,
        "test_profit_factor": report.profit_factor,
        "test_expectancy": report.expectancy,
    }


def build_manifest(
    args: argparse.Namespace,
    data: list[Candle],
    windows: list[Window],
    tested_configs: list[dict[str, object]],
    aggregate_report,
) -> dict[str, object]:
    return {
        "assumptions": {
            "strategy": args.strategy,
            "spread_pips": args.spread_pips,
            "slippage_pips": args.slippage_pips,
            "commission_per_trade": args.commission_per_trade,
            "swap_cost_per_trade": args.swap_cost_per_trade,
            "initial_balance": args.initial_balance,
            "units": args.units,
            "selection_score": "expectancy minus max_drawdown*100",
        },
        "data_quality_notes": data_quality_notes(data),
        "windows": len(windows),
        "tested_configs": tested_configs,
        "aggregate_out_of_sample": aggregate_report.to_dict(),
        "warning": (
            "Walk-forward validation reduces but does not eliminate overfit risk. "
            "Results may still be unrealistic if data quality is poor, spreads/slippage are understated, "
            "or the tested parameter grid was designed after inspecting this dataset."
        ),
    }


def data_quality_notes(data: list[Candle]) -> list[str]:
    notes = [
        f"rows={len(data)}",
        f"first_timestamp={data[0].timestamp.isoformat()}",
        f"last_timestamp={data[-1].timestamp.isoformat()}",
        "source_csv_not_independently_verified",
    ]
    duplicate_timestamps = len({candle.timestamp for candle in data}) != len(data)
    if duplicate_timestamps:
        notes.append("duplicate_timestamps_detected")
    return notes


def _stitch_equity_curve(starting_equity: Decimal, equity_curve: list[Decimal]) -> list[Decimal]:
    if len(equity_curve) <= 1:
        return []
    first = equity_curve[0]
    return [starting_equity + (value - first) for value in equity_curve[1:]]


def parse_int_list(value: str) -> list[int]:
    return [int(item.strip()) for item in value.split(",") if item.strip()]


def parse_decimal_list(value: str) -> list[Decimal]:
    return [to_decimal(item.strip()) for item in value.split(",") if item.strip()]


def parse_float_list(value: str) -> list[float]:
    return [float(item.strip()) for item in value.split(",") if item.strip()]


def print_summary(windows: Iterable[Window], aggregate_report) -> None:
    window_count = len(list(windows))
    print("Walk-forward complete")
    print(f"Windows: {window_count}")
    print(f"Out-of-sample total return: {aggregate_report.total_return}")
    print(f"Out-of-sample max drawdown: {aggregate_report.max_drawdown}")
    print(f"Out-of-sample win rate: {aggregate_report.win_rate}")
    print(f"Out-of-sample profit factor: {aggregate_report.profit_factor}")
    print(f"Out-of-sample expectancy: {aggregate_report.expectancy}")
    print("Warning: results may be overfit or unrealistic without independent validation.")


if __name__ == "__main__":
    raise SystemExit(main())
