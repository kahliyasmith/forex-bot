# Audit Assumptions

Run ID: `20260512_144721_audit_campaign`

This campaign separates framework readiness from trading evidence. No historical market data is present, so no backtest edge evidence exists.

## Data Assumptions

- Real historical market data available in repo: none found.
- Mock data created for framework smoke checks: `mock_data/EUR_USD_H1_mock.csv`.
- Mock data is synthetic, tiny, hand-shaped, and not representative of forex market behavior.
- Mock data must not be used for profitability, robustness, drawdown, win-rate, or strategy-edge conclusions.
- Current scripts require data to be supplied explicitly with `--data`.
- `config/data_manifest.yaml` is supported by a manifest loader for metadata validation and missing-file rejection. Backtest runners still accept explicit `--data` paths for direct runs.

## Current Loader Expectations

Entrypoint: `scripts/run_backtest.py`

Supported file format: CSV.

Supported input kinds:

- `quotes`: `timestamp,pair,bid,ask`
- `candles`: `timestamp,pair,open,high,low,close,volume`

The loader also accepts `symbol` instead of `pair`. Pair names are parsed into the repo's canonical underscore format, such as `EUR_USD`, `GBP_USD`, and `USD_JPY`.

Timestamp behavior:

- ISO-8601 timestamps are expected.
- `Z` is accepted as UTC.
- Naive timestamps are treated as UTC by the backtest runner, but the validator flags them as invalid for audit-grade data.
- Rows are sorted by timestamp before running.

Directories searched:

- No automatic data directories are searched by the runner.
- Data is loaded only from the explicit `--data` path.

Supported timeframes:

- The loader does not enforce timeframe names.
- Candle interval is inferred only by external validation, not by the backtest runner.
- Walk-forward validation currently requires candle rows.

Missing data handling:

- The runner does not repair missing candles/ticks.
- The validator can report duplicate timestamps, non-monotonic timestamps, missing intervals, weekend rows, bad prices, crossed bid/ask, large gaps, unrealistic spreads, and timezone problems.

## Execution Assumptions

For quote data:

- Bid/ask is supported.
- Quote fills are bid/ask-aware.
- Long entry fills at ask.
- Long exit fills at bid.
- Short entry fills at bid.
- Short exit fills at ask.
- Average quote spread can be measured from bid/ask rows.

For candle data:

- Bid/ask is synthesized from candle close plus an assumed spread.
- This is lower-confidence than real bid/ask data.
- Same-candle signal and fill behavior must be reviewed before using candle-only results as evidence.

Costs modeled by current tooling:

- Spread: modeled directly from bid/ask quotes or by `--spread-pips` for candles.
- Slippage: modeled by `--slippage-pips`.
- Commission: modeled by `--commission-per-trade`.
- Swap/rollover: modeled only as a simple `--swap-cost-per-trade` placeholder.
- Stress costs: `scripts/run_backtest.py` supports 1x/2x/3x spread and slippage stress grids.

Costs not yet modeled with broker-grade realism:

- Latency distribution.
- Minimum stop distance.
- Partial fills.
- Broker-specific margin closeout rules.
- Session-specific rejected orders.
- Detailed swap by pair, direction, and rollover date.

## Strategy Assumptions

Strategy entrypoint: `forex_bot.strategies.TrendPullbackStrategy`.

Runner strategy key: `trend_pullback`.

Default strategy parameters in `scripts/run_backtest.py`:

- `trend_ma_period=5`
- `pullback_lookback=3`
- `atr_period=3`
- `atr_multiplier=1.5`
- `reward_r_multiple=2.0`
- `min_confidence=0.6`

No strategy tuning was performed in this audit. The mock walk-forward run exercised the tuning code path only, and its outputs are not evidence.

## Config Files

Primary config: `config/bot.yaml`

Configured default pairs:

- `EUR_USD`
- `GBP_USD`
- `USD_JPY`

Risk defaults:

- Risk per trade: `0.25%`
- Max daily loss: `1.0%`
- Max weekly loss: `3.0%`
- Max drawdown: `8.0%`
- Max open trades: `2`
- Max leverage: `3.0`

Execution defaults:

- Max slippage: `1.0` pip
- Stop loss required: `true`

Mode defaults:

- Bot mode: `paper`
- Broker type: `paper`
- Live trading remains disabled.

## Bias Review

Lookahead/repainting risk:

- No market-data evidence run was performed.
- Candle-mode fills need further review because strategy candles and synthetic fills come from candle close.
- The walk-forward runner uses chronological windows, which is the right direction, but no real data was available to validate the full process.

Survivorship/cherry-picking risk:

- No pair, timeframe, or date range was selected from market performance.
- No real dataset exists yet, so no cherry-picking evidence is available.

Future leakage:

- No future leakage was proven in unit tests.
- Audit-grade confirmation requires real data with chronological split checks and inspection of feature generation.

## Evidence Boundary

Any metric generated from `mock_data/` or `framework_validation/` is a tooling result, not market evidence.
