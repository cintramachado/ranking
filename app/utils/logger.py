from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

_configured = False


def setup_logging(
    path: str | Path = "logs/flowrank.log",
    level: str = "INFO",
    max_bytes: int = 5_000_000,
    backup_count: int = 5,
) -> logging.Logger:
    global _configured
    logger = logging.getLogger("flowrank")
    if _configured:
        return logger

    log_path = Path(path)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logger.setLevel(getattr(logging, str(level).upper(), logging.INFO))
    fmt = logging.Formatter("%(asctime)s | %(levelname)-7s | %(name)s | %(message)s")

    file_handler = RotatingFileHandler(
        log_path, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    stream = logging.StreamHandler()
    stream.setFormatter(fmt)
    logger.addHandler(stream)

    logger.propagate = False
    _configured = True
    return logger


def get_logger(name: str = "flowrank") -> logging.Logger:
    if name == "flowrank":
        return logging.getLogger("flowrank")
    return logging.getLogger(f"flowrank.{name}")
