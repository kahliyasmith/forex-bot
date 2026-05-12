# forex-bot

Private Python scaffold for forex trading research, backtesting, paper trading, and monitored execution.

This first version supports validated configuration loading, structured logging setup, and a placeholder CLI command that prints the active bot mode. It does not implement live trading.

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
