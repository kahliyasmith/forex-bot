import importlib.util
import sys
from pathlib import Path


def load_script_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "validate_market_data.py"
    spec = importlib.util.spec_from_file_location("validate_market_data", script_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["validate_market_data"] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_validate_good_quote_data(tmp_path: Path) -> None:
    module = load_script_module()
    data_path = tmp_path / "EUR_USD_quotes.csv"
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

    result = module.validate_csv(data_path, expected_interval=module.timedelta(minutes=1))

    assert result.passed is True
    assert result.data_kind == "quotes"
    assert result.pairs == ["EUR_USD"]
    assert result.rows == 2


def test_validate_good_candle_data(tmp_path: Path) -> None:
    module = load_script_module()
    data_path = tmp_path / "EUR_USD_H1.csv"
    data_path.write_text(
        "\n".join(
            [
                "timestamp,pair,open,high,low,close,volume",
                "2026-01-05T14:00:00Z,EUR_USD,1.1000,1.1010,1.0990,1.1005,1000",
                "2026-01-05T15:00:00Z,EUR_USD,1.1005,1.1020,1.1000,1.1010,1000",
            ]
        ),
        encoding="utf-8",
    )

    result = module.validate_csv(data_path, expected_interval=module.timedelta(hours=1))

    assert result.passed is True
    assert result.data_kind == "candles"
    assert result.rows == 2


def test_validate_bad_quote_data_reports_errors_and_warnings(tmp_path: Path) -> None:
    module = load_script_module()
    data_path = tmp_path / "bad_quotes.csv"
    data_path.write_text(
        "\n".join(
            [
                "timestamp,pair,bid,ask",
                "2026-01-03T14:00:00Z,EUR_USD,1.1005,1.1000",
                "2026-01-03T14:00:00Z,EUR_USD,1.1000,1.1050",
                "2026-01-03T14:04:00,EUR_USD,1.1001,1.1003",
            ]
        ),
        encoding="utf-8",
    )

    result = module.validate_csv(
        data_path,
        expected_interval=module.timedelta(minutes=1),
        max_spread_pips=module.Decimal("5"),
    )
    checks = {issue.check for issue in result.issues}

    assert result.passed is False
    assert "crossed_market" in checks
    assert "duplicate_timestamp" in checks
    assert "timezone" in checks
    assert "weekend_row" in checks
    assert "unrealistic_spread" in checks


def test_validate_bidask_candle_data_and_auto_detection(tmp_path: Path) -> None:
    module = load_script_module()
    data_path = tmp_path / "EUR_USD_H1_bidask.csv"
    data_path.write_text(
        "\n".join(
            [
                "timestamp,pair,bid_open,bid_high,bid_low,bid_close,ask_open,ask_high,ask_low,ask_close,volume",
                "2026-01-05T14:00:00Z,EUR_USD,1.1000,1.1010,1.0990,1.1005,1.1002,1.1012,1.0992,1.1007,1000",
                "2026-01-05T15:00:00Z,EUR_USD,1.1005,1.1020,1.1000,1.1010,1.1007,1.1022,1.1002,1.1012,1000",
            ]
        ),
        encoding="utf-8",
    )

    result = module.validate_csv(data_path, expected_interval=module.timedelta(hours=1))

    assert result.passed is True
    assert result.data_kind == "bidask_candles"
    assert result.pairs == ["EUR_USD"]


def test_validate_bidask_candle_reports_crossed_market(tmp_path: Path) -> None:
    module = load_script_module()
    data_path = tmp_path / "crossed_bidask.csv"
    data_path.write_text(
        "\n".join(
            [
                "timestamp,pair,bid_open,bid_high,bid_low,bid_close,ask_open,ask_high,ask_low,ask_close,volume",
                "2026-01-05T14:00:00Z,EUR_USD,1.1000,1.1010,1.0990,1.1005,1.0999,1.1012,1.0992,1.1007,1000",
            ]
        ),
        encoding="utf-8",
    )

    result = module.validate_csv(data_path, data_kind="bidask_candles")

    assert result.passed is False
    assert "crossed_market" in {issue.check for issue in result.issues}


def test_validate_bidask_candle_reports_unrealistic_spread_and_missing_interval(tmp_path: Path) -> None:
    module = load_script_module()
    data_path = tmp_path / "wide_spread_bidask.csv"
    data_path.write_text(
        "\n".join(
            [
                "timestamp,pair,bid_open,bid_high,bid_low,bid_close,ask_open,ask_high,ask_low,ask_close,volume",
                "2026-01-05T14:00:00Z,EUR_USD,1.1000,1.1010,1.0990,1.1005,1.1002,1.1012,1.0992,1.1007,1000",
                "2026-01-05T16:00:00Z,EUR_USD,1.1005,1.1020,1.1000,1.1010,1.1015,1.1030,1.1010,1.1020,1000",
            ]
        ),
        encoding="utf-8",
    )

    result = module.validate_csv(
        data_path,
        data_kind="bidask_candles",
        expected_interval=module.timedelta(hours=1),
        max_spread_pips=module.Decimal("5"),
    )
    checks = {issue.check for issue in result.issues}

    assert result.passed is True
    assert "unrealistic_spread" in checks
    assert "missing_interval" in checks


def test_validate_bidask_candle_spread_pips_for_jpy_and_non_jpy(tmp_path: Path) -> None:
    module = load_script_module()
    data_path = tmp_path / "mixed_bidask.csv"
    data_path.write_text(
        "\n".join(
            [
                "timestamp,pair,bid_open,bid_high,bid_low,bid_close,ask_open,ask_high,ask_low,ask_close,volume",
                "2026-01-05T14:00:00Z,EUR_USD,1.1000,1.1010,1.0990,1.1005,1.1008,1.1018,1.0998,1.1013,1000",
                "2026-01-05T14:00:00Z,USD_JPY,150.00,150.20,149.90,150.10,150.08,150.28,149.98,150.18,1000",
            ]
        ),
        encoding="utf-8",
    )

    result = module.validate_csv(
        data_path,
        data_kind="bidask_candles",
        max_spread_pips=module.Decimal("5"),
    )
    messages = [issue.message for issue in result.issues if issue.check == "unrealistic_spread"]

    assert len(messages) == 8
    assert any("8" in message for message in messages)


def test_validator_cli_writes_reports(tmp_path: Path, capsys) -> None:
    module = load_script_module()
    data_path = tmp_path / "EUR_USD_quotes.csv"
    output_dir = tmp_path / "validation"
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

    exit_code = module.main(
        [
            "--data",
            str(data_path),
            "--expected-interval-minutes",
            "1",
            "--output-dir",
            str(output_dir),
        ]
    )

    assert exit_code == 0
    assert "Status: `PASS`" in capsys.readouterr().out
    assert (output_dir / "data_quality_report.md").exists()
    assert (output_dir / "data_quality_report.csv").exists()


def test_validator_cli_reports_missing_file_as_blocked(tmp_path: Path, capsys) -> None:
    module = load_script_module()
    missing_path = tmp_path / "missing.csv"

    exit_code = module.main(["--data", str(missing_path), "--data-kind", "bidask_candles"])

    output = capsys.readouterr().out
    assert exit_code == 2
    assert "Validation blocked: data file not found" in output
    assert "Do not use mock or synthetic data as trading evidence" in output
