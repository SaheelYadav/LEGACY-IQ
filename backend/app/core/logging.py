"""Structured logging setup with credential redaction and correlation ID context."""

from contextvars import ContextVar
from datetime import datetime, timezone
import json
import logging
import re
import sys

CREDENTIAL_URL_PATTERN = re.compile(
    r"((?:postgresql(?:\+\w+)?|redis|rediss)://[^:\s]*:)([^@\s]+)(@)"
)
BEARER_TOKEN_PATTERN = re.compile(
    r"(Bearer\s+)([A-Za-z0-9\-_\.]+)", re.IGNORECASE
)

correlation_id_ctx: ContextVar[str] = ContextVar("correlation_id", default="-")


def redact_sensitive_text(text: str) -> str:
    """Redact inline database/Redis passwords and Bearer tokens from log strings."""
    cleaned = CREDENTIAL_URL_PATTERN.sub(r"\1***REDACTED***\3", text)
    cleaned = BEARER_TOKEN_PATTERN.sub(r"\1***REDACTED***", cleaned)
    return cleaned


class RedactingFormatter(logging.Formatter):
    """Formatter that redacts inline URI passwords and tokens, with optional JSON output."""

    def __init__(
        self,
        fmt: str | None = None,
        datefmt: str | None = None,
        *,
        json_output: bool = False,
    ) -> None:
        super().__init__(fmt=fmt, datefmt=datefmt)
        self.json_output = json_output

    def format(self, record: logging.LogRecord) -> str:
        corr_id = getattr(record, "correlation_id", None) or correlation_id_ctx.get()
        record.correlation_id = corr_id
        if self.json_output:
            msg = redact_sensitive_text(record.getMessage())
            payload: dict[str, object] = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "correlation_id": corr_id,
                "message": msg,
            }
            if record.exc_info:
                payload["exception"] = redact_sensitive_text(
                    self.formatException(record.exc_info)
                )
            return json.dumps(payload, ensure_ascii=False)
        formatted = super().format(record)
        return redact_sensitive_text(formatted)


def configure_logging(
    debug: bool = True,
    *,
    log_format: str = "text",
    log_level: str | None = None,
) -> None:
    """Configure root and application loggers safely."""
    if log_level:
        level = getattr(logging, log_level.upper(), logging.INFO)
    else:
        level = logging.DEBUG if debug else logging.INFO

    handler = logging.StreamHandler(sys.stdout)
    formatter = RedactingFormatter(
        fmt="%(asctime)s | %(levelname)-8s | %(correlation_id)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        json_output=(log_format.lower() == "json"),
    )
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(level)
    root_logger.addHandler(handler)

    # Reduce noise from third-party libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


