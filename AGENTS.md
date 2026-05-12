# AGENTS.md

## Project goal

Build a Python forex trading bot for research, backtesting, paper trading, and eventually guarded live trading.

The bot must prioritize risk management, testability, and realistic transaction costs over aggressive performance.

## Non-negotiable safety rules

- Do not implement live trading until backtesting and paper trading modules exist.
- Do not place real-money orders unless LIVE_TRADING_ENABLED=true.
- Default mode must be paper trading.
- Every live order must pass risk checks, margin checks, spread checks, slippage checks, and news/session filters.
- Never implement martingale, grid averaging down, or doubling after losses.
- Never store broker credentials in code.
- Use environment variables for secrets.
- Every module must have unit tests.
- Every strategy must include transaction costs, spread, slippage, and swap assumptions in backtests.

## Preferred stack

- Python
- pytest
- pydantic for config validation
- pandas/numpy for research
- structured logging
- type hints throughout

## Required modules

- data layer
- backtesting engine
- strategy interface
- risk engine
- execution engine
- paper trading broker
- live broker adapter placeholder
- monitoring/logging
- kill switch

## Definition of done

A task is not complete unless:
- tests pass
- code is typed where practical
- README is updated if behavior changed
- no live trading can happen accidentally
