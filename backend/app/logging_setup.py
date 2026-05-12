"""Configure application loggers (stderr, INFO) without fighting uvicorn."""
from __future__ import annotations

import logging
import sys

_LOGGERS = (
    "app.api.analyze",
    "app.services.listing_parser",
)


def configure_app_logging(level: int = logging.INFO) -> None:
    fmt = "%(asctime)s | %(levelname)-5s | %(name)s | %(message)s"
    formatter = logging.Formatter(fmt, datefmt="%H:%M:%S")
    for name in _LOGGERS:
        lg = logging.getLogger(name)
        lg.setLevel(level)
        if not lg.handlers:
            h = logging.StreamHandler(sys.stderr)
            h.setFormatter(formatter)
            lg.addHandler(h)
        lg.propagate = False
