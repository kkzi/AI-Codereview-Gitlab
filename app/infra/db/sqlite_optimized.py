"""SQLite 优化：启用 WAL 模式和性能调优"""
from __future__ import annotations

import json
import sqlite3
from typing import Any, Dict, Optional


class SQLiteRepository:
    def __init__(self, db_file: str) -> None:
        self.db_file = db_file

    def _get_connection(self, timeout: float = 30.0) -> sqlite3.Connection:
        """
        获取优化的 SQLite 连接

        优化项：
        1. WAL 模式：允许读写并发
        2. 增加超时：减少 "database is locked" 错误
        3. 增加缓存：提升查询性能
        """
        conn = sqlite3.connect(self.db_file, timeout=timeout)

        # 启用 WAL 模式（Write-Ahead Logging）
        # 优势：读不阻塞写，写不阻塞读
        conn.execute("PRAGMA journal_mode=WAL")

        # 设置同步模式为 NORMAL（平衡性能和安全性）
        conn.execute("PRAGMA synchronous=NORMAL")

        # 增加缓存大小到 64MB
        conn.execute("PRAGMA cache_size=-64000")

        return conn

    def init_db(self) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # 创建表...（保持原有逻辑）
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
            # ... 其他表创建代码保持不变 ...

            # 创建索引
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_mr_project_name ON mr_review_log(project_name)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_mr_author ON mr_review_log(author)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_mr_status ON mr_review_log(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_mr_updated_at ON mr_review_log(updated_at DESC)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_mr_event_id ON mr_review_log(event_id)")

            conn.commit()

    # 其他方法使用 _get_connection() 替代直接 sqlite3.connect()
    def insert_event(self, **kwargs) -> Optional[int]:
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                # ... 原有逻辑 ...
                conn.commit()
                return cursor.lastrowid
        except Exception:
            return None
