from pathlib import Path

from forex_bot.cli import main


def test_cli_prints_active_mode(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "bot.yaml"
    config_path.write_text(
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

    exit_code = main(["--config", str(config_path)])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Active bot mode: paper" in output
    assert "Live trading enabled: false" in output
