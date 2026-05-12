import json
from datetime import datetime, timezone
from decimal import Decimal

from forex_bot.monitoring.reporting import ReportTrade, build_performance_report


def test_performance_report_groups_key_forex_metrics(tmp_path) -> None:
    trades = [
        ReportTrade(
            pair="EUR_USD",
            strategy="Trend",
            session="new_york",
            opened_at=datetime(2026, 1, 5, 14, tzinfo=timezone.utc),
            closed_at=datetime(2026, 1, 5, 15, tzinfo=timezone.utc),
            pnl=Decimal("20"),
            spread_pips=Decimal("1.2"),
            slippage_pips=Decimal("0.2"),
        ),
        ReportTrade(
            pair="USD_JPY",
            strategy="Trend",
            session="asian",
            opened_at=datetime(2026, 1, 6, 1, tzinfo=timezone.utc),
            closed_at=datetime(2026, 1, 6, 2, tzinfo=timezone.utc),
            pnl=Decimal("-10"),
            spread_pips=Decimal("1.0"),
            slippage_pips=Decimal("0.4"),
            news_window=True,
            rollover_exposure=True,
        ),
    ]

    report = build_performance_report(equity_curve=[10000, 10020, 10010], trades=trades)

    assert report.total_return == Decimal("0.001")
    assert report.performance_by_pair["EUR_USD"]["pnl"] == Decimal("20")
    assert report.performance_by_session["asian"]["pnl"] == Decimal("-10")
    assert report.average_spread_paid == Decimal("1.1")
    assert report.average_slippage == Decimal("0.3")
    assert report.news_window_losses == Decimal("-10")
    assert report.rollover_exposure == Decimal("10")

    report.export_json(tmp_path / "report.json")
    report.export_csv(tmp_path / "csv")

    payload = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert payload["performance_by_pair"]["USD_JPY"]["pnl"] == -10.0
    assert (tmp_path / "csv" / "trades.csv").exists()
    assert (tmp_path / "csv" / "performance_by_session.csv").exists()
