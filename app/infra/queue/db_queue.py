from __future__ import annotations

import json
import os
import sqlite3
import time
from typing import Any, Dict, Optional

from app.core.performance import get_monitor
from app.infra.db.pool import ConnectionPool, mark_schema_ready, schema_ready


class DbQueue:
    def __init__(self, db_file: str) -> None:
        self.db_file = db_file
        self.monitor = get_monitor()
        self._pool = ConnectionPool(self.db_file)
        self._last_reclaim_ts: float = 0.0

    def close(self) -> None:
        self._pool.close()

    def init_db(self) -> None:
        if schema_ready(self.db_file, "queue"):
            return
        with self._pool.connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS review_job (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_type TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    token TEXT,
                    url TEXT,
                    event_id INTEGER,
                    record_id INTEGER,
                    status TEXT DEFAULT 'pending',
                    attempts INTEGER DEFAULT 0,
                    max_attempts INTEGER DEFAULT 3,
                    run_after INTEGER DEFAULT 0,
                    last_error TEXT DEFAULT '',
                    created_at INTEGER,
                    updated_at INTEGER
                )
                """
            )
            _ensure_column(cursor, "review_job", "record_id", "INTEGER")
            conn.commit()
        mark_schema_ready(self.db_file, "queue")

    def enqueue_review_event(
        self,
        *,
        job_type: str,
        payload: Dict[str, Any],
        url: str,
        event_id: Optional[int] = None,
        record_id: Optional[int] = None,
    ) -> int:
        now = int(time.time())
        with self._pool.connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO review_job
                    (job_type, payload, url, event_id, record_id, status, attempts, max_attempts, run_after, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 'pending', 0, ?, 0, ?, ?)
                """,
                (
                    job_type,
                    json.dumps(payload, ensure_ascii=False),
                    url,
                    event_id,
                    record_id,
                    int(_get_max_attempts()),
                    now,
                    now,
                ),
            )
            conn.commit()
            return cursor.lastrowid

    def enqueue_gitlab_event(
        self,
        *,
        payload: Dict[str, Any],
        url: str,
        event_id: Optional[int] = None,
        record_id: Optional[int] = None,
    ) -> int:
        return self.enqueue_review_event(
            job_type="gitlab_review",
            payload=payload,
            url=url,
            event_id=event_id,
            record_id=record_id,
        )

    def enqueue_github_event(
        self,
        *,
        payload: Dict[str, Any],
        url: str,
        event_id: Optional[int] = None,
        record_id: Optional[int] = None,
    ) -> int:
        return self.enqueue_review_event(
            job_type="github_review",
            payload=payload,
            url=url,
            event_id=event_id,
            record_id=record_id,
        )

    def enqueue_gitea_event(
        self,
        *,
        payload: Dict[str, Any],
        url: str,
        event_id: Optional[int] = None,
        record_id: Optional[int] = None,
    ) -> int:
        return self.enqueue_review_event(
            job_type="gitea_review",
            payload=payload,
            url=url,
            event_id=event_id,
            record_id=record_id,
        )

    def claim_next_job(self) -> Optional[Dict[str, Any]]:
        now = int(time.time())
        with self.monitor.measure("queue_claim_job"):
            with self._pool.connect() as conn:
                conn.row_factory = sqlite3.Row
                conn.isolation_level = None
                cursor = conn.cursor()
                cursor.execute("BEGIN IMMEDIATE")
                if time.time() - self._last_reclaim_ts >= _get_reclaim_interval():
                    _reclaim_stale_jobs_with_cursor(cursor, now)
                    self._last_reclaim_ts = time.time()
                cursor.execute(
                    """
                    SELECT id, job_type, payload, url, event_id, record_id, attempts, max_attempts
                    FROM review_job
                    WHERE status = 'pending' AND run_after <= ?
                    ORDER BY id ASC
                    LIMIT 1
                    """,
                    (now,),
                )
                row = cursor.fetchone()
                if not row:
                    cursor.execute("COMMIT")
                    return None

                job_id = row["id"]
                attempts = int(row["attempts"] or 0) + 1
                cursor.execute(
                    """
                    UPDATE review_job
                    SET status = 'running', attempts = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (attempts, now, job_id),
                )
                cursor.execute("COMMIT")

            payload = json.loads(row["payload"]) if row["payload"] else {}
            return {
                "id": job_id,
                "job_type": row["job_type"],
                "payload": payload,
                "url": row["url"],
                "event_id": row["event_id"],
                "record_id": row["record_id"],
                "attempts": attempts,
                "max_attempts": row["max_attempts"],
            }

    def mark_done(self, job_id: int) -> None:
        now = int(time.time())
        with self._pool.connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE review_job SET status='done', updated_at=? WHERE id=?",
                (now, job_id),
            )
            conn.commit()

    def mark_failed(self, job_id: int, attempts: int, max_attempts: int, error: str) -> None:
        now = int(time.time())
        with self._pool.connect() as conn:
            cursor = conn.cursor()
            if attempts >= max_attempts:
                cursor.execute(
                    """
                    UPDATE review_job
                    SET status='failed', last_error=?, updated_at=?
                    WHERE id=?
                    """,
                    (error[:500], now, job_id),
                )
            else:
                backoff = _get_backoff_seconds(attempts)
                run_after = now + backoff
                cursor.execute(
                    """
                    UPDATE review_job
                    SET status='pending', run_after=?, last_error=?, updated_at=?
                    WHERE id=?
                    """,
                    (run_after, error[:500], now, job_id),
                )
            conn.commit()

    def has_active_event(self, event_id: int) -> bool:
        if not event_id:
            return False
        lease_seconds = _get_lease_seconds()
        now = int(time.time())
        with self._pool.connect() as conn:
            cursor = conn.cursor()
            if lease_seconds > 0:
                cursor.execute(
                    """
                    SELECT COUNT(*) FROM review_job
                    WHERE event_id = ?
                      AND (
                        status = 'pending'
                        OR (status = 'running' AND updated_at >= ?)
                      )
                    """,
                    (int(event_id), now - lease_seconds),
                )
            else:
                cursor.execute(
                    """
                    SELECT COUNT(*) FROM review_job
                    WHERE event_id = ? AND status IN ('pending', 'running')
                    """,
                    (int(event_id),),
                )
            count = cursor.fetchone()[0]
            return int(count or 0) > 0

    def reclaim_stale_jobs(self) -> int:
        lease_seconds = _get_lease_seconds()
        if lease_seconds <= 0:
            return 0
        now = int(time.time())
        stale_before = now - lease_seconds
        with self._pool.connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE review_job
                SET status = 'pending', run_after = 0, updated_at = ?
                WHERE status = 'running' AND updated_at < ?
                """,
                (now, stale_before),
            )
            conn.commit()
            self._last_reclaim_ts = time.time()
            return int(cursor.rowcount or 0)

    def get_latest_job_for_record(self, record_id: int) -> Optional[Dict[str, Any]]:
        if not record_id:
            return None
        with self._pool.connect() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, job_type, status, attempts, max_attempts, run_after, last_error,
                       created_at, updated_at
                FROM review_job
                WHERE record_id = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (int(record_id),),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_job_status_counts(self) -> Dict[str, int]:
        counts = {"pending": 0, "running": 0, "done": 0, "failed": 0}
        with self._pool.connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT status, COUNT(*) FROM review_job
                GROUP BY status
                """
            )
            for status, count in cursor.fetchall():
                if status in counts:
                    counts[status] = int(count or 0)
                else:
                    counts[str(status)] = int(count or 0)
        counts["total"] = sum(
            v for k, v in counts.items() if k in {"pending", "running", "done", "failed"}
        )
        return counts

    def get_latest_job_update(self) -> Optional[Dict[str, Any]]:
        with self._pool.connect() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, status, updated_at
                FROM review_job
                WHERE updated_at IS NOT NULL
                ORDER BY updated_at DESC
                LIMIT 1
                """
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_latest_failed_job(self) -> Optional[Dict[str, Any]]:
        with self._pool.connect() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, last_error, updated_at
                FROM review_job
                WHERE status = 'failed'
                ORDER BY updated_at DESC
                LIMIT 1
                """
            )
            row = cursor.fetchone()
            return dict(row) if row else None


def _get_max_attempts() -> int:
    try:
        return int(os.getenv("JOB_MAX_ATTEMPTS", "3"))
    except Exception:
        return 3


def _get_backoff_seconds(attempts: int) -> int:
    try:
        base = int(os.getenv("JOB_RETRY_BACKOFF", "2"))
    except Exception:
        base = 2
    return min(base * (2 ** max(attempts - 1, 0)), 60)


def _get_lease_seconds() -> int:
    try:
        return int(os.getenv("JOB_LEASE_SECONDS", "600"))
    except Exception:
        return 600


def _get_reclaim_interval() -> float:
    try:
        return float(os.getenv("QUEUE_RECLAIM_INTERVAL", "60"))
    except Exception:
        return 60.0


def _reclaim_stale_jobs_with_cursor(cursor: sqlite3.Cursor, now: int) -> None:
    lease_seconds = _get_lease_seconds()
    if lease_seconds <= 0:
        return
    stale_before = now - lease_seconds
    cursor.execute(
        """
        UPDATE review_job
        SET status = 'pending', run_after = 0, updated_at = ?
        WHERE status = 'running' AND updated_at < ?
        """,
        (now, stale_before),
    )


def _ensure_column(cursor: sqlite3.Cursor, table: str, column: str, column_type: str) -> None:
    cursor.execute(f"PRAGMA table_info({table})")
    columns = [row[1] for row in cursor.fetchall()]
    if column in columns:
        return
    cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")
