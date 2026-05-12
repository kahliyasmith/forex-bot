# forex-bot

Private Python scaffold for forex trading research, backtesting, paper trading, and monitored execution.

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
