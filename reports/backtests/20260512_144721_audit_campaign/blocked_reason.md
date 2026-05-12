# Blocked Reason

Run ID: `20260512_144721_audit_campaign`

Status: `FRAMEWORK_READY_DATA_MISSING`

Backtest edge evidence: `BLOCKED`

Reason: no historical market data present.

Strategy performance: `UNKNOWN`

## What Is Blocked

The following cannot be truthfully completed:

- Durable edge assessment.
- Pair ranking.
- Session ranking.
- Market-regime ranking.
- Real drawdown estimate.
- Real win rate, profit factor, expectancy, Sharpe-like ratio, or CAGR.
- Real spread/slippage sensitivity.
- Real walk-forward conclusion.
- Tradable/promising/bad strategy classification.

## What Is Not Blocked

The following framework checks were completed separately:

- Unit tests.
- Import tests.
- Config parsing tests.
- Strategy initialization tests.
- Data validator tests.
- Backtest runner smoke path with mock data.
- Walk-forward runner smoke path with mock data.

Mock data is not market evidence.

## Exact Missing Inputs

At minimum, add real historical data for:

- `EUR_USD`
- `GBP_USD`
- `USD_JPY`

Preferred data:

- Tick-level bid/ask or broker bid/ask candles.
- UTC timestamps.
- Several years of history.
- Documented spread, commission, and swap assumptions.

See `data_requirements.md`.

## Final Determination

The repo can proceed to real-data smoke testing once data is added. It cannot claim any forex trading edge now.
