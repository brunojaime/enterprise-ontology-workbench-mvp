"""Structured logging configuration for the packaged API process."""

from __future__ import annotations

import json
import logging
import logging.config
from datetime import UTC, datetime
from typing import Any


class JsonFormatter(logging.Formatter):
    """Render one JSON object per line without leaking arbitrary record fields."""

    _structured_fields = (
        "request_id",
        "method",
        "path",
        "status_code",
        "duration_ms",
        "semantic_operation",
    )

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "event": record.getMessage(),
        }
        for field in self._structured_fields:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def uvicorn_log_config(level: str = "INFO") -> dict[str, Any]:
    """Return a Uvicorn-compatible config that keeps every backend line JSON."""

    normalized = level.upper()
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {"json": {"()": JsonFormatter}},
        "handlers": {
            "default": {
                "class": "logging.StreamHandler",
                "formatter": "json",
                "stream": "ext://sys.stdout",
            }
        },
        "loggers": {
            "uvicorn": {"handlers": ["default"], "level": normalized, "propagate": False},
            "uvicorn.error": {
                "handlers": ["default"],
                "level": normalized,
                "propagate": False,
            },
            "uvicorn.access": {
                "handlers": ["default"],
                "level": normalized,
                "propagate": False,
            },
            "eow.api.access": {
                "handlers": ["default"],
                "level": normalized,
                "propagate": False,
            },
        },
    }


def configure_application_logging(level: str = "INFO") -> None:
    """Install the same formatter when the app is hosted outside its module runner."""

    logging.config.dictConfig(uvicorn_log_config(level))
