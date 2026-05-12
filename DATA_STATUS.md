# Data Status

Status: `EUR_USD_DATA_READY_VALIDATED_LOCAL`

Next milestone: `BACKTEST_SMOKE_READY`

## EUR_USD

Real OANDA `EUR_USD` H1 bid/ask candle data has been imported and validated locally.

- File: `data/historical/EUR_USD_H1_bidask_2020_2025.csv`
- Rows: `37,357`
- Range: `2020-01-01T22:00:00Z` to `2025-12-31T21:00:00Z`
- Validation result: `PASS`
- Validation report: `reports/data_validation/EUR_USD_H1_bidask/`

The raw CSV and validation report are intentionally not committed. They are local data artifacts and are ignored by git.

## Evidence Boundary

Strategy edge is still unknown. This data validation proves only that the EUR_USD historical file is structurally usable for the next backtest smoke step.

Before making strong evidence claims, review:

- `318` missing interval warnings.
- `817` weekend row warnings.

Do not claim profitability or trading edge from data validation alone.
