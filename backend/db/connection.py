from __future__ import annotations

import threading

import duckdb

from config import settings

# One connection per OS thread — DuckDB connections are not thread-safe.
# asyncio.to_thread() worker threads each get their own handle; they all
# point at the same on-disk file and share data via DuckDB's WAL/MVCC.
_thread_local = threading.local()


def get_connection() -> duckdb.DuckDBPyConnection:
    conn: duckdb.DuckDBPyConnection | None = getattr(_thread_local, "conn", None)
    if conn is None:
        conn = duckdb.connect(settings.db_path)
        # All timestamps UTC so TIMESTAMPTZ and current_date() stay consistent
        # regardless of the host's local timezone.
        conn.execute("SET TimeZone='UTC'")
        _thread_local.conn = conn
    return conn


def close_connection() -> None:
    conn: duckdb.DuckDBPyConnection | None = getattr(_thread_local, "conn", None)
    if conn is not None:
        conn.close()
        _thread_local.conn = None
