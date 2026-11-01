"""Structured logging setup with credential redaction."""

import logging
import re
import sys

CREDENTIAL_URL_PATTERN = re.compile(
    r"((?:postgresql(?:\+\w+)?|redis|rediss)://[^:\s]*:)([^@\s]+)(@)"
)


class RedactingFormatter(logging.Formatter):
    """Formatter that redacts inline URI passwords from log records."""

    def format(self, record: logging.LogRecord) -> str:
        formatted = super().format(record)
        return CREDENTIAL_URL_PATTERN.sub(r"\1***REDACTED***\3", formatted)


def configure_logging(debug: bool = True) -> None:
    """Configure root and application loggers safely."""
    level = logging.DEBUG if debug else logging.INFO
    handler = logging.StreamHandler(sys.stdout)
    formatter = RedactingFormatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
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

