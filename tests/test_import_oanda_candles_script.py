import csv
import importlib.util
import re
import sys
from pathlib import Path

import pytest


def load_script_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "import_oanda_candles.py"
    spec = importlib.util.spec_from_file_location("import_oanda_candles", script_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["import_oanda_candles"] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def complete_candle(timestamp: str = "2020-01-01T00:00:00.000000000Z") -> dict:
    return {
        "complete": True,
        "volume": 100,
        "time": timestamp,
        "bid": {"o": "1.1000", "h": "1.1010", "l": "1.0990", "c": "1.1005"},
        "ask": {"o": "1.1002", "h": "1.1012", "l": "1.0992", "c": "1.1007"},
    }


def test_response_parsing_outputs_repo_schema() -> None:
    module = load_script_module()
    rows = module.parse_response_candles({"candles": [complete_candle()]}, "EUR_USD")

    assert rows == [
        {
            "timestamp": "2020-01-01T00:00:00Z",
            "pair": "EUR_USD",
            "bid_open": "1.1000",
            "bid_high": "1.1010",
            "bid_low": "1.0990",
            "bid_close": "1.1005",
            "ask_open": "1.1002",
            "ask_high": "1.1012",
            "ask_low": "1.0992",
            "ask_close": "1.1007",
            "volume": "100",
        }
    ]


def test_csv_column_output(tmp_path: Path) -> None:
    module = load_script_module()
    output_path = tmp_path / "candles.csv"
    module.write_candles_csv(
        module.parse_response_candles({"candles": [complete_candle()]}, "EUR_USD"),
        output_path,
    )

    with output_path.open(newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        rows = list(reader)

    assert reader.fieldnames == module.CSV_FIELDS
    assert rows[0]["timestamp"] == "2020-01-01T00:00:00Z"
    assert rows[0]["pair"] == "EUR_USD"


def test_duplicate_timestamp_prevention() -> None:
    module = load_script_module()
    response = {"candles": [complete_candle(), complete_candle()]}

    rows = module.parse_response_candles(response, "EUR_USD", seen_timestamps=set())

    assert len(rows) == 1


def test_missing_bid_or_ask_rejected() -> None:
    module = load_script_module()
    candle = complete_candle()
    del candle["ask"]

    with pytest.raises(module.OandaImportError, match="missing bid or ask"):
        module.parse_response_candles({"candles": [candle]}, "EUR_USD")


def test_incomplete_candles_are_skipped() -> None:
    module = load_script_module()
    incomplete = complete_candle("2020-01-01T00:00:00.000000000Z")
    incomplete["complete"] = False
    complete = complete_candle("2020-01-01T01:00:00.000000000Z")

    rows = module.parse_response_candles({"candles": [incomplete, complete]}, "EUR_USD")

    assert len(rows) == 1
    assert rows[0]["timestamp"] == "2020-01-01T01:00:00Z"


def test_no_api_key_is_hardcoded() -> None:
    script_text = (Path(__file__).resolve().parents[1] / "scripts" / "import_oanda_candles.py").read_text(encoding="utf-8")

    assert "OANDA_API_KEY" in script_text
    assert "YOUR_API_KEY" not in script_text
    assert "REPLACE_ME" not in script_text
    assert not re.search(r"[A-Za-z0-9_-]{40,}", script_text)


def test_cli_help_works(capsys) -> None:
    module = load_script_module()

    with pytest.raises(SystemExit) as exc:
        module.main(["--help"])

    assert exc.value.code == 0
    assert "Import OANDA REST v20 bid/ask candles" in capsys.readouterr().out


def test_fetch_uses_deterministic_chunks_and_deduplicates() -> None:
    module = load_script_module()
    requested_urls: list[str] = []

    def fake_fetch(url: str, api_key: str) -> dict:
        requested_urls.append(url)
        return {"candles": [complete_candle("2020-01-01T00:00:00.000000000Z")]}

    rows = module.fetch_candles(
        api_key="env-token",
        base_url=module.PRACTICE_URL,
        instrument="EUR_USD",
        granularity="H1",
        start=module.parse_utc_timestamp("2020-01-01T00:00:00Z"),
        end=module.parse_utc_timestamp("2020-09-01T00:00:00Z"),
        fetch_json=fake_fetch,
    )

    assert len(requested_urls) > 1
    assert len(rows) == 1
    assert "price=BA" in requested_urls[0]
