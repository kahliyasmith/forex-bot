# Backtest Smoke Report

Status: `BACKTEST_SMOKE_COMPLETED`

Next milestone: `DATA_WARNING_TRIAGE_READY`

Alternative evidence milestone after warning triage: `WALK_FORWARD_EVIDENCE_READY`

## Data

Real OANDA `EUR_USD` H1 bid/ask candle data was used.

- Data file: `data/historical/EUR_USD_H1_bidask_2020_2025.csv`
- Rows: `37,357`
- Range: `2020-01-01T22:00:00Z` to `2025-12-31T21:00:00Z`
- Validation result: `PASS`
- Validation report: `reports/data_validation/EUR_USD_H1_bidask/`

The raw CSV and generated validation report are intentionally not committed.

## Validation Warnings

The validation pass included warnings that still need triage before strong evidence claims:

- `318` missing interval warnings.
- `817` weekend row warnings.

These warnings may be normal broker-session behavior, but they must be reviewed and documented before the dataset is treated as strong evidence.

## Smoke Backtest

Smoke output directory:

```text
reports/backtests/EUR_USD_H1_real_smoke
```

Generated local outputs:

- `backtest_trades.csv`
- `performance_report.json`
- `summary.csv`
- `equity_curve.csv`
- `performance_by_pair.csv`
- `performance_by_session.csv`
- `performance_by_strategy.csv`
- `cost_stress_report.csv`
- `cost_stress_report.json`

The generated backtest output is intentionally not committed.

## Smoke Metrics

- Stress regimes: `9`
- Trades: `21`
- Total return: `-0.069790339695371684021736232`
- Max drawdown: `0.1288480106810587611680656472`
- Win rate: `0.4761904761904761904761904762`
- Profit factor: `0.6960665441244657156030242790`
- Expectancy: `-33.23349509303413524844582476`
- Average trade: `-33.23349509303413524844582476`
- Average spread paid: `1.671590331129373343683914660`
- Average slippage: `0.2`

The smoke result was negative.

## Evidence Boundary

Strategy edge remains `UNKNOWN / NOT PROVEN`.

No profitability claim can be made. This was a first smoke test on one pair and one timeframe using default strategy settings. The trade count was only `21`, which is not enough for strong statistical evidence.

Before moving to walk-forward evidence, triage the validation warnings and document whether they are expected OANDA market-session gaps or true data-quality issues.
