# DATA_WARNING_TRIAGE.md

Status: DATA_WARNING_TRIAGE_READY

Validation source:

- Report directory: `reports/data_validation/EUR_USD_H1_bidask/`
- CSV report: `reports/data_validation/EUR_USD_H1_bidask/data_quality_report.csv`
- Markdown report: `reports/data_validation/EUR_USD_H1_bidask/data_quality_report.md`
- Dataset validated: `data/historical/EUR_USD_H1_bidask_2020_2025.csv`
- Pair: `EUR_USD`
- Timeframe: `H1`
- Rows: `37,357`
- Range: `2020-01-01T22:00:00Z` to `2025-12-31T21:00:00Z`
- Validation status: `PASS`

This triage does not modify the raw CSV, strategy logic, or strategy parameters. It does not make any profitability or trading-edge claim.

## Warning Summary

The validation report contains `1,135` warnings and no errors.

| Warning type | Count | Triage |
| --- | ---: | --- |
| `missing_interval` | 318 | Mostly expected FX weekend/session or holiday closures, with two weekday intraday gaps requiring review. |
| `weekend_row` | 817 | All are Sunday UTC rows during FX week-open hours; no Saturday rows were reported. |

Because the report contains no errors, validation status remains `PASS`.

## Missing Interval Triage

The `318` missing interval warnings break down as:

| Category | Count | Assessment |
| --- | ---: | --- |
| Weekend/session reopen gaps | 309 | Expected for an H1 forex dataset that pauses between Friday close and Sunday evening UTC reopen. |
| Delayed week-open/session gap | 1 | `2021-11-22T00:00:00Z`, gap `2 days, 3:00:00`; appears to be a weekend/session-close gap with a delayed Monday UTC reopen. |
| Holiday market closures | 6 | Christmas/New Year style market closures; explainable but should be documented in backtest assumptions. |
| Normal weekday intraday gaps | 2 | Requires review before strong evidence claims. |

Normal weekday intraday gaps:

| Timestamp | Day | Hour UTC | Gap |
| --- | --- | ---: | --- |
| `2022-05-12T08:00:00Z` | Thursday | 8 | `3:00:00` |
| `2024-05-20T17:00:00Z` | Monday | 17 | `3:00:00` |

Holiday/market-closure gaps:

| Timestamp | Day | Gap |
| --- | --- | --- |
| `2022-12-26T22:00:00Z` | Monday | `3 days, 1:00:00` |
| `2023-12-25T22:00:00Z` | Monday | `3 days, 1:00:00` |
| `2024-01-01T22:00:00Z` | Monday | `3 days, 1:00:00` |
| `2024-12-25T22:00:00Z` | Wednesday | `1 day, 1:00:00` |
| `2025-01-01T22:00:00Z` | Wednesday | `1 day, 1:00:00` |
| `2025-12-25T22:00:00Z` | Thursday | `1 day, 1:00:00` |

## Weekend Row Triage

The `817` weekend row warnings break down as:

| Weekend row category | Count |
| --- | ---: |
| Sunday rows | 817 |
| Saturday rows | 0 |

Sunday UTC hour distribution:

| UTC hour | Count |
| ---: | ---: |
| 21 | 201 |
| 22 | 307 |
| 23 | 309 |

These rows are consistent with FX Sunday evening market reopen behavior in UTC, including seasonal open-hour shifts. They should not be removed only because the UTC date is Sunday.

## Blocking Assessment

These warnings do not block backtesting infrastructure execution, and they do not invalidate the validator result. The validation status remains `PASS`.

They do block strong evidence claims until the assumptions are documented and the two weekday intraday gaps are reviewed. Any backtest using this dataset should state that:

- Sunday UTC rows are expected FX week-open rows, not automatically bad weekend data.
- Holiday closures are expected market closures and should be modeled as non-trading periods.
- The two weekday intraday gaps may slightly affect indicator continuity, stop/take-profit simulation, and trade opportunity counts.
- No trading edge is proven by data validation or by the prior smoke backtest.

## Row Removal Decision

No data rows should be removed from the raw CSV based on this triage.

The Sunday rows are explainable FX session behavior. The holiday gaps are explainable market closures. The two weekday intraday gaps should be documented and reviewed against the original OANDA export or re-imported if needed, but the current evidence does not justify editing or deleting rows.

## Next Milestone

Next milestone: `WALK_FORWARD_EVIDENCE_READY`

Before claiming stronger evidence, complete:

- Broker/session calendar handling so Sunday FX open rows are not treated as generic weekend anomalies.
- Review or re-fetch around the two normal weekday intraday gaps.
- Walk-forward testing with chronological splits and the warning assumptions included in every report.
- Keep profitability and edge status as `UNKNOWN / NOT PROVEN` until walk-forward evidence exists.
