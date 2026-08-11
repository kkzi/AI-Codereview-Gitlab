"""SQLite connection pool with per-thread connections and WAL tuning.

Each thread keeps a single reusable connection, avoiding the cost of
opening a fresh sqlite3 connection on every database operation while
staying safe for multi-threaded usage (sqlite3 connections must be
used from a single thread).

Schema initialization is guarded per (db_file, tag) so repeated
``init_db()`` calls do not re-run DDL on every webhook request.
"""
from __future__ import annotations

import os
import sqlite3
import threading
from typing import Dict, Tuple


class ConnectionPool:
    """Thread-local SQLite connection pool."""

    def __init__(self, db_file: str, timeout: float = 30.0) -> None:
        self.db_file = db_file
        self.timeout = timeout
        self._local = threading.local()
        self._connections: Dict[int, sqlite3.Connection] = {}
        self._lock = threading.Lock()

    def connect(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            return conn

        conn = sqlite3.connect(self.db_file, timeout=self.timeout)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=%d" % int(self.timeout * 1000))
        conn.execute("PRAGMA cache_size=-64000")
        conn.execute("PRAGMA foreign_keys=OFF")

        self._local.conn = conn
        with self._lock:
            self._connections[threading.get_ident()] = conn
        return conn

    def close(self) -> None:
        with self._lock:
            connections = list(self._connections.values())
            self._connections.clear()
        for conn in connections:
            try:
                conn.close()
            except sqlite3.Error:
                pass
        self._local.conn = None


_schema_lock = threading.Lock()
_schema_ready: Dict[Tuple[str, str], bool] = {}


def schema_ready(db_file: str, tag: str) -> bool:
    """Whether the schema for (db_file, tag) was already initialized."""
    key = (os.path.abspath(db_file), tag)
    with _schema_lock:
        return _schema_ready.get(key, False)


def mark_schema_ready(db_file: str, tag: str) -> None:
    """Mark the schema for (db_file, tag) as initialized."""
    key = (os.path.abspath(db_file), tag)
    with _schema_lock:
        _schema_ready[key] = True