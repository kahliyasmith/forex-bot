"""Structured trade decision journal."""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from forex_bot.monitoring.reporting import decimal_to_json


@dataclass(frozen=True)
class TradeDecisionRecord:
    timestamp: datetime
    pair: str
    strategy: str
    signal: str | None
    bid: Decimal
    ask: Decimal
    spread: Decimal
    session: str
    news_filter_status: str
    risk_decision: str
    position_size: Decimal
    order_result: str
    stop_loss: Decimal | None
    take_profit: Decimal | None
    rejection_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return decimal_to_json(asdict(self))  # type: ignore[return-value]


class TradeJournal:
    def __init__(self, jsonl_path: str | Path, csv_path: str | Path) -> None:
        self.jsonl_path = Path(jsonl_path)
        self.csv_path = Path(csv_path)
        self.records: list[TradeDecisionRecord] = []
        self.jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        self.csv_path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, entry: TradeDecisionRecord) -> None:
        self.records.append(entry)
        with self.jsonl_path.open("a", encoding="utf-8") as jsonl_file:
            jsonl_file.write(json.dumps(entry.to_dict(), sort_keys=True) + "\n")
        self._rewrite_csv()

    def _rewrite_csv(self) -> None:
        if not self.records:
            return
        rows = [record.to_dict() for record in self.records]
        with self.csv_path.open("w", newline="", encoding="utf-8") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)


def make_decision_record(
    *,
    pair: str,
    strategy: str,
    signal: str | None,
    bid: Decimal,
    ask: Decimal,
    spread: Decimal,
    session: str,
    news_filter_status: str,
    risk_decision: str,
    position_size: Decimal,
    order_result: str,
    stop_loss: Decimal | None,
    take_profit: Decimal | None,
    rejection_reason: str | None = None,
    timestamp: datetime | None = None,
) -> TradeDecisionRecord:
    return TradeDecisionRecord(
        timestamp=timestamp or datetime.now(timezone.utc),
        pair=pair,
        strategy=strategy,
        signal=signal,
        bid=bid,
        ask=ask,
        spread=spread,
        session=session,
        news_filter_status=news_filter_status,
        risk_decision=risk_decision,
        position_size=position_size,
        order_result=order_result,
        stop_loss=stop_loss,
        take_profit=take_profit,
        rejection_reason=rejection_reason,
    )
