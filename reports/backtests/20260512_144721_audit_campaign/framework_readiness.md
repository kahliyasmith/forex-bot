# Framework Readiness

Run ID: `20260512_144721_audit_campaign`

Framework status: `FRAMEWORK_READY_DATA_MISSING`

This file reports whether the repo can run the bot/backtest tooling when valid data exists. It does not report strategy edge.

## Commands Run

Unit tests:

```powershell
$env:PYTHONPATH = "$PWD\.test-deps;$PWD\src"
.\.test-deps\bin\pytest.exe
```

Result: `92 passed`

Backtest runner help:

```powershell
python scripts\run_backtest.py --help
```

Result: passed.

Walk-forward runner help:

```powershell
python scripts\run_walkforward.py --help
```

Result: passed.

Data validator help:

```powershell
python scripts\validate_market_data.py --help
```

Result: passed. Current help includes `--data-kind {auto,quotes,candles,bidask_candles}`.

Mock-data validation:

```powershell
python scripts\validate_market_data.py --data reports\backtests\20260512_144721_audit_campaign\mock_data\EUR_USD_H1_mock.csv --data-kind candles --expected-interval-minutes 60 --output-dir reports\backtests\20260512_144721_audit_campaign\framework_validation\data_validator
```

Result: passed.

Mock-data backtest smoke:

```powershell
python scripts\run_backtest.py --config config\bot.yaml --data reports\backtests\20260512_144721_audit_campaign\mock_data\EUR_USD_H1_mock.csv --data-kind candles --strategy trend_pullback --spread-pips 1.0 --slippage-pips 0.2 --commission-per-trade 0.5 --swap-cost-per-trade 0.1 --output-dir reports\backtests\20260512_144721_audit_campaign\framework_validation\mock_smoke --trend-ma-period 3 --atr-period 2 --pullback-lookback 2 --no-stress-costs
```

Result: completed and wrote trade/performance outputs.

Mock-data walk-forward smoke:

```powershell
python scripts\run_walkforward.py --config config\bot.yaml --data reports\backtests\20260512_144721_audit_campaign\mock_data\EUR_USD_H1_mock.csv --data-kind candles --output-dir reports\backtests\20260512_144721_audit_campaign\framework_validation\mock_walkforward --train-window-size 7 --test-window-size 7 --step-size 7 --trend-ma-periods 3 --pullback-lookbacks 2 --atr-periods 2 --atr-multipliers 1.5,2.0 --reward-r-multiples 2.0 --spread-pips 1.0 --slippage-pips 0.2
```

Result: completed and wrote walk-forward outputs.

Warning: mock-data outputs are tooling validation only and are not market evidence.

## What Is Ready

- Python package imports.
- Config loading and validation.
- Live-trading safety guard tests.
- Market data model tests.
- Strategy interface and trend-pullback strategy tests.
- Bid/ask-aware backtest engine tests.
- Performance reporting tests.
- Backtest CLI tests.
- Walk-forward CLI tests.
- New data validator tests.
- Paper, demo, and live broker safety tests.
- Bot loop and status command tests.

## Current Entrypoints

Bot CLI:

```powershell
forex-bot --config config\bot.yaml
forex-bot --config config\bot.yaml status
```

Backtest runner:

```powershell
python scripts\run_backtest.py --config config\bot.yaml --data <csv> --data-kind <quotes|candles|bidask_candles|auto> --strategy trend_pullback --output-dir <report_dir>
```

Walk-forward runner:

```powershell
python scripts\run_walkforward.py --config config\bot.yaml --data <candle_csv> --data-kind candles --train-window-size <n> --test-window-size <n> --step-size <n> --output-dir <report_dir>
```

Data validator:

```powershell
python scripts\validate_market_data.py --data <csv> --data-kind <quotes|candles|bidask_candles|auto> --output-dir <validation_report_dir>
```

## Data Loader Expectations

Current data directories searched:

- None automatically.
- The runner loads only the explicit `--data` file.

Config keys for data paths:

- None currently used by backtest scripts.

Supported file types:

- CSV only.

Required quote columns:

- `timestamp`
- `pair` or `symbol`
- `bid`
- `ask`

Required candle columns:

- `timestamp`
- `pair` or `symbol`
- `open`
- `high`
- `low`
- `close`
- `volume` optional, defaulted to `0` by the runner.

Required bid/ask candle columns:

- `timestamp`
- `pair` or `symbol`
- `bid_open`
- `bid_high`
- `bid_low`
- `bid_close`
- `ask_open`
- `ask_high`
- `ask_low`
- `ask_close`
- `volume` optional, defaulted to `0` by the runner.

Supported symbol naming:

- Canonical repo symbols use underscores: `EUR_USD`, `GBP_USD`, `USD_JPY`.
- Loader accepts `pair` or `symbol`.
- Market-data parsing accepts compact symbols such as `EURUSD` and normalizes them to `EUR_USD`.

Supported timeframes:

- Not explicitly enforced by the loader.
- The validator can check expected intervals when `--expected-interval-minutes` is provided.

Bid/ask support:

- Quote data supports real bid/ask fields.
- Bid/ask candle data is validated as `bidask_candles` and normalized by the backtest loader into mid-price candles plus a measured close-spread assumption.
- Plain candle data does not preserve bid/ask OHLC; the engine synthesizes bid/ask from close and assumed spread.

Cost modeling:

- Spread: real bid/ask for quote rows, measured close spread for `bidask_candles`, or `--spread-pips` for plain candle rows.
- Slippage: `--slippage-pips`.
- Commission: `--commission-per-trade`.
- Swap: `--swap-cost-per-trade`, currently a placeholder.

Missing candle/tick handling:

- Runner sorts rows but does not repair or reject missing intervals.
- Validator reports missing intervals when expected interval is supplied.

Timezone handling:

- Runner treats naive timestamps as UTC.
- Validator flags naive timestamps as errors for audit use.

## Known Framework Limits

- No real market data is present.
- Manifest metadata loading exists, but no full campaign matrix runner consumes it end-to-end yet.
- Walk-forward validation currently requires candle data.
- No automated full matrix runner exists yet.
- `bidask_candles` validation and loader normalization exist, but the current strategy path still consumes normalized mid-price candles plus a measured average spread assumption.
- Plain candle-mode backtests are lower confidence because bid/ask is synthesized.
- Swap, commission, latency, and rejected-order assumptions are still simplified.

## Ready-To-Run Commands After Data Exists

Validate one file:

```powershell
python scripts\validate_market_data.py --data data\historical\EUR_USD_H1_2020_2025.csv --data-kind candles --expected-interval-minutes 60 --output-dir reports\data_validation\EUR_USD_H1
python scripts\validate_market_data.py --data data\historical\EUR_USD_H1_bidask_2020_2025.csv --data-kind bidask_candles --expected-interval-minutes 60 --output-dir reports\data_validation\EUR_USD_H1_bidask
```

Run one smoke backtest:

```powershell
python scripts\run_backtest.py --config config\bot.yaml --data data\historical\EUR_USD_H1_2020_2025.csv --data-kind candles --strategy trend_pullback --spread-pips 1.2 --slippage-pips 0.2 --commission-per-trade 0 --swap-cost-per-trade 0 --output-dir reports\backtests\real_smoke_EUR_USD_H1
python scripts\run_backtest.py --config config\bot.yaml --data data\historical\EUR_USD_H1_bidask_2020_2025.csv --data-kind bidask_candles --strategy trend_pullback --slippage-pips 0.2 --commission-per-trade 0 --swap-cost-per-trade 0 --output-dir reports\backtests\real_smoke_EUR_USD_H1_bidask
```

Run one walk-forward validation:

```powershell
python scripts\run_walkforward.py --config config\bot.yaml --data data\historical\EUR_USD_H1_2020_2025.csv --data-kind candles --train-window-size 1000 --test-window-size 250 --step-size 250 --output-dir reports\walkforward\EUR_USD_H1
```

Run tests before trusting changes:

```powershell
pytest
```

## Framework Verdict

The framework is ready for real-data smoke testing, with the limitations above. The evidence campaign remains blocked because no real market data exists.
