# Next Experiments

Run ID: `20260512_144721_audit_campaign`

Priority: acquire and validate real historical market data. Do not tune strategy parameters or interpret mock-data outputs as performance.

## 1. Add Historical Data

Place files under:

```text
data/historical/
```

Recommended first files:

```text
data/historical/EUR_USD_H1_bidask_2020_2025.csv
data/historical/GBP_USD_H1_bidask_2020_2025.csv
data/historical/USD_JPY_H1_bidask_2020_2025.csv
```

Preferred format for bid/ask candles:

```csv
timestamp,pair,bid_open,bid_high,bid_low,bid_close,ask_open,ask_high,ask_low,ask_close,volume
```

Current runner format for immediate use:

```csv
timestamp,pair,bid,ask
```

or:

```csv
timestamp,pair,open,high,low,close,volume
```

If richer bid/ask candle data is provided, add a loader adapter before treating results as audit-grade.

## 2. Validate Data

Candidate command for quote data:

```powershell
python scripts\validate_market_data.py --data data\historical\EUR_USD_tick_bidask_2020_2025.csv --data-kind quotes --expected-interval-minutes 1 --max-spread-pips 10 --output-dir reports\data_validation\EUR_USD
```

Candidate command for candle data:

```powershell
python scripts\validate_market_data.py --data data\historical\EUR_USD_H1_2020_2025.csv --data-kind candles --expected-interval-minutes 60 --max-gap-pct 5 --output-dir reports\data_validation\EUR_USD_H1
```

Repeat validation for every pair before running performance tests.

## 3. Run One Real Smoke Backtest

Use one pair, one timeframe, default parameters, and realistic costs. Example:

```powershell
python scripts\run_backtest.py --config config\bot.yaml --data data\historical\EUR_USD_H1_2020_2025.csv --data-kind candles --strategy trend_pullback --spread-pips 1.2 --slippage-pips 0.2 --commission-per-trade 0 --swap-cost-per-trade 0 --output-dir reports\backtests\real_smoke_EUR_USD_H1
```

If using quote data:

```powershell
python scripts\run_backtest.py --config config\bot.yaml --data data\historical\EUR_USD_tick_bidask_2020_2025.csv --data-kind quotes --strategy trend_pullback --slippage-pips 0.2 --commission-per-trade 0 --swap-cost-per-trade 0 --output-dir reports\backtests\real_smoke_EUR_USD_quotes
```

Note: the current trend-pullback strategy is candle-driven, so quote-data behavior should be inspected before relying on it.

## 4. Run Baseline Matrix Without Tuning

There is no campaign-level matrix runner yet. Until one is added, run explicit commands per pair/timeframe/cost regime and aggregate the resulting CSVs.

Candidate default-pair baseline commands:

```powershell
python scripts\run_backtest.py --config config\bot.yaml --data data\historical\EUR_USD_H1_2020_2025.csv --data-kind candles --strategy trend_pullback --spread-pips 1.2 --slippage-pips 0.2 --output-dir reports\backtests\baseline\EUR_USD_H1
python scripts\run_backtest.py --config config\bot.yaml --data data\historical\GBP_USD_H1_2020_2025.csv --data-kind candles --strategy trend_pullback --spread-pips 1.6 --slippage-pips 0.2 --output-dir reports\backtests\baseline\GBP_USD_H1
python scripts\run_backtest.py --config config\bot.yaml --data data\historical\USD_JPY_H1_2020_2025.csv --data-kind candles --strategy trend_pullback --spread-pips 1.4 --slippage-pips 0.2 --output-dir reports\backtests\baseline\USD_JPY_H1
```

Ranking rule: rank by out-of-sample robustness, realistic execution, sufficient trade count, drawdown control, and consistency across pairs/timeframes. Do not rank by total profit alone.

## 5. Run Walk-Forward Validation

Candidate command after adding sufficient candle history:

```powershell
python scripts\run_walkforward.py --config config\bot.yaml --data data\historical\EUR_USD_H1_2020_2025.csv --data-kind candles --train-window-size 1000 --test-window-size 250 --step-size 250 --trend-ma-periods 5,10,20 --pullback-lookbacks 2,3,5 --atr-periods 3,7,14 --atr-multipliers 1.0,1.5,2.0 --reward-r-multiples 1.5,2.0,3.0 --spread-pips 1.2 --slippage-pips 0.2 --output-dir reports\walkforward\EUR_USD_H1
```

Keep a final untouched out-of-sample period outside the walk-forward optimization process.

## 6. Add Missing Infrastructure

Highest-value framework additions:

- Manifest-aware data loader that consumes `data_manifest.yaml`.
- Bid/ask candle loader that preserves bid and ask OHLC separately.
- Campaign matrix runner for pairs, timeframes, sessions, regimes, and cost assumptions.
- Final untouched out-of-sample split enforcement.
- Drawdown-duration and consecutive-loss metrics.
- Broker-specific commission, swap, minimum stop distance, and margin models.

## Current Blocker

No next performance experiment is valid until real historical market data exists.
