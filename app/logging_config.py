"""Structured logging that never leaks secret material."""
from __future__ import annotations

import logging
import re
import sys

from app.config import get_settings

_SECRET_KEYS = re.compile(
    r'"(password|pat|secret|token|api_key|private_key)"\s*:\s*"[^"]*"',
    re.IGNORECASE,
)


class SecretScrubbingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:
            return True
        if _SECRET_KEYS.search(msg):
            record.msg = _SECRET_KEYS.sub(r'"\1": "***REDACTED***"', msg)
            record.args = ()
        return True


def configure_logging() -> None:
    settings = get_settings()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    handler.addFilter(SecretScrubbingFilter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(settings.db_validator_log_level.upper())
