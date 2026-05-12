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
