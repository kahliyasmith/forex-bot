from pathlib import Path

import pytest

from forex_bot.data.manifest import load_data_manifest


def write_manifest(path: Path, data_path: str) -> None:
    path.write_text(
        f"""
symbols:
  EURUSD:
    source: "broker_or_vendor_name"
    broker_or_venue: "demo_venue"
    data_type: "bidask_candles"
    timeframe: "H1"
    timezone: "UTC"
    path: "{data_path}"
    start: "2020-01-01"
    end: "2025-12-31"
    columns:
      timestamp: "timestamp"
      pair: "pair"
      bid_open: "bid_open"
      bid_high: "bid_high"
      bid_low: "bid_low"
      bid_close: "bid_close"
      ask_open: "ask_open"
      ask_high: "ask_high"
      ask_low: "ask_low"
      ask_close: "ask_close"
      volume: "volume"
    spread_available: true
    commission_model: "documented_in_assumptions.md"
    swap_model: "documented_in_assumptions.md"
    account_currency: "USD"
    expected_interval: "60m"
    validation:
      required_before_backtest: true
      expected_interval_minutes: 60
      max_spread_pips: 10
""",
        encoding="utf-8",
    )


def test_load_data_manifest(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data" / "historical"
    config_dir.mkdir()
    data_dir.mkdir(parents=True)
    market_data = data_dir / "EUR_USD_H1_bidask_2020_2025.csv"
    market_data.write_text("timestamp,pair,bid_open,bid_high,bid_low,bid_close,ask_open,ask_high,ask_low,ask_close,volume\n", encoding="utf-8")
    manifest_path = config_dir / "data_manifest.yaml"
    write_manifest(manifest_path, "data/historical/EUR_USD_H1_bidask_2020_2025.csv")

    manifest = load_data_manifest(manifest_path)

    entry = manifest.symbols["EUR_USD"]
    assert entry.pair == "EUR_USD"
    assert entry.data_type == "bidask_candles"
    assert entry.timeframe == "H1"
    assert entry.validation.expected_interval_minutes == 60


def test_load_data_manifest_rejects_missing_data_file(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    manifest_path = config_dir / "data_manifest.yaml"
    write_manifest(manifest_path, "data/historical/missing.csv")

    with pytest.raises(FileNotFoundError, match="manifest data file not found"):
        load_data_manifest(manifest_path)
