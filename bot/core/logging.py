from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from bot.core.config import LOG_DIR


def setup_logging(level: str) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        "%Y-%m-%d %H:%M:%S",
    )
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    file_handler = RotatingFileHandler(
        LOG_DIR / "bot.log", maxBytes=10_000_000, backupCount=10, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    root.addHandler(console)
    root.addHandler(file_handler)
    logging.getLogger("discord").setLevel(logging.INFO)
