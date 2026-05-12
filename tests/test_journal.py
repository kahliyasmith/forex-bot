import json
from decimal import Decimal

from forex_bot.monitoring.journal import TradeJournal, make_decision_record


def test_trade_journal_writes_jsonl_and_csv(tmp_path) -> None:
    journal = TradeJournal(tmp_path / "journal.jsonl", tmp_path / "journal.csv")
    journal.record(
        make_decision_record(
            pair="EUR_USD",
            strategy="Trend",
            signal="long",
            bid=Decimal("1.1000"),
            ask=Decimal("1.1002"),
            spread=Decimal("2"),
            session="new_york",
            news_filter_status="allowed",
            risk_decision="approved",
            position_size=Decimal("10000"),
            order_result="filled",
            stop_loss=Decimal("1.0975"),
            take_profit=Decimal("1.1050"),
        )
    )

    payload = json.loads((tmp_path / "journal.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert payload["pair"] == "EUR_USD"
    assert payload["spread"] == 2.0
    assert "risk_decision" in (tmp_path / "journal.csv").read_text(encoding="utf-8")
