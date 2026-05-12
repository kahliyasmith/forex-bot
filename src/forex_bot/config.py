"""Validated configuration loading for forex-bot."""

from __future__ import annotations

import os
import re
from enum import Enum
from pathlib import Path
from typing import Any, Mapping

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

PAIR_PATTERN = re.compile(r"^[A-Z]{3}_[A-Z]{3}$")
TRUE_VALUES = {"1", "true", "yes", "on"}


class BotMode(str, Enum):
    """Supported bot runtime modes."""

    BACKTEST = "backtest"
    PAPER = "paper"
    LIVE = "live"


class BrokerType(str, Enum):
    """Supported broker adapter types."""

    PAPER = "paper"
    LIVE = "live"


class RiskConfig(BaseModel):
    """Risk limits expressed as account-level guardrails."""

    risk_per_trade_pct: float = Field(gt=0, le=5)
    max_daily_loss_pct: float = Field(gt=0, le=25)
    max_weekly_loss_pct: float = Field(gt=0, le=50)
    max_drawdown_pct: float = Field(gt=0, le=100)
    max_open_trades: int = Field(ge=1, le=100)
    max_leverage: float = Field(gt=0, le=50)

    @model_validator(mode="after")
    def validate_loss_limits(self) -> "RiskConfig":
        if self.max_weekly_loss_pct < self.max_daily_loss_pct:
            raise ValueError("max_weekly_loss_pct must be greater than or equal to max_daily_loss_pct")
        if self.max_drawdown_pct < self.max_weekly_loss_pct:
            raise ValueError("max_drawdown_pct must be greater than or equal to max_weekly_loss_pct")
        return self


class BrokerConfig(BaseModel):
    """Broker adapter selection."""

    type: BrokerType = BrokerType.PAPER


class ExecutionConfig(BaseModel):
    """Execution limits that apply before any order can be submitted."""

    max_slippage_pips: float = Field(ge=0)
    require_stop_loss: bool = True


class FilterConfig(BaseModel):
    """News and session filters for suppressing unsafe trading windows."""

    avoid_news_minutes_before: int = Field(ge=0)
    avoid_news_minutes_after: int = Field(ge=0)
    avoid_rollover: bool = True
    avoid_friday_close: bool = True


class BotConfig(BaseModel):
    """Top-level forex-bot configuration."""

    model_config = ConfigDict(extra="forbid")

    mode: BotMode = BotMode.PAPER
    base_currency: str = Field(default="USD", min_length=3, max_length=3)
    pairs: list[str] = Field(min_length=1)
    max_spread_pips: dict[str, float]
    risk: RiskConfig
    broker: BrokerConfig = Field(default_factory=BrokerConfig)
    execution: ExecutionConfig
    filters: FilterConfig

    @field_validator("base_currency")
    @classmethod
    def normalize_base_currency(cls, value: str) -> str:
        return value.upper()

    @field_validator("pairs")
    @classmethod
    def validate_pairs(cls, values: list[str]) -> list[str]:
        normalized = [value.upper() for value in values]
        invalid = [value for value in normalized if not PAIR_PATTERN.match(value)]
        if invalid:
            raise ValueError(f"invalid currency pair format: {', '.join(invalid)}")
        if len(set(normalized)) != len(normalized):
            raise ValueError("pairs must be unique")
        return normalized

    @field_validator("max_spread_pips")
    @classmethod
    def validate_spreads(cls, values: dict[str, float]) -> dict[str, float]:
        normalized = {pair.upper(): spread for pair, spread in values.items()}
        invalid_pairs = [pair for pair in normalized if not PAIR_PATTERN.match(pair)]
        if invalid_pairs:
            raise ValueError(f"invalid max spread pair format: {', '.join(invalid_pairs)}")
        invalid_spreads = [pair for pair, spread in normalized.items() if spread <= 0]
        if invalid_spreads:
            raise ValueError(f"max spread must be positive for: {', '.join(invalid_spreads)}")
        return normalized

    @model_validator(mode="after")
    def validate_spread_coverage(self) -> "BotConfig":
        configured_pairs = set(self.pairs)
        spread_pairs = set(self.max_spread_pips)
        missing = configured_pairs - spread_pairs
        unknown = spread_pairs - configured_pairs
        if missing:
            raise ValueError(f"missing max_spread_pips for: {', '.join(sorted(missing))}")
        if unknown:
            raise ValueError(f"max_spread_pips includes unknown pairs: {', '.join(sorted(unknown))}")
        return self

    def live_trading_enabled(self, environ: Mapping[str, str] | None = None) -> bool:
        """Return whether live trading is explicitly enabled for this process."""

        env = os.environ if environ is None else environ
        flag = env.get("LIVE_TRADING_ENABLED", "")
        return (
            self.mode is BotMode.LIVE
            and self.broker.type is BrokerType.LIVE
            and flag.strip().lower() in TRUE_VALUES
        )


def load_config(path: str | Path = "config/bot.yaml") -> BotConfig:
    """Load and validate a YAML bot configuration file."""

    config_path = Path(path)
    with config_path.open("r", encoding="utf-8") as config_file:
        raw_config: Any = yaml.safe_load(config_file) or {}
    if not isinstance(raw_config, dict):
        raise ValueError(f"configuration must be a mapping: {config_path}")
    return BotConfig.model_validate(raw_config)
