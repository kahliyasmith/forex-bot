# Historical Data Requirements

Run ID: `20260512_144721_audit_campaign`

Purpose: define the exact data needed for a valid forex backtest campaign.

## Required Symbols

Minimum first campaign:

- `EUR_USD`
- `GBP_USD`
- `USD_JPY`

Additional symbols can be added later, but they must be declared before testing. Do not cherry-pick symbols after seeing performance.

## Required Date Range

Minimum acceptable history:

- At least 2 full years per pair for a first low-confidence campaign.

Preferred audit history:

- 2020-01-01 through 2025-12-31 or longer.

Split requirement:

- Chronological only.
- Keep a final untouched out-of-sample period, preferably the most recent 15% to 25% of history.
- Do not use the final out-of-sample period for parameter selection.

## Required Granularity

Data-quality priority order:

1. Tick-level bid/ask data from the same broker or venue intended for live trading.
2. High-quality broker historical bid/ask candle data.
3. Tick data from a reputable external forex data source.
4. OHLCV candle data with realistic spread/cost modeling.
5. Mid-price OHLC only as low-confidence research data.

The current `trend_pullback` strategy is candle-driven, so H1 or lower candle data can run the first campaign. For audit-grade stop/limit and spread-sensitive evaluation, preserve bid/ask history rather than mid-only OHLC.

## Required Columns

Current runner quote CSV:

```csv
timestamp,pair,bid,ask
```

Current runner candle CSV:

```csv
timestamp,pair,open,high,low,close,volume
```

Supported bid/ask candle CSV:

```csv
timestamp,pair,bid_open,bid_high,bid_low,bid_close,ask_open,ask_high,ask_low,ask_close,volume
```

Tick data preferred columns:

```csv
timestamp,pair,bid,ask,bid_size,ask_size
```

`bid_size` and `ask_size` may be blank if the source does not provide top-of-book size.

## Timestamp Requirements

- ISO-8601 format.
- UTC preferred, with timezone included.
- Examples: `2020-01-02T14:30:00Z`, `2020-01-02T14:30:00+00:00`.
- No timezone-naive timestamps for audit-grade data.
- DST conversion must be handled by the data vendor or documented before import.

## Spread Requirements

Required for preferred datasets:

- Real bid and ask fields.
- Spread derivable for every row.
- Pair-specific spread distributions preserved.

If only candle or mid data is available:

- Document assumed spread by pair and session.
- Run normal, conservative, and harsh spread assumptions.
- Mark the campaign lower confidence.

## Commission Requirements

Document:

- Commission per side or round turn.
- Whether spread includes broker markup.
- Account type used for the assumption.
- Effective commission by notional size if tiered.

## Swap/Rollover Requirements

Document:

- Swap by pair and direction.
- Broker rollover time.
- Triple-swap weekday.
- Whether swap changes over the sample period.

If exact historical swap is unavailable, use a conservative documented approximation and mark results lower confidence.

## Volume Requirements

Forex spot volume is usually tick volume, not exchange volume.

Acceptable:

- Tick volume from broker candles.
- Null volume for tick bid/ask data if source does not provide size.

Required documentation:

- Whether volume means tick count, quote count, real venue volume, or unavailable.

## Broker And Account Assumptions

Required before evidence-quality runs:

- Broker or venue source.
- Account currency: `USD`.
- Account type: demo/practice/live-like pricing.
- Typical spread by pair and session.
- Commission model.
- Swap model.
- Leverage and margin rules.
- Minimum order size and lot increment.
- Minimum stop distance.
- Trading session hours and weekend close/open.
- Whether orders can be rejected during news, rollover, or illiquid periods.

## Minimum Trade Count Target

First confidence target:

- At least 100 completed trades overall.
- At least 30 completed trades per major pair if making pair-specific claims.
- At least 30 completed trades per session if making session-specific claims.

If trade count is lower, results may still be useful for debugging but should be labeled inconclusive.

## Expected Repo Placement

Recommended directory:

```text
data/historical/
```

Recommended manifest:

```text
config/data_manifest.yaml
```

The manifest loader now supports `config/data_manifest.yaml`, validates manifest metadata, and rejects missing data files. Backtest scripts still accept explicit `--data` paths for direct runs.
For `bidask_candles`, the current backtest runner normalizes strategy input to mid-price candles and uses the measured average close spread as the spread assumption.

## Naming Convention

Tick bid/ask:

```text
data/historical/EUR_USD_tick_bidask_2020_2025.csv
```

H1 bid/ask candles:

```text
data/historical/EUR_USD_H1_bidask_2020_2025.csv
```

H1 mid/ohlc candles:

```text
data/historical/EUR_USD_H1_ohlcv_mid_2020_2025.csv
```

Use the repo's canonical symbol format with underscores in outputs and config. The market-data parser and manifest loader also accept compact symbols such as `EURUSD` and normalize them to `EUR_USD`.

## Validation Gate

Do not run evidence backtests until each file passes:

```powershell
python scripts\validate_market_data.py --data <file> --data-kind <quotes|candles|bidask_candles|auto> --expected-interval-minutes <minutes> --output-dir <validation_dir>
```

Any validation error must be fixed or explicitly documented before backtesting.
