# forex-bot

Private Python scaffold for forex trading research, backtesting, paper trading, and monitored execution.

This first version supports validated configuration loading, structured logging setup, and a placeholder CLI command that prints the active bot mode. It does not implement live trading.

Current core modules also include:

- Bid/ask-aware market data models and pip helpers.
- A paper broker that simulates account state, fills, open positions, stop loss, take profit, pending orders, and realized/unrealized P&L.
- Performance reporting with JSON and CSV exports, including pair/session/strategy breakdowns, average spread paid, average slippage, news-window losses, and rollover exposure.
- A structured trade journal that writes JSONL and CSV decision records.
- Kill switches for loss limits, abnormal spread/slippage, stale data, position mismatches, missing stops, order rejects, and API errors.
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
