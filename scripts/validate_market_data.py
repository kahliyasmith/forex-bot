"""Validate historical forex market data before backtesting."""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Literal

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from forex_bot.data.models import CurrencyPair
from forex_bot.monitoring.reporting import decimal_to_json

DataKind = Literal["quotes", "candles"]


@dataclass(frozen=True)
class ValidationIssue:
    severity: str
    check: str
    row: int | None
    pair: str | None
    timestamp: str | None
    message: str


@dataclass(frozen=True)
class ValidationResult:
    path: Path
    data_kind: DataKind
    rows: int
    pairs: list[str]
    start: datetime | None
    end: datetime | None
    issues: list[ValidationIssue]

    @property
    def passed(self) -> bool:
        return not any(issue.severity == "error" for issue in self.issues)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate forex CSV market data.")
    parser.add_argument("--data", required=True, help="CSV data file to validate.")
    parser.add_argument("--data-kind", choices=["auto", "quotes", "candles"], default="auto")
    parser.add_argument(
        "--expected-interval-minutes",
        type=int,
        help="Expected interval for candle/quote timestamps per pair. Enables missing-gap checks.",
    )
    parser.add_argument("--max-spread-pips", default="10")
    parser.add_argument("--max-gap-pct", default="5")
    parser.add_argument("--output-dir", help="Optional directory for validation CSV and Markdown report.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = validate_csv(
        Path(args.data),
        data_kind=args.data_kind,
        expected_interval=(
            timedelta(minutes=args.expected_interval_minutes)
            if args.expected_interval_minutes
            else None
        ),
        max_spread_pips=Decimal(args.max_spread_pips),
        max_gap_pct=Decimal(args.max_gap_pct),
    )
    print(render_markdown(result))
    if args.output_dir:
        write_reports(result, Path(args.output_dir))
    return 0 if result.passed else 1


def validate_csv(
    path: Path,
    *,
    data_kind: str = "auto",
    expected_interval: timedelta | None = None,
    max_spread_pips: Decimal = Decimal("10"),
    max_gap_pct: Decimal = Decimal("5"),
) -> ValidationResult:
    with path.open("r", newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        if reader.fieldnames is None:
            raise ValueError(f"{path} has no header row")
        headers = [header.strip().lower() for header in reader.fieldnames]
        rows = [
            {key.strip().lower(): (value.strip() if value is not None else "") for key, value in row.items()}
            for row in reader
        ]

    detected_kind = detect_data_kind(headers) if data_kind == "auto" else data_kind
    issues: list[ValidationIssue] = []
    required_columns = required_columns_for(detected_kind)
    missing = sorted(required_columns - set(headers))
    for column in missing:
        issues.append(issue("error", "required_columns", None, None, None, f"missing column: {column}"))

    parsed_rows: list[dict[str, object]] = []
    for index, row in enumerate(rows, start=2):
        parsed = parse_row(row, detected_kind, index)
        issues.extend(parsed.pop("issues"))
        parsed_rows.append(parsed)

    issues.extend(check_duplicates(parsed_rows))
    issues.extend(check_monotonicity(parsed_rows))
    issues.extend(check_expected_intervals(parsed_rows, expected_interval))
    issues.extend(check_weekend_rows(parsed_rows))
    issues.extend(check_large_price_gaps(parsed_rows, max_gap_pct))
    if detected_kind == "quotes":
        issues.extend(check_spreads(parsed_rows, max_spread_pips))

    timestamps = [row["timestamp"] for row in parsed_rows if isinstance(row.get("timestamp"), datetime)]
    pairs = sorted({str(row["pair"]) for row in parsed_rows if row.get("pair")})
    return ValidationResult(
        path=path,
        data_kind=detected_kind,
        rows=len(rows),
        pairs=pairs,
        start=min(timestamps, key=timestamp_check_value) if timestamps else None,
        end=max(timestamps, key=timestamp_check_value) if timestamps else None,
        issues=issues,
    )


def detect_data_kind(headers: list[str]) -> DataKind:
    header_set = set(headers)
    if {"timestamp", "pair", "bid", "ask"}.issubset(header_set) or {
        "timestamp",
        "symbol",
        "bid",
        "ask",
    }.issubset(header_set):
        return "quotes"
    if {"timestamp", "open", "high", "low", "close"}.issubset(header_set) and (
        "pair" in header_set or "symbol" in header_set
    ):
        return "candles"
    raise ValueError("CSV must contain either quote or candle columns")


def required_columns_for(data_kind: DataKind) -> set[str]:
    if data_kind == "quotes":
        return {"timestamp", "bid", "ask"}
    return {"timestamp", "open", "high", "low", "close"}


def parse_row(row: dict[str, str], data_kind: DataKind, index: int) -> dict[str, object]:
    issues: list[ValidationIssue] = []
    pair_raw = row.get("pair") or row.get("symbol") or ""
    timestamp_raw = row.get("timestamp") or ""
    pair = None
    timestamp = None
    try:
        pair = CurrencyPair.parse(pair_raw).symbol
    except ValueError as exc:
        issues.append(issue("error", "symbol_naming", index, pair_raw, timestamp_raw, str(exc)))
    try:
        timestamp = parse_timestamp(timestamp_raw)
        if timestamp.tzinfo is None:
            issues.append(issue("error", "timezone", index, pair, timestamp_raw, "timestamp is timezone-naive"))
    except ValueError as exc:
        issues.append(issue("error", "timestamp_parse", index, pair, timestamp_raw, str(exc)))

    parsed: dict[str, object] = {
        "row": index,
        "pair": pair,
        "timestamp": timestamp,
        "issues": issues,
    }
    if data_kind == "quotes":
        bid = parse_decimal(row.get("bid", ""), "bid", index, pair, timestamp_raw, issues)
        ask = parse_decimal(row.get("ask", ""), "ask", index, pair, timestamp_raw, issues)
        parsed.update({"bid": bid, "ask": ask})
        if bid is not None and ask is not None:
            if bid <= 0 or ask <= 0:
                issues.append(issue("error", "bad_prices", index, pair, timestamp_raw, "bid/ask must be positive"))
            if ask < bid:
                issues.append(issue("error", "crossed_market", index, pair, timestamp_raw, "ask is below bid"))
    else:
        prices = {
            name: parse_decimal(row.get(name, ""), name, index, pair, timestamp_raw, issues)
            for name in ("open", "high", "low", "close")
        }
        parsed.update(prices)
        parsed["volume"] = parse_decimal(row.get("volume", "0"), "volume", index, pair, timestamp_raw, issues)
        if all(value is not None for value in prices.values()):
            open_ = prices["open"]
            high = prices["high"]
            low = prices["low"]
            close = prices["close"]
            if min(open_, high, low, close) <= 0:
                issues.append(issue("error", "bad_prices", index, pair, timestamp_raw, "OHLC prices must be positive"))
            if high < max(open_, close) or low > min(open_, close) or high < low:
                issues.append(issue("error", "ohlc_consistency", index, pair, timestamp_raw, "OHLC high/low are inconsistent"))
    return parsed


def parse_timestamp(value: str) -> datetime:
    timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if timestamp.tzinfo is None:
        return timestamp
    return timestamp.astimezone(timezone.utc)


def timestamp_check_value(timestamp: datetime) -> datetime:
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        return timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(timezone.utc)


def parse_decimal(
    value: str,
    field: str,
    row: int,
    pair: str | None,
    timestamp: str | None,
    issues: list[ValidationIssue],
) -> Decimal | None:
    try:
        return Decimal(value)
    except (InvalidOperation, ValueError):
        issues.append(issue("error", "numeric_parse", row, pair, timestamp, f"{field} is not numeric"))
        return None


def check_duplicates(rows: list[dict[str, object]]) -> list[ValidationIssue]:
    seen: set[tuple[str, datetime]] = set()
    issues: list[ValidationIssue] = []
    for row in rows:
        pair = row.get("pair")
        timestamp = row.get("timestamp")
        if not isinstance(pair, str) or not isinstance(timestamp, datetime):
            continue
        key = (pair, timestamp_check_value(timestamp))
        if key in seen:
            issues.append(issue("error", "duplicate_timestamp", row["row"], pair, timestamp.isoformat(), "duplicate pair/timestamp"))
        seen.add(key)
    return issues


def check_monotonicity(rows: list[dict[str, object]]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    by_pair = group_by_pair(rows)
    for pair, pair_rows in by_pair.items():
        last_timestamp: datetime | None = None
        for row in pair_rows:
            timestamp = row.get("timestamp")
            if not isinstance(timestamp, datetime):
                continue
            timestamp_value = timestamp_check_value(timestamp)
            if last_timestamp is not None and timestamp_value < last_timestamp:
                issues.append(issue("error", "non_monotonic", row["row"], pair, timestamp.isoformat(), "timestamp moved backward"))
            last_timestamp = timestamp_value
    return issues


def check_expected_intervals(
    rows: list[dict[str, object]],
    expected_interval: timedelta | None,
) -> list[ValidationIssue]:
    if expected_interval is None:
        return []
    issues: list[ValidationIssue] = []
    for pair, pair_rows in group_by_pair(rows).items():
        timestamps = [timestamp_check_value(row["timestamp"]) for row in pair_rows if isinstance(row.get("timestamp"), datetime)]
        for previous, current in zip(timestamps, timestamps[1:]):
            gap = current - previous
            if gap > expected_interval * 1.5:
                issues.append(issue("warning", "missing_interval", None, pair, current.isoformat(), f"gap detected: {gap}"))
    return issues


def check_weekend_rows(rows: list[dict[str, object]]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for row in rows:
        timestamp = row.get("timestamp")
        if isinstance(timestamp, datetime) and timestamp.weekday() in {5, 6}:
            issues.append(issue("warning", "weekend_row", row["row"], row.get("pair"), timestamp.isoformat(), "weekend timestamp present"))
    return issues


def check_large_price_gaps(rows: list[dict[str, object]], max_gap_pct: Decimal) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for pair, pair_rows in group_by_pair(rows).items():
        previous_close: Decimal | None = None
        for row in pair_rows:
            price = row.get("close") or row.get("bid")
            if not isinstance(price, Decimal):
                continue
            if previous_close and previous_close > 0:
                gap_pct = abs(price - previous_close) / previous_close * Decimal("100")
                if gap_pct > max_gap_pct:
                    timestamp = row.get("timestamp")
                    issues.append(issue("warning", "large_price_gap", row["row"], pair, timestamp.isoformat() if isinstance(timestamp, datetime) else None, f"gap {gap_pct:.4f}%"))
            previous_close = price
    return issues


def check_spreads(rows: list[dict[str, object]], max_spread_pips: Decimal) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for row in rows:
        pair_raw = row.get("pair")
        bid = row.get("bid")
        ask = row.get("ask")
        timestamp = row.get("timestamp")
        if not isinstance(pair_raw, str) or not isinstance(bid, Decimal) or not isinstance(ask, Decimal):
            continue
        if ask < bid:
            continue
        pair = CurrencyPair.parse(pair_raw)
        spread_pips = (ask - bid) / pair.pip_size
        if spread_pips > max_spread_pips:
            issues.append(issue("warning", "unrealistic_spread", row["row"], pair.symbol, timestamp.isoformat() if isinstance(timestamp, datetime) else None, f"spread {spread_pips} pips exceeds {max_spread_pips}"))
    return issues


def group_by_pair(rows: list[dict[str, object]]) -> dict[str, list[dict[str, object]]]:
    grouped: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        pair = row.get("pair")
        if isinstance(pair, str):
            grouped.setdefault(pair, []).append(row)
    return grouped


def issue(
    severity: str,
    check: str,
    row: int | None,
    pair: str | None,
    timestamp: str | None,
    message: str,
) -> ValidationIssue:
    return ValidationIssue(severity, check, row, pair, timestamp, message)


def render_markdown(result: ValidationResult) -> str:
    lines = [
        "# Market Data Validation",
        "",
        f"File: `{result.path}`",
        f"Data kind: `{result.data_kind}`",
        f"Rows: `{result.rows}`",
        f"Pairs: `{', '.join(result.pairs) if result.pairs else 'none'}`",
        f"Start: `{result.start.isoformat() if result.start else 'n/a'}`",
        f"End: `{result.end.isoformat() if result.end else 'n/a'}`",
        f"Status: `{'PASS' if result.passed else 'FAIL'}`",
        "",
        "Mock or synthetic data is only for tooling validation and is not market evidence.",
        "",
        "## Issues",
        "",
    ]
    if not result.issues:
        lines.append("No issues found.")
    else:
        lines.append("| Severity | Check | Row | Pair | Timestamp | Message |")
        lines.append("| --- | --- | --- | --- | --- | --- |")
        for item in result.issues:
            lines.append(
                f"| {item.severity} | {item.check} | {item.row or ''} | {item.pair or ''} | {item.timestamp or ''} | {item.message} |"
            )
    return "\n".join(lines) + "\n"


def write_reports(result: ValidationResult, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "data_quality_report.md").write_text(render_markdown(result), encoding="utf-8")
    rows = [
        {
            "severity": item.severity,
            "check": item.check,
            "row": item.row,
            "pair": item.pair,
            "timestamp": item.timestamp,
            "message": item.message,
        }
        for item in result.issues
    ]
    if not rows:
        rows = [{"severity": "info", "check": "no_issues", "row": "", "pair": "", "timestamp": "", "message": "No issues found"}]
    with (output_dir / "data_quality_report.csv").open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(decimal_to_json(rows))


if __name__ == "__main__":
    raise SystemExit(main())
