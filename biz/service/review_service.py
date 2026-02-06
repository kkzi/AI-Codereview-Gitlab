import sqlite3
import datetime

import pandas as pd

from biz.entity.review_entity import MergeRequestReviewEntity, PushReviewEntity


class ReviewService:
    DB_FILE = "data/data.db"

    @staticmethod
    def _get_model_name_from_env() -> str:
        """Return the current LLM model name from env.

        Keep this here (instead of importing biz.queue.worker.get_model_name)
        to avoid circular imports (worker -> ReviewService).
        """

        from biz.llm.config import get_llm_value

        provider = get_llm_value("LLM_PROVIDER", "unknown") or "unknown"
        api_model_env_map = {
            "anthropic": "ANTHROPIC_API_MODEL",
            "zhipuai": "ZHIPUAI_API_MODEL",
            "openai": "OPENAI_API_MODEL",
            "deepseek": "DEEPSEEK_API_MODEL",
            "ollama": "OLLAMA_API_MODEL",
            "qwen": "QWEN_API_MODEL",
        }
        env_var_name = api_model_env_map.get(provider)
        if env_var_name:
            model_name = get_llm_value(env_var_name)
            if model_name:
                return model_name

        provider_friendly_names = {
            "anthropic": "Claude",
            "zhipuai": "智谱AI",
            "openai": "GPT",
            "deepseek": "DeepSeek",
            "ollama": "Ollama",
            "qwen": "通义千问",
        }
        return provider_friendly_names.get(provider, provider.upper())

    @staticmethod
    def _extract_project_url(webhook_data: dict) -> str:
        if not webhook_data:
            return ""

        # GitLab: project.web_url
        project = webhook_data.get("project") or {}
        if isinstance(project, dict):
            url = project.get("web_url")
            if url:
                return url

        # GitHub/Gitea: repository.html_url
        repo = webhook_data.get("repository") or {}
        if isinstance(repo, dict):
            url = repo.get("html_url") or repo.get("url")
            if url:
                return url

        return ""

    @staticmethod
    def init_db():
        """初始化数据库及表结构"""
        try:
            with sqlite3.connect(ReviewService.DB_FILE) as conn:
                cursor = conn.cursor()
                cursor.execute("""
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
                    """)
                cursor.execute("""
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
                    """)
                cursor.execute("""
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
                    """)
                # 确保旧版本的mr_review_log、push_review_log表添加必要字段
                tables_columns = {
                    "mr_review_log": [
                        "additions",
                        "deletions",
                        "status",
                        "retry_count",
                        "last_commit_id",
                        "project_url",
                        "commit_url",
                        "author_display_name",
                        "model_name",
                        "language",
                        "event_id",
                    ],
                    "push_review_log": [
                        "additions",
                        "deletions",
                        "status",
                        "retry_count",
                        "last_commit_id",
                        "project_url",
                        "commit_url",
                        "author_display_name",
                        "model_name",
                        "language",
                        "event_id",
                    ],
                }
                for table, columns in tables_columns.items():
                    cursor.execute(f"PRAGMA table_info({table})")
                    current_columns = [col[1] for col in cursor.fetchall()]
                    for column in columns:
                        if column not in current_columns:
                            if column in ["additions", "deletions", "retry_count"]:
                                cursor.execute(
                                    f"ALTER TABLE {table} ADD COLUMN {column} INTEGER DEFAULT 0"
                                )
                            elif column == "status":
                                cursor.execute(
                                    f"ALTER TABLE {table} ADD COLUMN {column} TEXT DEFAULT 'success'"
                                )
                            elif column == "last_commit_id":
                                cursor.execute(
                                    f"ALTER TABLE {table} ADD COLUMN {column} TEXT DEFAULT ''"
                                )
                            elif column == "project_url":
                                cursor.execute(
                                    f"ALTER TABLE {table} ADD COLUMN {column} TEXT DEFAULT ''"
                                )
                            elif column == "commit_url":
                                cursor.execute(
                                    f"ALTER TABLE {table} ADD COLUMN {column} TEXT DEFAULT ''"
                                )
                            elif column == "author_display_name":
                                cursor.execute(
                                    f"ALTER TABLE {table} ADD COLUMN {column} TEXT DEFAULT ''"
                                )
                            elif column == "model_name":
                                cursor.execute(
                                    f"ALTER TABLE {table} ADD COLUMN {column} TEXT DEFAULT ''"
                                )
                            elif column == "language":
                                cursor.execute(
                                    f"ALTER TABLE {table} ADD COLUMN {column} TEXT DEFAULT ''"
                                )
                            elif column == "event_id":
                                cursor.execute(
                                    f"ALTER TABLE {table} ADD COLUMN {column} INTEGER DEFAULT NULL"
                                )

                conn.commit()
                # 添加时间字段索引
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_push_review_log_updated_at ON "
                    "push_review_log (updated_at);"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_mr_review_log_updated_at ON mr_review_log (updated_at);"
                )
                # 添加 status 索引
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_mr_review_log_status ON mr_review_log (status);"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_push_review_log_status ON push_review_log (status);"
                )
        except sqlite3.DatabaseError as e:
            print(f"Database initialization failed: {e}")

    @staticmethod
    def insert_mr_review_log(entity: MergeRequestReviewEntity, status: str = "success"):
        """插入合并请求审核日志"""
        try:
            with sqlite3.connect(ReviewService.DB_FILE) as conn:
                cursor = conn.cursor()
                model_name = ReviewService._get_model_name_from_env()
                project_url = ReviewService._extract_project_url(entity.webhook_data)
                commit_url = entity.url
                cursor.execute(
                    """
                                INSERT INTO mr_review_log (project_name,author, author_display_name, source_branch, target_branch,
                                updated_at, commit_messages, score, model_name, language, url,review_result, additions, deletions,
                                last_commit_id, status, project_url, commit_url, event_id)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                    (
                        entity.project_name,
                        entity.author,
                        entity.author_display_name,
                        entity.source_branch,
                        entity.target_branch,
                        entity.updated_at,
                        entity.commit_messages,
                        entity.score,
                        model_name,
                        getattr(entity, "language", "") or "",
                        entity.url,
                        entity.review_result,
                        entity.additions,
                        entity.deletions,
                        entity.last_commit_id,
                        status,
                        project_url,
                        commit_url,
                        entity.event_id,
                    ),
                )
                conn.commit()
                return cursor.lastrowid
        except sqlite3.DatabaseError as e:
            print(f"Error inserting review log: {e}")
            return None

    @staticmethod
    def update_mr_review_log(
        record_id: int,
        score: int,
        review_result: str,
        status: str = "success",
        language: str = "",
    ):
        """更新 MR 审查记录（用于重新审查后）"""
        try:
            with sqlite3.connect(ReviewService.DB_FILE) as conn:
                cursor = conn.cursor()
                model_name = ReviewService._get_model_name_from_env()
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
        except sqlite3.DatabaseError as e:
            print(f"Error updating review log: {e}")
            return False

    @staticmethod
    def get_mr_review_logs(
        authors: list = None,
        project_names: list = None,
        updated_at_gte: int = None,
        updated_at_lte: int = None,
    ) -> pd.DataFrame:
        """获取符合条件的合并请求审核日志"""
        try:
            with sqlite3.connect(ReviewService.DB_FILE) as conn:
                query = """
                            SELECT mr.id, mr.project_name, mr.project_url, mr.author, mr.author_display_name, mr.source_branch, mr.target_branch,
                                   COALESCE(ev.created_at, mr.updated_at) AS updated_at,
                                   mr.commit_messages, mr.score, mr.model_name, mr.language, mr.url, mr.review_result, mr.additions, mr.deletions,
                                   mr.status, mr.commit_url
                            FROM mr_review_log mr
                            LEFT JOIN webhook_event_log ev ON mr.event_id = ev.id
                            WHERE 1=1
                            """
                params = []

                if authors:
                    placeholders = ",".join(["?"] * len(authors))
                    query += f" AND (author IN ({placeholders}) OR author_display_name IN ({placeholders}))"
                    params.extend(authors)
                    params.extend(authors)

                if project_names:
                    placeholders = ",".join(["?"] * len(project_names))
                    query += f" AND project_name IN ({placeholders})"
                    params.extend(project_names)

                if updated_at_gte is not None:
                    query += " AND COALESCE(ev.created_at, mr.updated_at) >= ?"
                    params.append(updated_at_gte)

                if updated_at_lte is not None:
                    query += " AND COALESCE(ev.created_at, mr.updated_at) <= ?"
                    params.append(updated_at_lte)
                query += " ORDER BY updated_at DESC"
                df = pd.read_sql_query(sql=query, con=conn, params=params)
            return df
        except sqlite3.DatabaseError as e:
            print(f"Error retrieving review logs: {e}")
            return pd.DataFrame()

    @staticmethod
    def get_mr_review_logs_paginated(
        authors: list | None = None,
        project_names: list | None = None,
        language: str | None = None,
        updated_at_gte: int | None = None,
        updated_at_lte: int | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
        sort: str = "updated_at",
        order: str = "desc",
    ) -> tuple[pd.DataFrame, dict]:
        """获取 MR 审查日志（分页版）。

        返回: (df_page, meta)
          meta: {total, authors, projects, stats}
        """

        allowed_sort = {"updated_at", "score", "project_name", "author", "status"}
        if sort not in allowed_sort:
            sort = "updated_at"
        order = (order or "desc").lower()
        if order not in {"asc", "desc"}:
            order = "desc"

        try:
            with sqlite3.connect(ReviewService.DB_FILE) as conn:
                base_from = " FROM mr_review_log mr LEFT JOIN webhook_event_log ev ON mr.event_id = ev.id"
                base_where = " WHERE 1=1 "
                params: list = []

                if authors:
                    placeholders = ",".join(["?"] * len(authors))
                    base_where += f" AND (mr.author IN ({placeholders}) OR mr.author_display_name IN ({placeholders}))"
                    params.extend(authors)
                    params.extend(authors)

                if project_names:
                    placeholders = ",".join(["?"] * len(project_names))
                    base_where += f" AND mr.project_name IN ({placeholders})"
                    params.extend(project_names)

                if language:
                    base_where += " AND mr.language = ?"
                    params.append(language)

                if updated_at_gte is not None:
                    base_where += " AND COALESCE(ev.created_at, mr.updated_at) >= ?"
                    params.append(updated_at_gte)

                if updated_at_lte is not None:
                    base_where += " AND COALESCE(ev.created_at, mr.updated_at) <= ?"
                    params.append(updated_at_lte)

                if status in {"success", "failed"}:
                    base_where += " AND mr.status = ?"
                    params.append(status)

                # total
                total_query = "SELECT COUNT(*)" + base_from + base_where
                total = conn.execute(total_query, params).fetchone()[0]

                # filters (from filtered dataset)
                authors_query = (
                    "SELECT DISTINCT mr.author_display_name" + base_from + base_where
                )
                authors_list = []
                for row in conn.execute(authors_query, params).fetchall():
                    if not row:
                        continue
                    display_name = (row[0] or "").strip()
                    if display_name:
                        authors_list.append(display_name)
                projects_query = (
                    "SELECT DISTINCT mr.project_name" + base_from + base_where
                )
                projects_list = [
                    r[0]
                    for r in conn.execute(projects_query, params).fetchall()
                    if r and r[0]
                ]

                languages_query = "SELECT DISTINCT mr.language" + base_from + base_where
                languages_list = [
                    r[0]
                    for r in conn.execute(languages_query, params).fetchall()
                    if r and r[0]
                ]

                # stats (from filtered dataset)
                stats_query = (
                    "SELECT "
                    "SUM(CASE WHEN mr.status != 'failed' AND mr.score IS NOT NULL AND mr.score != 0 THEN 1 ELSE 0 END) as total, "
                    "SUM(CASE WHEN mr.status='success' THEN 1 ELSE 0 END) as success, "
                    "SUM(CASE WHEN mr.status='failed' THEN 1 ELSE 0 END) as failed, "
                    "AVG(CASE WHEN mr.status != 'failed' AND mr.score IS NOT NULL AND mr.score != 0 THEN mr.score END) as avg_score "
                    + base_from
                    + base_where
                )
                stats_row = conn.execute(stats_query, params).fetchone()
                stats = {
                    "total": int(stats_row[0] or 0),
                    "success": int(stats_row[1] or 0),
                    "failed": int(stats_row[2] or 0),
                    "avg_score": round(float(stats_row[3] or 0), 1),
                }

                sort_map = {
                    "updated_at": "updated_at",
                    "score": "mr.score",
                    "project_name": "mr.project_name",
                    "author": "mr.author",
                    "status": "mr.status",
                }
                order_by = sort_map.get(sort, "updated_at")
                query = (
                    "SELECT mr.id, mr.project_name, mr.project_url, mr.author, mr.author_display_name, mr.source_branch, mr.target_branch, "
                    "COALESCE(ev.created_at, mr.updated_at) AS updated_at, "
                    "mr.commit_messages, mr.score, mr.model_name, mr.language, mr.url, mr.review_result, mr.additions, mr.deletions, mr.status, mr.commit_url "
                    + base_from
                    + base_where
                    + f" ORDER BY {order_by} {order} LIMIT ? OFFSET ?"
                )
                page_params = params + [int(limit), int(offset)]
                df = pd.read_sql_query(sql=query, con=conn, params=page_params)

            if not df.empty and "author_display_name" in df.columns:
                pass

            meta = {
                "total": int(total or 0),
                "authors": sorted(set(authors_list)),
                "projects": sorted(set(projects_list)),
                "languages": sorted(set(languages_list)),
                "stats": stats,
            }
            return df, meta
        except sqlite3.DatabaseError as e:
            print(f"Error retrieving paginated MR review logs: {e}")
            return pd.DataFrame(), {
                "total": 0,
                "authors": [],
                "projects": [],
                "stats": {"total": 0, "success": 0, "failed": 0, "avg_score": 0},
            }

    @staticmethod
    def check_mr_last_commit_id_exists(
        project_name: str, source_branch: str, target_branch: str, last_commit_id: str
    ) -> bool:
        """检查指定项目的Merge Request是否已经存在相同的last_commit_id"""
        try:
            with sqlite3.connect(ReviewService.DB_FILE) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT COUNT(*) FROM mr_review_log 
                    WHERE project_name = ? AND source_branch = ? AND target_branch = ? AND last_commit_id = ?
                """,
                    (project_name, source_branch, target_branch, last_commit_id),
                )
                count = cursor.fetchone()[0]
                return count > 0
        except sqlite3.DatabaseError as e:
            print(f"Error checking last_commit_id: {e}")
            return False

    @staticmethod
    def insert_push_review_log(entity: PushReviewEntity, status: str = "success"):
        """插入推送审核日志"""
        try:
            with sqlite3.connect(ReviewService.DB_FILE) as conn:
                cursor = conn.cursor()
                model_name = ReviewService._get_model_name_from_env()
                project_url = ReviewService._extract_project_url(entity.webhook_data)
                commit_url = entity.commits[-1].get("url", "") if entity.commits else ""
                cursor.execute(
                    """
                                INSERT INTO push_review_log (project_name,author, author_display_name, branch, updated_at, commit_messages, score, model_name, language, review_result, additions, deletions, status, project_url, commit_url, event_id, last_commit_id)
                                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                    (
                        entity.project_name,
                        entity.author,
                        entity.author_display_name,
                        entity.branch,
                        entity.updated_at,
                        entity.commit_messages,
                        entity.score,
                        model_name,
                        getattr(entity, "language", "") or "",
                        entity.review_result,
                        entity.additions,
                        entity.deletions,
                        status,
                        project_url,
                        commit_url,
                        entity.event_id,
                        (entity.commits[-1].get("id") if entity.commits else "") or "",
                    ),
                )
                conn.commit()
                return cursor.lastrowid
        except sqlite3.DatabaseError as e:
            print(f"Error inserting review log: {e}")
            return None

    @staticmethod
    def update_push_review_log(
        record_id: int,
        score: int,
        review_result: str,
        status: str = "success",
        language: str = "",
    ):
        """更新 Push 审查记录（用于重新审查后）"""
        try:
            with sqlite3.connect(ReviewService.DB_FILE) as conn:
                cursor = conn.cursor()
                model_name = ReviewService._get_model_name_from_env()
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
        except sqlite3.DatabaseError as e:
            print(f"Error updating review log: {e}")
            return False

    @staticmethod
    def get_failed_mr_review_logs() -> pd.DataFrame:
        """获取失败的 MR 审查记录"""
        try:
            with sqlite3.connect(ReviewService.DB_FILE) as conn:
                query = """
                    SELECT id, project_name, author, author_display_name, source_branch, target_branch, updated_at, 
                           commit_messages, score, url, review_result, additions, deletions, last_commit_id, retry_count
                    FROM mr_review_log
                    WHERE status = 'failed'
                    ORDER BY updated_at DESC
                """
                df = pd.read_sql_query(sql=query, con=conn)
                if not df.empty and "author_display_name" in df.columns:
                    df["author"] = df["author_display_name"].where(
                        df["author_display_name"].astype(str).str.strip() != "",
                        df["author"],
                    )
                return df
        except sqlite3.DatabaseError as e:
            print(f"Error retrieving failed review logs: {e}")
            return pd.DataFrame()

    @staticmethod
    def get_failed_push_review_logs() -> pd.DataFrame:
        """获取失败的 Push 审查记录"""
        try:
            with sqlite3.connect(ReviewService.DB_FILE) as conn:
                query = """
                    SELECT id, project_name, author, author_display_name, branch, updated_at, 
                           commit_messages, score, review_result, additions, deletions, retry_count
                    FROM push_review_log
                    WHERE status = 'failed'
                    ORDER BY updated_at DESC
                """
                df = pd.read_sql_query(sql=query, con=conn)
                if not df.empty and "author_display_name" in df.columns:
                    df["author"] = df["author_display_name"].where(
                        df["author_display_name"].astype(str).str.strip() != "",
                        df["author"],
                    )
                return df
        except sqlite3.DatabaseError as e:
            print(f"Error retrieving failed review logs: {e}")
            return pd.DataFrame()

    @staticmethod
    def get_mr_review_log_by_id(record_id: int) -> dict | None:
        """根据 ID 获取 MR 审查记录"""
        try:
            with sqlite3.connect(ReviewService.DB_FILE) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT id, project_name, project_url, author, author_display_name, source_branch, target_branch, updated_at, 
                           commit_messages, score, model_name, language, url, review_result, additions, deletions, last_commit_id, status, retry_count, commit_url, event_id
                    FROM mr_review_log WHERE id = ?
                """,
                    (record_id,),
                )
                row = cursor.fetchone()
                if row:
                    return {
                        "id": row[0],
                        "project_name": row[1],
                        "project_url": row[2],
                        "author": row[4] if row[4] else row[3],
                        "author_username": row[3],
                        "author_display_name": row[4] or "",
                        "source_branch": row[5],
                        "target_branch": row[6],
                        "updated_at": row[7],
                        "commit_messages": row[8],
                        "score": row[9],
                        "model_name": row[10],
                        "language": row[11] or "",
                        "url": row[12],
                        "review_result": row[13],
                        "additions": row[14],
                        "deletions": row[15],
                        "last_commit_id": row[16],
                        "status": row[17],
                        "retry_count": row[18],
                        "commit_url": row[19],
                        "event_id": row[20],
                    }
                return None
        except sqlite3.DatabaseError as e:
            print(f"Error retrieving review log: {e}")
            return None

    @staticmethod
    def get_push_review_log_by_id(record_id: int) -> dict | None:
        """根据 ID 获取 Push 审查记录"""
        try:
            with sqlite3.connect(ReviewService.DB_FILE) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT id, project_name, project_url, author, author_display_name, branch, updated_at, 
                           commit_messages, score, model_name, language, review_result, additions, deletions, last_commit_id, status, retry_count, commit_url, event_id
                    FROM push_review_log WHERE id = ?
                """,
                    (record_id,),
                )
                row = cursor.fetchone()
                if row:
                    return {
                        "id": row[0],
                        "project_name": row[1],
                        "project_url": row[2],
                        "author": row[4] if row[4] else row[3],
                        "author_username": row[3],
                        "author_display_name": row[4] or "",
                        "branch": row[5],
                        "updated_at": row[6],
                        "commit_messages": row[7],
                        "score": row[8],
                        "model_name": row[9],
                        "language": row[10] or "",
                        "review_result": row[11],
                        "additions": row[12],
                        "deletions": row[13],
                        "last_commit_id": row[14],
                        "status": row[15],
                        "retry_count": row[16],
                        "commit_url": row[17],
                        "event_id": row[18],
                    }
                return None
        except sqlite3.DatabaseError as e:
            print(f"Error retrieving review log: {e}")
            return None

    @staticmethod
    def get_push_review_logs(
        authors: list = None,
        project_names: list = None,
        updated_at_gte: int = None,
        updated_at_lte: int = None,
    ) -> pd.DataFrame:
        """获取符合条件的推送审核日志"""
        try:
            with sqlite3.connect(ReviewService.DB_FILE) as conn:
                # 基础查询
                query = """
                    SELECT pr.id, pr.project_name, pr.project_url, pr.author, pr.author_display_name, pr.branch,
                           COALESCE(ev.created_at, pr.updated_at) AS updated_at,
                           pr.commit_messages, pr.score, pr.model_name, pr.language, pr.review_result, pr.additions, pr.deletions, pr.status, pr.commit_url
                    FROM push_review_log pr
                    LEFT JOIN webhook_event_log ev ON pr.event_id = ev.id
                    WHERE 1=1
                """
                params = []

                # 动态添加 authors 条件
                if authors:
                    placeholders = ",".join(["?"] * len(authors))
                    query += f" AND (author IN ({placeholders}) OR author_display_name IN ({placeholders}))"
                    params.extend(authors)
                    params.extend(authors)

                if project_names:
                    placeholders = ",".join(["?"] * len(project_names))
                    query += f" AND project_name IN ({placeholders})"
                    params.extend(project_names)

                # 动态添加 updated_at_gte 条件
                if updated_at_gte is not None:
                    query += " AND COALESCE(ev.created_at, pr.updated_at) >= ?"
                    params.append(updated_at_gte)

                # 动态添加 updated_at_lte 条件
                if updated_at_lte is not None:
                    query += " AND COALESCE(ev.created_at, pr.updated_at) <= ?"
                    params.append(updated_at_lte)

                # 按 updated_at 降序排序
                query += " ORDER BY updated_at DESC"

                # 执行查询
                df = pd.read_sql_query(sql=query, con=conn, params=params)
                return df
        except sqlite3.DatabaseError as e:
            print(f"Error retrieving push review logs: {e}")
            return pd.DataFrame()

    @staticmethod
    def get_push_review_logs_paginated(
        authors: list | None = None,
        project_names: list | None = None,
        language: str | None = None,
        updated_at_gte: int | None = None,
        updated_at_lte: int | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
        sort: str = "updated_at",
        order: str = "desc",
    ) -> tuple[pd.DataFrame, dict]:
        """获取 Push 审查日志（分页版）。

        返回: (df_page, meta)
          meta: {total, authors, projects, stats}
        """

        allowed_sort = {"updated_at", "score", "project_name", "author", "status"}
        if sort not in allowed_sort:
            sort = "updated_at"
        order = (order or "desc").lower()
        if order not in {"asc", "desc"}:
            order = "desc"

        try:
            with sqlite3.connect(ReviewService.DB_FILE) as conn:
                base_where = " WHERE 1=1 "
                params: list = []

                if authors:
                    placeholders = ",".join(["?"] * len(authors))
                    base_where += f" AND (author IN ({placeholders}) OR author_display_name IN ({placeholders}))"
                    params.extend(authors)
                    params.extend(authors)

                if project_names:
                    placeholders = ",".join(["?"] * len(project_names))
                    base_where += f" AND project_name IN ({placeholders})"
                    params.extend(project_names)

                if language:
                    base_where += " AND language = ?"
                    params.append(language)

                if updated_at_gte is not None:
                    base_where += " AND updated_at >= ?"
                    params.append(updated_at_gte)

                if updated_at_lte is not None:
                    base_where += " AND updated_at <= ?"
                    params.append(updated_at_lte)

                if status in {"success", "failed"}:
                    base_where += " AND status = ?"
                    params.append(status)

                total_query = "SELECT COUNT(*) FROM push_review_log" + base_where
                total = conn.execute(total_query, params).fetchone()[0]

                authors_query = (
                    "SELECT DISTINCT author_display_name FROM push_review_log"
                    + base_where
                )
                authors_list = []
                for row in conn.execute(authors_query, params).fetchall():
                    if not row:
                        continue
                    display_name = (row[0] or "").strip()
                    if display_name:
                        authors_list.append(display_name)
                projects_query = (
                    "SELECT DISTINCT project_name FROM push_review_log" + base_where
                )
                projects_list = [
                    r[0]
                    for r in conn.execute(projects_query, params).fetchall()
                    if r and r[0]
                ]

                languages_query = (
                    "SELECT DISTINCT language FROM push_review_log" + base_where
                )
                languages_list = [
                    r[0]
                    for r in conn.execute(languages_query, params).fetchall()
                    if r and r[0]
                ]

                stats_query = (
                    "SELECT "
                    "SUM(CASE WHEN status != 'failed' AND score IS NOT NULL AND score != 0 THEN 1 ELSE 0 END) as total, "
                    "SUM(CASE WHEN status='success' THEN 1 ELSE 0 END) as success, "
                    "SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) as failed, "
                    "AVG(CASE WHEN status != 'failed' AND score IS NOT NULL AND score != 0 THEN score END) as avg_score "
                    "FROM push_review_log" + base_where
                )
                stats_row = conn.execute(stats_query, params).fetchone()
                stats = {
                    "total": int(stats_row[0] or 0),
                    "success": int(stats_row[1] or 0),
                    "failed": int(stats_row[2] or 0),
                    "avg_score": round(float(stats_row[3] or 0), 1),
                }

                query = (
                    "SELECT id, project_name, project_url, author, author_display_name, branch, updated_at, commit_messages, score, model_name, language, review_result, additions, deletions, status, commit_url "
                    "FROM push_review_log"
                    + base_where
                    + f" ORDER BY {sort} {order} LIMIT ? OFFSET ?"
                )
                page_params = params + [int(limit), int(offset)]
                df = pd.read_sql_query(sql=query, con=conn, params=page_params)

            if not df.empty and "author_display_name" in df.columns:
                pass

            meta = {
                "total": int(total or 0),
                "authors": sorted(set(authors_list)),
                "projects": sorted(set(projects_list)),
                "languages": sorted(set(languages_list)),
                "stats": stats,
            }
            return df, meta
        except sqlite3.DatabaseError as e:
            print(f"Error retrieving paginated push review logs: {e}")
            return pd.DataFrame(), {
                "total": 0,
                "authors": [],
                "projects": [],
                "stats": {"total": 0, "success": 0, "failed": 0, "avg_score": 0},
            }


# Initialize database
ReviewService.init_db()
