import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


def load_script_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_walkforward.py"
    spec = importlib.util.spec_from_file_location("run_walkforward", script_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["run_walkforward"] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def write_candles(path: Path, rows: int = 21) -> None:
    start = datetime(2026, 1, 5, 14, tzinfo=timezone.utc)
    pattern = [
        ("1.1000", "1.1010", "1.0990", "1.1000"),
        ("1.1000", "1.1020", "1.1000", "1.1010"),
        ("1.1010", "1.1030", "1.1010", "1.1020"),
        ("1.1020", "1.1040", "1.1020", "1.1030"),
        ("1.1030", "1.1035", "1.1015", "1.1020"),
        ("1.1020", "1.1050", "1.1020", "1.1045"),
        ("1.1045", "1.1080", "1.1040", "1.1070"),
    ]
    lines = ["timestamp,pair,open,high,low,close,volume"]
    for index in range(rows):
        candle = pattern[index % len(pattern)]
        timestamp = start + timedelta(hours=index)
        lines.append(
            f"{timestamp.isoformat().replace('+00:00', 'Z')},EUR_USD,{candle[0]},{candle[1]},{candle[2]},{candle[3]},1000"
        )
    path.write_text("\n".join(lines), encoding="utf-8")


def write_config(path: Path) -> None:
    path.write_text(
        """
mode: paper
base_currency: USD
pairs:
  - EUR_USD
max_spread_pips:
  EUR_USD: 1.2
risk:
  risk_per_trade_pct: 0.25
  max_daily_loss_pct: 1.0
  max_weekly_loss_pct: 3.0
  max_drawdown_pct: 8.0
  max_open_trades: 2
  max_leverage: 3.0
broker:
  type: paper
execution:
  max_slippage_pips: 1.0
  require_stop_loss: true
filters:
  avoid_news_minutes_before: 30
  avoid_news_minutes_after: 30
  avoid_rollover: true
  avoid_friday_close: true
""",
        encoding="utf-8",
    )


def test_build_windows() -> None:
    module = load_script_module()
    candles = [object() for _ in range(20)]

    windows = module.build_windows(
        candles,
        train_window_size=6,
        test_window_size=4,
        step_size=4,
    )

    assert len(windows) == 3
    assert windows[0].train_start == 0
    assert windows[0].test_start == 6
    assert windows[-1].train_start == 8
    assert windows[-1].test_end == 18


def test_run_walkforward_writes_window_and_aggregate_reports(tmp_path: Path, capsys) -> None:
    module = load_script_module()
    config_path = tmp_path / "bot.yaml"
    data_path = tmp_path / "candles.csv"
    output_dir = tmp_path / "walkforward"
    write_config(config_path)
    write_candles(data_path, rows=21)

    exit_code = module.main(
        [
            "--config",
            str(config_path),
            "--data",
            str(data_path),
            "--data-kind",
            "candles",
            "--output-dir",
            str(output_dir),
            "--train-window-size",
            "7",
            "--test-window-size",
            "7",
            "--step-size",
            "7",
            "--trend-ma-periods",
            "3",
            "--pullback-lookbacks",
            "2",
            "--atr-periods",
            "2",
            "--atr-multipliers",
            "1.5,2.0",
            "--reward-r-multiples",
            "2.0",
            "--spread-pips",
            "1.0",
            "--slippage-pips",
            "0.2",
        ]
    )

    output = capsys.readouterr().out
    summary = json.loads((output_dir / "walkforward_summary.json").read_text(encoding="utf-8"))

    assert exit_code == 0
    assert "Walk-forward complete" in output
    assert "Windows: 2" in output
    assert (output_dir / "window_001" / "training_grid.csv").exists()
    assert (output_dir / "window_001" / "test_trades.csv").exists()
    assert (output_dir / "window_002" / "test_report.json").exists()
    assert (output_dir / "walkforward_windows.csv").exists()
    assert (output_dir / "walkforward_oos_report.json").exists()
    assert summary["windows"] == 2
    assert len(summary["tested_configs"]) == 4
    assert "data_quality_notes" in summary
    assert "overfit" in summary["warning"]
