"""Logging helpers - writes both to console and a daily log file."""
from __future__ import annotations

import logging
import sys
from datetime import datetime

from .config import CFG


def get_logger(name: str = "efos_ai_blog") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s | %(levelname)-7s | %(message)s", "%Y-%m-%d %H:%M:%S")

    # Force UTF-8 on the console stream so rupee/emoji symbols don't crash runs
    # on Windows (cp1252) terminals.
    stream = logging.StreamHandler(sys.stdout)
    try:
        stream.stream.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001 - older/non-file streams
        pass
    stream.setFormatter(fmt)
    logger.addHandler(stream)

    log_file = CFG.log_dir / f"run_{datetime.now():%Y-%m-%d}.log"
    try:
        fileh = logging.FileHandler(log_file, encoding="utf-8")
        fileh.setFormatter(fmt)
        logger.addHandler(fileh)
    except OSError:
        pass

    return logger


log = get_logger()
