# forex-bot

Private Python scaffold for forex trading research, backtesting, paper trading, and monitored execution.

This first version supports validated configuration loading, structured logging setup, and a placeholder CLI command that prints the active bot mode. It does not implement live trading.

Current core modules also include:

- Bid/ask-aware market data models and pip helpers.
- A paper broker that simulates account state, fills, open positions, stop loss, take profit, pending orders, and realized/unrealized P&L.
- Performance reporting with JSON and CSV exports, including pair/session/strategy breakdowns, average spread paid, average slippage, news-window losses, and rollover exposure.
- A structured trade journal that writes JSONL and CSV decision records.
- Kill switches for loss limits, abnormal spread/slippage, stale data, position mismatches, missing stops, order rejects, and API errors.
- A demo broker adapter for practice-account integration through the shared `Broker` interface. It fetches account state, quotes, open positions, places/closes demo orders, reconciles positions, handles API errors, and retries order placement with idempotency keys.
- A live broker adapter placeholder that cannot place live orders unless `LIVE_TRADING_ENABLED=true`; live order transport is still not implemented.

## Layout

```text
config/              YAML configuration for bot behavior, risk, and currency pairs
src/forex_bot/       Application package
tests/               Automated tests
notebooks/           Research notebooks
scripts/             Operational and development scripts
```

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

Copy `.env.example` to `.env` and fill in local credentials. Never commit `.env`.

For demo-account integration, set `broker.type` to `demo` and use demo/practice credentials only:

```text
BROKER_API_KEY=
BROKER_ACCOUNT_ID=
BROKER_ENV=demo
LIVE_TRADING_ENABLED=false
```

The demo adapter refuses non-demo environments and does not place real-money trades.

## CLI

```powershell
forex-bot --config config/bot.yaml
```

Expected output:

```text
Active bot mode: paper
Live trading enabled: false
```

Live trading is only considered enabled when the config mode is `live`, the broker type is `live`, and `LIVE_TRADING_ENABLED=true` is present in the environment.

## Status

```powershell
forex-bot --config config/bot.yaml status
```

The status command prints mode, equity, positions, daily/weekly P&L, drawdown, active kill switches, latest spreads, latest decisions, and rejected signal count. It is intentionally text-only for now.

## Backtests

Run a CSV backtest with candle data:

```powershell
python scripts/run_backtest.py --data data/history/EUR_USD_H1.csv --data-kind candles --strategy trend_pullback --spread-pips 1.2 --slippage-pips 0.2 --commission-per-trade 0 --swap-cost-per-trade 0 --output-dir reports/backtest
```

Input candle CSV columns: `timestamp,pair,open,high,low,close,volume`.
Input bid/ask CSV columns: `timestamp,pair,bid,ask`.

Outputs:

- `backtest_trades.csv`: full trade ledger with entry, exit, P&L, commission, and swap.
- `performance_report.json`: full performance report.
- `trades.csv`, `equity_curve.csv`, `summary.csv`, `performance_by_pair.csv`, `performance_by_session.csv`, and `performance_by_strategy.csv`.
- `cost_stress_report.json` and `cost_stress_report.csv`: comparison table for spread/slippage stress regimes.

By default, the script also reruns the backtest across a 3x3 transaction-cost grid:

- spread: normal, 2x, 3x
- slippage: normal, 2x, 3x

Use `--no-stress-costs` to skip the stress report. The script prints summary metrics after the run. The current `trend_pullback` strategy is candle-driven, so candle data is the practical input for that strategy.

## Walk-Forward Validation

Run walk-forward validation with candle data:

```powershell
python scripts/run_walkforward.py --data data/history/EUR_USD_H1.csv --data-kind candles --train-window-size 500 --test-window-size 100 --step-size 100 --trend-ma-periods 10,20,50 --atr-periods 7,14 --pullback-lookbacks 2,3 --atr-multipliers 1.0,1.5,2.0 --reward-r-multiples 1.5,2.0 --output-dir reports/walkforward
```

For each window, the script trains by testing every parameter set on the in-sample window, selects the best risk-aware score, then evaluates only that selected config on the next out-of-sample window.

Outputs:

- `window_*/training_grid.csv`: every tested config and training score for that window.
- `window_*/test_trades.csv` and `window_*/test_report.json`: out-of-sample trades and report.
- `walkforward_windows.csv`: selected parameters and out-of-sample metrics per window.
- `walkforward_oos_report.json`: aggregate out-of-sample performance.
- `walkforward_summary.json`: assumptions, data-quality notes, all tested configs, aggregate metrics, and an overfit/unrealistic-results warning.
