"""Command-line interface for forex-bot."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from forex_bot.bot import create_broker
from forex_bot.config import load_config
from forex_bot.logging import configure_logging
from forex_bot.status import build_status_snapshot, render_status


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="forex-bot")
    parser.add_argument(
        "--config",
        default="config/bot.yaml",
        help="Path to the bot YAML configuration file.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Python logging level.",
    )
    parser.add_argument(
        "command",
        nargs="?",
        choices=["status"],
        help="Optional command to run.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    configure_logging(args.log_level)
    config = load_config(args.config)

    if args.command == "status":
        broker = create_broker(config)
        print(render_status(build_status_snapshot(config=config, broker=broker)))
        return 0

    print(f"Active bot mode: {config.mode.value}")
    print(f"Live trading enabled: {str(config.live_trading_enabled()).lower()}")
    return 0
