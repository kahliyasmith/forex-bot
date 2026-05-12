import importlib.util
import json
from pathlib import Path


def load_script_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_backtest.py"
    spec = importlib.util.spec_from_file_location("run_backtest", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


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


def write_candles(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "timestamp,pair,open,high,low,close,volume",
                "2026-01-05T14:00:00Z,EUR_USD,1.1000,1.1010,1.0990,1.1000,1000",
                "2026-01-05T15:00:00Z,EUR_USD,1.1000,1.1020,1.1000,1.1010,1000",
                "2026-01-05T16:00:00Z,EUR_USD,1.1010,1.1030,1.1010,1.1020,1000",
                "2026-01-05T17:00:00Z,EUR_USD,1.1020,1.1040,1.1020,1.1030,1000",
                "2026-01-05T18:00:00Z,EUR_USD,1.1030,1.1035,1.1015,1.1020,1000",
                "2026-01-05T19:00:00Z,EUR_USD,1.1020,1.1050,1.1020,1.1045,1000",
                "2026-01-05T20:00:00Z,EUR_USD,1.1045,1.1080,1.1040,1.1070,1000",
            ]
        ),
        encoding="utf-8",
    )


def test_load_historical_quote_data(tmp_path: Path) -> None:
    module = load_script_module()
    data_path = tmp_path / "quotes.csv"
    data_path.write_text(
        "\n".join(
            [
                "timestamp,pair,bid,ask",
                "2026-01-05T14:00:00Z,EUR_USD,1.1000,1.1002",
                "2026-01-05T14:01:00Z,EUR_USD,1.1001,1.1003",
            ]
        ),
        encoding="utf-8",
    )

    data_kind, rows = module.load_historical_data(data_path)

    assert data_kind == "quotes"
    assert len(rows) == 2
    assert rows[0].spread_pips == 2


def test_run_backtest_script_writes_outputs(tmp_path: Path, capsys) -> None:
    module = load_script_module()
    config_path = tmp_path / "bot.yaml"
    data_path = tmp_path / "candles.csv"
    output_dir = tmp_path / "out"
    write_config(config_path)
    write_candles(data_path)

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
            "--trend-ma-period",
            "3",
            "--atr-period",
            "2",
            "--pullback-lookback",
            "2",
            "--spread-pips",
            "1.0",
            "--slippage-pips",
            "0.2",
            "--commission-per-trade",
            "0.5",
            "--swap-cost-per-trade",
            "0.1",
        ]
    )

    output = capsys.readouterr().out
    report = json.loads((output_dir / "performance_report.json").read_text(encoding="utf-8"))

    assert exit_code == 0
    assert "Backtest complete" in output
    assert "Trades: 1" in output
    assert (output_dir / "backtest_trades.csv").exists()
    assert (output_dir / "equity_curve.csv").exists()
    assert (output_dir / "cost_stress_report.csv").exists()
    assert (output_dir / "cost_stress_report.json").exists()
    assert report["average_spread_paid"] == 1.0
    assert report["average_slippage"] == 0.2


def test_run_backtest_script_writes_cost_stress_grid(tmp_path: Path) -> None:
    module = load_script_module()
    config_path = tmp_path / "bot.yaml"
    data_path = tmp_path / "candles.csv"
    output_dir = tmp_path / "out"
    write_config(config_path)
    write_candles(data_path)

    module.main(
        [
            "--config",
            str(config_path),
            "--data",
            str(data_path),
            "--data-kind",
            "candles",
            "--output-dir",
            str(output_dir),
            "--trend-ma-period",
            "3",
            "--atr-period",
            "2",
            "--pullback-lookback",
            "2",
            "--spread-pips",
            "1.0",
            "--slippage-pips",
            "0.2",
        ]
    )

    rows = json.loads((output_dir / "cost_stress_report.json").read_text(encoding="utf-8"))

    assert len(rows) == 9
    assert rows[0]["regime"] == "spread_1x_slippage_1x"
    assert rows[-1]["regime"] == "spread_3x_slippage_3x"
    assert rows[-1]["spread_pips"] == 3.0
    assert rows[-1]["slippage_pips"] == 0.6
    assert "profit_factor" in rows[-1]
