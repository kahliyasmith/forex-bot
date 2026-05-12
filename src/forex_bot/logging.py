"""Logging setup for forex-bot."""

from __future__ import annotations

import json
import logging
from typing import Any

STANDARD_LOG_ATTRS = set(logging.makeLogRecord({}).__dict__)


class JsonFormatter(logging.Formatter):
    """Small JSON formatter for structured logs."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in STANDARD_LOG_ATTRS and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, sort_keys=True)


def configure_logging(level: str = "INFO") -> logging.Logger:
    """Configure root logging and return the package logger."""

    root = logging.getLogger()
    root.handlers.clear()

    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
    root.setLevel(level.upper())

    return logging.getLogger("forex_bot")
