"""Import OANDA bid/ask candles into the repo's historical data schema."""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]

PRACTICE_URL = "https://api-fxpractice.oanda.com"
LIVE_URL = "https://api-fxtrade.oanda.com"
DEFAULT_INSTRUMENT = "EUR_USD"
DEFAULT_GRANULARITY = "H1"
DEFAULT_FROM = "2020-01-01T00:00:00Z"
DEFAULT_TO = "2025-12-31T23:00:00Z"
DEFAULT_OUTPUT = "data/historical/EUR_USD_H1_bidask_2020_2025.csv"
DEFAULT_VALIDATION_OUTPUT = "reports/data_validation/EUR_USD_H1_bidask"
OANDA_MAX_COUNT = 5000
SAFE_CHUNK_COUNT = 4900
CSV_FIELDS = [
    "timestamp",
    "pair",
    "bid_open",
    "bid_high",
    "bid_low",
    "bid_close",
    "ask_open",
    "ask_high",
    "ask_low",
    "ask_close",
    "volume",
]


JsonFetcher = Callable[[str, str], dict]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Import OANDA REST v20 bid/ask candles.")
    parser.add_argument("--instrument", default=DEFAULT_INSTRUMENT)
    parser.add_argument("--from", dest="start", default=DEFAULT_FROM)
    parser.add_argument("--to", dest="end", default=DEFAULT_TO)
    parser.add_argument("--granularity", default=DEFAULT_GRANULARITY)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--max-spread-pips", default="10")
    parser.add_argument("--validation-output-dir", default=DEFAULT_VALIDATION_OUTPUT)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        api_key = require_api_key(os.environ)
        base_url = base_url_for_env(os.environ.get("OANDA_ENV", "practice"))
        start = parse_utc_timestamp(args.start)
        end = parse_utc_timestamp(args.end)
        rows = fetch_candles(
            api_key=api_key,
            base_url=base_url,
            instrument=args.instrument,
            granularity=args.granularity,
            start=start,
            end=end,
        )
        output_path = Path(args.output)
        write_candles_csv(rows, output_path)
        print(f"Wrote {len(rows)} complete bid/ask candles to {output_path}")
        return run_validation(
            output_path=output_path,
            granularity=args.granularity,
            max_spread_pips=args.max_spread_pips,
            output_dir=Path(args.validation_output_dir),
        )
    except (OandaImportError, ValueError, FileNotFoundError) as exc:
        print(f"OANDA import failed: {exc}", file=sys.stderr)
        return 1


class OandaImportError(RuntimeError):
    """Raised when OANDA import cannot safely continue."""


def require_api_key(environ: dict[str, str]) -> str:
    api_key = environ.get("OANDA_API_KEY", "").strip()
    if not api_key:
        raise OandaImportError("OANDA_API_KEY is not set")
    return api_key


def base_url_for_env(value: str | None) -> str:
    env = (value or "practice").strip().lower()
    if env == "practice":
        return PRACTICE_URL
    if env == "live":
        return LIVE_URL
    raise OandaImportError("OANDA_ENV must be practice or live")


def fetch_candles(
    *,
    api_key: str,
    base_url: str,
    instrument: str,
    granularity: str,
    start: datetime,
    end: datetime,
    fetch_json: JsonFetcher = None,
) -> list[dict[str, str]]:
    if end <= start:
        raise ValueError("--to must be after --from")
    fetch = fetch_json or request_json
    rows: list[dict[str, str]] = []
    seen_timestamps: set[str] = set()
    for chunk_start, chunk_end in iter_time_chunks(start, end, granularity):
        url = build_candles_url(
            base_url=base_url,
            instrument=instrument,
            granularity=granularity,
            start=chunk_start,
            end=chunk_end,
        )
        response = fetch(url, api_key)
        rows.extend(parse_response_candles(response, instrument, seen_timestamps))
    rows.sort(key=lambda row: row["timestamp"])
    return rows


def iter_time_chunks(
    start: datetime,
    end: datetime,
    granularity: str,
    *,
    max_count: int = SAFE_CHUNK_COUNT,
) -> list[tuple[datetime, datetime]]:
    if max_count >= OANDA_MAX_COUNT:
        raise ValueError("max_count must stay below OANDA's 5000 candle limit")
    step = granularity_delta(granularity)
    chunk_span = step * max_count
    chunks: list[tuple[datetime, datetime]] = []
    current = start
    while current < end:
        chunk_end = min(current + chunk_span, end)
        chunks.append((current, chunk_end))
        current = chunk_end
    return chunks


def granularity_delta(granularity: str) -> timedelta:
    normalized = granularity.upper()
    if normalized == "H1":
        return timedelta(hours=1)
    if normalized.startswith("M") and normalized[1:].isdigit():
        return timedelta(minutes=int(normalized[1:]))
    if normalized.startswith("H") and normalized[1:].isdigit():
        return timedelta(hours=int(normalized[1:]))
    raise ValueError(f"unsupported granularity for deterministic chunking: {granularity}")


def build_candles_url(
    *,
    base_url: str,
    instrument: str,
    granularity: str,
    start: datetime,
    end: datetime,
) -> str:
    params = urlencode(
        {
            "price": "BA",
            "granularity": granularity,
            "from": format_utc_timestamp(start),
            "to": format_utc_timestamp(end),
        }
    )
    return f"{base_url}/v3/instruments/{instrument}/candles?{params}"


def request_json(url: str, api_key: str) -> dict:
    request = Request(
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept-Datetime-Format": "RFC3339",
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise OandaImportError(f"OANDA HTTP {exc.code}: {details}") from exc
    except URLError as exc:
        raise OandaImportError(f"OANDA request failed: {exc.reason}") from exc


def parse_response_candles(
    response: dict,
    instrument: str,
    seen_timestamps: set[str] | None = None,
) -> list[dict[str, str]]:
    seen = seen_timestamps if seen_timestamps is not None else set()
    rows: list[dict[str, str]] = []
    for candle in response.get("candles", []):
        row = parse_candle(candle, instrument)
        if row is None:
            continue
        timestamp = row["timestamp"]
        if timestamp in seen:
            continue
        seen.add(timestamp)
        rows.append(row)
    return rows


def parse_candle(candle: dict, instrument: str) -> dict[str, str] | None:
    if not candle.get("complete", False):
        return None
    bid = candle.get("bid")
    ask = candle.get("ask")
    if bid is None or ask is None:
        raise OandaImportError("complete candle is missing bid or ask data")
    for side_name, side in (("bid", bid), ("ask", ask)):
        missing = sorted({"o", "h", "l", "c"} - set(side))
        if missing:
            raise OandaImportError(f"complete candle {side_name} data missing fields: {', '.join(missing)}")
    return {
        "timestamp": format_utc_timestamp(parse_utc_timestamp(str(candle["time"]))),
        "pair": instrument,
        "bid_open": str(bid["o"]),
        "bid_high": str(bid["h"]),
        "bid_low": str(bid["l"]),
        "bid_close": str(bid["c"]),
        "ask_open": str(ask["o"]),
        "ask_high": str(ask["h"]),
        "ask_low": str(ask["l"]),
        "ask_close": str(ask["c"]),
        "volume": str(candle.get("volume", "0")),
    }


def write_candles_csv(rows: list[dict[str, str]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def run_validation(
    *,
    output_path: Path,
    granularity: str,
    max_spread_pips: str,
    output_dir: Path,
) -> int:
    command = [
        sys.executable,
        str(ROOT / "scripts" / "validate_market_data.py"),
        "--data",
        str(output_path),
        "--data-kind",
        "bidask_candles",
        "--expected-interval-minutes",
        str(int(granularity_delta(granularity).total_seconds() // 60)),
        "--max-spread-pips",
        max_spread_pips,
        "--output-dir",
        str(output_dir),
    ]
    completed = subprocess.run(command, check=False)
    return completed.returncode


def parse_utc_timestamp(value: str) -> datetime:
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    if "." in normalized:
        prefix, suffix = normalized.split(".", 1)
        if "+" in suffix:
            fraction, offset = suffix.split("+", 1)
            normalized = f"{prefix}.{fraction[:6].ljust(6, '0')}+{offset}"
        elif "-" in suffix:
            fraction, offset = suffix.split("-", 1)
            normalized = f"{prefix}.{fraction[:6].ljust(6, '0')}-{offset}"
    timestamp = datetime.fromisoformat(normalized)
    if timestamp.tzinfo is None:
        raise ValueError(f"timestamp must include timezone: {value}")
    return timestamp.astimezone(timezone.utc)


def format_utc_timestamp(timestamp: datetime) -> str:
    return timestamp.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


if __name__ == "__main__":
    raise SystemExit(main())
