"""DuckDB connection helpers."""
from __future__ import annotations

import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import duckdb

from .config import settings

_lock = threading.Lock()
_conn: duckdb.DuckDBPyConnection | None = None


def _ensure_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def get_conn() -> duckdb.DuckDBPyConnection:
    """Return a single shared DuckDB connection (lazy-init)."""
    global _conn
    if _conn is not None:
        return _conn
    with _lock:
        if _conn is None:
            cfg = settings()
            _ensure_dir(cfg.duckdb_path)
            _conn = duckdb.connect(str(cfg.duckdb_path), read_only=False)
            _conn.execute("INSTALL spatial; LOAD spatial;")
    return _conn


@contextmanager
def cursor() -> Iterator[duckdb.DuckDBPyConnection]:
    """Yield a per-call cursor (DuckDB cursors are cheap)."""
    yield get_conn().cursor()
