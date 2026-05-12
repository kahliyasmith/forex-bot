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
