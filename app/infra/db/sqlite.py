from __future__ import annotations

import json
import sqlite3
from typing import Any, Dict, Optional

from app.infra.db.pool import ConnectionPool, mark_schema_ready, schema_ready


class SQLiteRepository:
    def __init__(self, db_file: str) -> None:
        self.db_file = db_file
        self._pool = ConnectionPool(self.db_file)

    def close(self) -> None:
        self._pool.close()

    def init_db(self) -> None:
        if schema_ready(self.db_file, "review_log"):
            return
        with self._pool.connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS mr_review_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_name TEXT,
                    author TEXT,
                    author_display_name TEXT DEFAULT '',
                    source_branch TEXT,
                    target_branch TEXT,
                    updated_at INTEGER,
                    commit_messages TEXT,
                    score INTEGER,
                    model_name TEXT DEFAULT '',
                    language TEXT DEFAULT '',
                    url TEXT,
                    review_result TEXT,
                    additions INTEGER DEFAULT 0,
                    deletions INTEGER DEFAULT 0,
                    last_commit_id TEXT DEFAULT '',
                    status TEXT DEFAULT 'success',
                    retry_count INTEGER DEFAULT 0,
                    project_url TEXT DEFAULT '',
                    commit_url TEXT DEFAULT '',
                    event_id INTEGER DEFAULT NULL
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS push_review_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_name TEXT,
                    author TEXT,
                    author_display_name TEXT DEFAULT '',
                    branch TEXT,
                    updated_at INTEGER,
                    commit_messages TEXT,
                    score INTEGER,
                    model_name TEXT DEFAULT '',
                    language TEXT DEFAULT '',
                    review_result TEXT,
                    additions INTEGER DEFAULT 0,
                    deletions INTEGER DEFAULT 0,
                    last_commit_id TEXT DEFAULT '',
                    status TEXT DEFAULT 'success',
                    retry_count INTEGER DEFAULT 0,
                    project_url TEXT DEFAULT '',
                    commit_url TEXT DEFAULT '',
                    event_id INTEGER DEFAULT NULL
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS webhook_event_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    review_type TEXT,
                    source TEXT,
                    event_type TEXT,
                    project_name TEXT,
                    project_url TEXT,
                    created_at INTEGER,
                    payload TEXT
                )
                """
            )

            # 创建索引以提升查询性能
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_mr_project_name ON mr_review_log(project_name)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_mr_author ON mr_review_log(author)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_mr_status ON mr_review_log(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_mr_updated_at ON mr_review_log(updated_at DESC)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_mr_event_id ON mr_review_log(event_id)")

            cursor.execute("CREATE INDEX IF NOT EXISTS idx_push_project_name ON push_review_log(project_name)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_push_author ON push_review_log(author)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_push_status ON push_review_log(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_push_updated_at ON push_review_log(updated_at DESC)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_push_event_id ON push_review_log(event_id)")

            cursor.execute("CREATE INDEX IF NOT EXISTS idx_webhook_created_at ON webhook_event_log(created_at DESC)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_webhook_source ON webhook_event_log(source)")

            conn.commit()
        mark_schema_ready(self.db_file, "review_log")

    def insert_event(
        self,
        *,
        review_type: str,
        source: str,
        event_type: str,
        project_name: str,
        project_url: str,
        created_at: int,
        payload: Dict[str, Any],
    ) -> Optional[int]:
        try:
            with self._pool.connect() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO webhook_event_log
                        (review_type, source, event_type, project_name, project_url, created_at, payload)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        review_type,
                        source,
                        event_type,
                        project_name,
                        project_url,
                        created_at,
                        json.dumps(payload, ensure_ascii=False),
                    ),
                )
                conn.commit()
                return cursor.lastrowid
        except sqlite3.DatabaseError:
            return None

    def insert_mr_review_log(
        self,
        *,
        project_name: str,
        author: str,
        author_display_name: str,
        source_branch: str,
        target_branch: str,
        updated_at: int,
        commit_messages: str,
        score: int,
        model_name: str,
        language: str,
        url: str,
        review_result: str,
        additions: int,
        deletions: int,
        last_commit_id: str,
        status: str,
        project_url: str,
        commit_url: str,
        event_id: int | None,
    ) -> None:
        with self._pool.connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO mr_review_log (
                    project_name, author, author_display_name, source_branch, target_branch,
                    updated_at, commit_messages, score, model_name, language, url, review_result,
                    additions, deletions, last_commit_id, status, project_url, commit_url, event_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_name,
                    author,
                    author_display_name,
                    source_branch,
                    target_branch,
                    updated_at,
                    commit_messages,
                    score,
                    model_name,
                    language,
                    url,
                    review_result,
                    additions,
                    deletions,
                    last_commit_id,
                    status,
                    project_url,
                    commit_url,
                    event_id,
                ),
            )
            conn.commit()

    def insert_push_review_log(
        self,
        *,
        project_name: str,
        author: str,
        author_display_name: str,
        branch: str,
        updated_at: int,
        commit_messages: str,
        score: int,
        model_name: str,
        language: str,
        review_result: str,
        additions: int,
        deletions: int,
        last_commit_id: str,
        status: str,
        project_url: str,
        commit_url: str,
        event_id: int | None,
    ) -> None:
        with self._pool.connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO push_review_log (
                    project_name, author, author_display_name, branch, updated_at, commit_messages,
                    score, model_name, language, review_result, additions, deletions, last_commit_id,
                    status, project_url, commit_url, event_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_name,
                    author,
                    author_display_name,
                    branch,
                    updated_at,
                    commit_messages,
                    score,
                    model_name,
                    language,
                    review_result,
                    additions,
                    deletions,
                    last_commit_id,
                    status,
                    project_url,
                    commit_url,
                    event_id,
                ),
            )
            conn.commit()

    def update_mr_review_log(
        self,
        *,
        record_id: int,
        score: int,
        review_result: str,
        status: str,
        language: str,
        model_name: str,
    ) -> bool:
        with self._pool.connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE mr_review_log
                SET score = ?, model_name = ?, language = ?, review_result = ?, status = ?, retry_count = retry_count + 1
                WHERE id = ?
                """,
                (
                    score,
                    model_name,
                    language or "",
                    review_result,
                    status,
                    record_id,
                ),
            )
            conn.commit()
            return cursor.rowcount > 0

    def update_push_review_log(
        self,
        *,
        record_id: int,
        score: int,
        review_result: str,
        status: str,
        language: str,
        model_name: str,
    ) -> bool:
        with self._pool.connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE push_review_log
                SET score = ?, model_name = ?, language = ?, review_result = ?, status = ?, retry_count = retry_count + 1
                WHERE id = ?
                """,
                (
                    score,
                    model_name,
                    language or "",
                    review_result,
                    status,
                    record_id,
                ),
            )
            conn.commit()
            return cursor.rowcount > 0

    def check_mr_last_commit_id_exists(
        self, project_name: str, source_branch: str, target_branch: str, last_commit_id: str
    ) -> bool:
        if not project_name or not source_branch or not target_branch or not last_commit_id:
            return False
        with self._pool.connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT COUNT(*) FROM mr_review_log
                WHERE project_name = ? AND source_branch = ? AND target_branch = ? AND last_commit_id = ?
                """,
                (project_name, source_branch, target_branch, last_commit_id),
            )
            count = cursor.fetchone()[0]
            return int(count or 0) > 0

    def get_review_by_id(self, data_type: str, record_id: int) -> Optional[Dict[str, Any]]:
        table = "push_review_log" if data_type == "push" else "mr_review_log"
        with self._pool.connect() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(f"SELECT * FROM {table} WHERE id = ?", (record_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_event_by_id(self, event_id: int) -> Optional[Dict[str, Any]]:
        with self._pool.connect() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM webhook_event_log WHERE id = ?", (event_id,))
            row = cursor.fetchone()
            if not row:
                return None
            data = dict(row)
            payload = data.get("payload")
            if isinstance(payload, str) and payload:
                try:
                    data["payload"] = json.loads(payload)
                except json.JSONDecodeError:
                    pass
            return data

    def get_unreviewed_events_since(self, since_ts: int) -> list[Dict[str, Any]]:
        results: list[Dict[str, Any]] = []
        with self._pool.connect() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            for review_type, table in (("mr", "mr_review_log"), ("push", "push_review_log")):
                cursor.execute(
                    f"""
                    SELECT e.*
                    FROM webhook_event_log e
                    LEFT JOIN {table} r ON r.event_id = e.id
                    WHERE e.review_type = ? AND e.created_at >= ? AND r.id IS NULL
                    ORDER BY e.id ASC
                    """,
                    (review_type, since_ts),
                )
                for row in cursor.fetchall():
                    data = dict(row)
                    payload = data.get("payload")
                    if isinstance(payload, str) and payload:
                        try:
                            data["payload"] = json.loads(payload)
                        except json.JSONDecodeError:
                            pass
                    results.append(data)
        return results

    def get_reviews_paginated(
        self,
        *,
        data_type: str,
        authors: Optional[list[str]] = None,
        project_names: Optional[list[str]] = None,
        language: Optional[str] = None,
        status: Optional[str] = None,
        updated_at_gte: Optional[int] = None,
        updated_at_lte: Optional[int] = None,
        sort: str = "updated_at",
        order: str = "desc",
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[Dict[str, Any]], Dict[str, Any]]:
        table = "push_review_log" if data_type == "push" else "mr_review_log"
        allowed_sort = {"updated_at", "score", "project_name", "author", "status"}
        sort_field = sort if sort in allowed_sort else "updated_at"
        order_dir = "asc" if order == "asc" else "desc"

        limit = page_size
        offset = (page - 1) * page_size

        with self._pool.connect() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            resolved_authors = authors
            if authors:
                resolved_authors = _resolve_usernames_by_display_name(
                    cursor, table, authors
                )
                if not resolved_authors:
                    meta = {
                        "total": 0,
                        "success": 0,
                        "failed": 0,
                        "avg_score": 0,
                        "authors": [],
                        "projects": [],
                        "languages": [],
                    }
                    return [], meta

            where, params = self._build_where(
                authors=resolved_authors,
                project_names=project_names,
                language=language,
                status=status,
                updated_at_gte=updated_at_gte,
                updated_at_lte=updated_at_lte,
            )

            base_query = f"FROM {table} {where}"
            cursor.execute(f"SELECT COUNT(*) {base_query}", params)
            total = int(cursor.fetchone()[0] or 0)

            success_query = (
                f"SELECT COUNT(*) {base_query} AND status = 'success'"
                if where
                else f"SELECT COUNT(*) FROM {table} WHERE status = 'success'"
            )
            cursor.execute(success_query, params)
            success = int(cursor.fetchone()[0] or 0)

            failed_query = (
                f"SELECT COUNT(*) {base_query} AND status = 'failed'"
                if where
                else f"SELECT COUNT(*) FROM {table} WHERE status = 'failed'"
            )
            cursor.execute(failed_query, params)
            failed = int(cursor.fetchone()[0] or 0)

            cursor.execute(
                f"SELECT AVG(CASE WHEN status != 'failed' AND score IS NOT NULL AND score > 0 AND score <= 100 THEN score END) {base_query}",
                params,
            )
            avg_score = cursor.fetchone()[0]
            avg_score = round(float(avg_score or 0), 2)

            cursor.execute(
                f"SELECT DISTINCT author_display_name FROM {table} {where} ORDER BY author_display_name ASC",
                params,
            )
            authors_list = []
            seen = set()
            for row in cursor.fetchall():
                display_name = (row[0] or "").strip()
                if not display_name or display_name in seen:
                    continue
                seen.add(display_name)
                authors_list.append(display_name)

            cursor.execute(
                f"SELECT DISTINCT project_name FROM {table} {where} ORDER BY project_name ASC",
                params,
            )
            projects_list = [row[0] for row in cursor.fetchall() if row[0]]

            cursor.execute(
                f"SELECT DISTINCT language FROM {table} {where} ORDER BY language ASC",
                params,
            )
            languages_list = [row[0] for row in cursor.fetchall() if row[0]]

            cursor.execute(
                f"SELECT * {base_query} ORDER BY {sort_field} {order_dir} LIMIT ? OFFSET ?",
                (*params, limit, offset),
            )
            rows = [dict(row) for row in cursor.fetchall()]

        meta = {
            "total": total,
            "success": success,
            "failed": failed,
            "avg_score": avg_score,
            "authors": authors_list,
            "projects": projects_list,
            "languages": languages_list,
        }
        return rows, meta

    @staticmethod
    def _build_where(
        *,
        authors: Optional[list[str]] = None,
        project_names: Optional[list[str]] = None,
        language: Optional[str] = None,
        status: Optional[str] = None,
        updated_at_gte: Optional[int] = None,
        updated_at_lte: Optional[int] = None,
    ) -> tuple[str, tuple[Any, ...]]:
        clauses: list[str] = []
        params: list[Any] = []
        if authors:
            placeholders = ",".join("?" for _ in authors)
            clauses.append(f"author IN ({placeholders})")
            params.extend(authors)
        if project_names:
            placeholders = ",".join("?" for _ in project_names)
            clauses.append(f"project_name IN ({placeholders})")
            params.extend(project_names)
        if language:
            clauses.append("language = ?")
            params.append(language)
        if status:
            clauses.append("status = ?")
            params.append(status)
        if updated_at_gte is not None:
            clauses.append("updated_at >= ?")
            params.append(updated_at_gte)
        if updated_at_lte is not None:
            clauses.append("updated_at <= ?")
            params.append(updated_at_lte)

        if not clauses:
            return "", tuple()
        return " WHERE " + " AND ".join(clauses), tuple(params)


def _resolve_usernames_by_display_name(
    cursor: sqlite3.Cursor, table: str, display_names: list[str]
) -> list[str]:
    placeholders = ",".join("?" for _ in display_names)
    cursor.execute(
        f"SELECT DISTINCT author FROM {table} WHERE author_display_name IN ({placeholders})",
        display_names,
    )
    results = []
    for row in cursor.fetchall():
        username = (row[0] or "").strip()
        if username:
            results.append(username)
    return results
