from pathlib import Path

import pytest
from pydantic import ValidationError

from forex_bot.config import BotConfig, load_config


def valid_config() -> dict:
    return {
        "mode": "paper",
        "base_currency": "USD",
        "pairs": ["EUR_USD", "GBP_USD"],
        "max_spread_pips": {"EUR_USD": 1.2, "GBP_USD": 1.6},
        "risk": {
            "risk_per_trade_pct": 0.25,
            "max_daily_loss_pct": 1.0,
            "max_weekly_loss_pct": 3.0,
            "max_drawdown_pct": 8.0,
            "max_open_trades": 2,
            "max_leverage": 3.0,
        },
        "broker": {"type": "paper"},
        "execution": {"max_slippage_pips": 1.0, "require_stop_loss": True},
        "filters": {
            "avoid_news_minutes_before": 30,
            "avoid_news_minutes_after": 30,
            "avoid_rollover": True,
            "avoid_friday_close": True,
        },
    }


def test_load_config_from_yaml(tmp_path: Path) -> None:
    config_path = tmp_path / "bot.yaml"
    config_path.write_text(
        """
mode: paper
base_currency: usd
pairs:
  - eur_usd
  - gbp_usd
max_spread_pips:
  eur_usd: 1.2
  gbp_usd: 1.6
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

    config = load_config(config_path)

    assert config.mode.value == "paper"
    assert config.base_currency == "USD"
    assert config.pairs == ["EUR_USD", "GBP_USD"]
    assert config.max_spread_pips["EUR_USD"] == 1.2


def test_rejects_missing_spread_for_allowed_pair() -> None:
    raw_config = valid_config()
    raw_config["pairs"].append("USD_JPY")

    with pytest.raises(ValidationError, match="missing max_spread_pips"):
        BotConfig.model_validate(raw_config)


def test_live_trading_disabled_when_mode_is_not_live() -> None:
    raw_config = valid_config()
    raw_config["broker"] = {"type": "live"}
    config = BotConfig.model_validate(raw_config)

    assert config.live_trading_enabled({"LIVE_TRADING_ENABLED": "true"}) is False


def test_live_trading_disabled_without_environment_flag() -> None:
    raw_config = valid_config()
    raw_config["mode"] = "live"
    raw_config["broker"] = {"type": "live"}
    config = BotConfig.model_validate(raw_config)

    assert config.live_trading_enabled({}) is False
    assert config.live_trading_enabled({"LIVE_TRADING_ENABLED": "false"}) is False


def test_live_trading_disabled_when_broker_is_paper() -> None:
    raw_config = valid_config()
    raw_config["mode"] = "live"
    config = BotConfig.model_validate(raw_config)

    assert config.live_trading_enabled({"LIVE_TRADING_ENABLED": "true"}) is False


def test_live_trading_requires_live_mode_live_broker_and_environment_flag() -> None:
    raw_config = valid_config()
    raw_config["mode"] = "live"
    raw_config["broker"] = {"type": "live"}
    config = BotConfig.model_validate(raw_config)

    assert config.live_trading_enabled({"LIVE_TRADING_ENABLED": "true"}) is True
