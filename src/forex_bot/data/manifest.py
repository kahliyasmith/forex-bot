"""Data manifest loading for historical market data files."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from forex_bot.data.models import CurrencyPair


class ManifestValidationSettings(BaseModel):
    """Optional validation metadata for one manifest entry."""

    model_config = ConfigDict(extra="allow")

    required_before_backtest: bool = True
    validator_command: str | None = None
    expected_interval_minutes: int | None = Field(default=None, gt=0)
    max_spread_pips: float | None = Field(default=None, gt=0)
    max_gap_pct: float | None = Field(default=None, gt=0)


class DataManifestEntry(BaseModel):
    """One historical dataset registered in the manifest."""

    model_config = ConfigDict(extra="allow")

    pair: str
    source: str
    broker_or_venue: str
    data_type: str
    timeframe: str
    timezone: str
    path: Path
    start: date
    end: date
    columns: dict[str, str | None]
    spread_available: bool
    commission_model: str
    swap_model: str
    account_currency: str
    expected_interval: str | None = None
    validation: ManifestValidationSettings = Field(default_factory=ManifestValidationSettings)

    @field_validator("pair")
    @classmethod
    def normalize_pair(cls, value: str) -> str:
        return CurrencyPair.parse(value).symbol

    @field_validator("account_currency")
    @classmethod
    def normalize_account_currency(cls, value: str) -> str:
        normalized = value.upper()
        if len(normalized) != 3:
            raise ValueError("account_currency must be a three-letter ISO currency code")
        return normalized

    @model_validator(mode="after")
    def validate_dates(self) -> "DataManifestEntry":
        if self.end < self.start:
            raise ValueError("end must be greater than or equal to start")
        return self


class DataManifest(BaseModel):
    """Collection of historical datasets keyed by pair symbol."""

    model_config = ConfigDict(extra="forbid")

    symbols: dict[str, DataManifestEntry]

    @model_validator(mode="after")
    def validate_symbol_keys(self) -> "DataManifest":
        for key, entry in self.symbols.items():
            symbol = CurrencyPair.parse(key).symbol
            if entry.pair != symbol:
                raise ValueError(f"manifest key {key} does not match entry pair {entry.pair}")
        return self


def load_data_manifest(
    path: str | Path = "config/data_manifest.yaml",
    *,
    require_files: bool = True,
) -> DataManifest:
    """Load and validate a historical data manifest.

    Relative data paths are resolved from the repository root when the manifest
    is inside `config/`, otherwise from the manifest file's parent directory.
    """

    manifest_path = Path(path)
    with manifest_path.open("r", encoding="utf-8") as manifest_file:
        raw_manifest: Any = yaml.safe_load(manifest_file) or {}
    if not isinstance(raw_manifest, dict):
        raise ValueError(f"data manifest must be a mapping: {manifest_path}")

    raw_symbols = raw_manifest.get("symbols")
    if not isinstance(raw_symbols, dict) or not raw_symbols:
        raise ValueError("data manifest must define at least one symbol")

    normalized_symbols: dict[str, Any] = {}
    for key, raw_entry in raw_symbols.items():
        if not isinstance(raw_entry, dict):
            raise ValueError(f"manifest entry must be a mapping: {key}")
        symbol = CurrencyPair.parse(str(key)).symbol
        entry = dict(raw_entry)
        entry.setdefault("pair", symbol)
        normalized_symbols[symbol] = entry

    manifest = DataManifest.model_validate({"symbols": normalized_symbols})
    if require_files:
        base_dir = manifest_base_dir(manifest_path)
        missing = [
            str(resolve_manifest_path(entry.path, base_dir))
            for entry in manifest.symbols.values()
            if not resolve_manifest_path(entry.path, base_dir).exists()
        ]
        if missing:
            raise FileNotFoundError(f"manifest data file not found: {', '.join(missing)}")
    return manifest


def manifest_base_dir(manifest_path: Path) -> Path:
    resolved = manifest_path.resolve()
    if resolved.parent.name == "config":
        return resolved.parent.parent
    return resolved.parent


def resolve_manifest_path(path: str | Path, base_dir: Path) -> Path:
    data_path = Path(path)
    if data_path.is_absolute():
        return data_path
    return base_dir / data_path
