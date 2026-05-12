# Data Quality Report

Run ID: `20260512_144721_audit_campaign`

Data evidence status: `BLOCKED`

Reason: no historical market data present.

## Inventory

Real historical market data files found: `0`

Configured pairs needing data:

- `EUR_USD`
- `GBP_USD`
- `USD_JPY`

Available real date ranges: none.

Available real timeframes: none.

Available real data type: none.

Bid/ask availability: none.

Spread availability: none.

Commission/swap documentation: none.

## Framework Validation Data

Mock fixture created:

- `mock_data/EUR_USD_H1_mock.csv`

Validator result for mock fixture: `PASS`

The mock fixture contains 21 synthetic hourly candle rows from `2026-01-05T14:00:00Z` through `2026-01-06T10:00:00Z`.

This file is not market data. It exists only to validate that the data validator, backtest runner, and walk-forward runner can process valid-shaped CSV input.

## Required Checks Once Real Data Is Added

Each real dataset must pass checks for:

- Required columns.
- Timestamp parseability.
- UTC or explicit timezone.
- Monotonic timestamps per pair.
- Duplicate pair/timestamp rows.
- Missing candles or tick gaps.
- Weekend and broker-session handling.
- Zero or negative prices.
- OHLC high/low consistency for candle data.
- Crossed bid/ask quotes.
- Unrealistic spreads.
- Large price gaps.
- Date range coverage.
- Pair naming consistency.

## Current Finding

The campaign cannot evaluate market behavior. Data quality is not merely weak; it is absent.

Status: `BLOCKED_BY_NO_MARKET_DATA`
