import sqlite3
import datetime

import pandas as pd

from biz.entity.review_entity import MergeRequestReviewEntity, PushReviewEntity


class ReviewService:
    DB_FILE = "data/data.db"

    @staticmethod
    def init_db():
        """初始化数据库及表结构"""
        try:
            with sqlite3.connect(ReviewService.DB_FILE) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                        CREATE TABLE IF NOT EXISTS mr_review_log (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            project_name TEXT,
                            author TEXT,
                            source_branch TEXT,
                            target_branch TEXT,
                            updated_at INTEGER,
                            commit_messages TEXT,
                            score INTEGER,
                            url TEXT,
                            review_result TEXT,
                            additions INTEGER DEFAULT 0,
                            deletions INTEGER DEFAULT 0,
                            last_commit_id TEXT DEFAULT '',
                            status TEXT DEFAULT 'success',
                            retry_count INTEGER DEFAULT 0
                        )
                    ''')
                cursor.execute('''
                        CREATE TABLE IF NOT EXISTS push_review_log (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            project_name TEXT,
                            author TEXT,
                            branch TEXT,
                            updated_at INTEGER,
                            commit_messages TEXT,
                            score INTEGER,
                            review_result TEXT,
                            additions INTEGER DEFAULT 0,
                            deletions INTEGER DEFAULT 0,
                            status TEXT DEFAULT 'success',
                            retry_count INTEGER DEFAULT 0
                        )
                    ''')
                # 确保旧版本的mr_review_log、push_review_log表添加必要字段
                tables_columns = {
                    "mr_review_log": ["additions", "deletions", "status", "retry_count", "last_commit_id", "project_url", "commit_url"],
                    "push_review_log": ["additions", "deletions", "status", "retry_count", "project_url", "commit_url"]
                }
                for table, columns in tables_columns.items():
                    cursor.execute(f"PRAGMA table_info({table})")
                    current_columns = [col[1] for col in cursor.fetchall()]
                    for column in columns:
                        if column not in current_columns:
                            if column in ["additions", "deletions", "retry_count"]:
                                cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} INTEGER DEFAULT 0")
                            elif column == "status":
                                cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} TEXT DEFAULT 'success'")
                            elif column == "last_commit_id":
                                cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} TEXT DEFAULT ''")
                            elif column == "project_url":
                                cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} TEXT DEFAULT ''")
                            elif column == "commit_url":
                                cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} TEXT DEFAULT ''")

                conn.commit()
                # 添加时间字段索引
                conn.execute('CREATE INDEX IF NOT EXISTS idx_push_review_log_updated_at ON '
                             'push_review_log (updated_at);')
                conn.execute('CREATE INDEX IF NOT EXISTS idx_mr_review_log_updated_at ON mr_review_log (updated_at);')
                # 添加 status 索引
                conn.execute('CREATE INDEX IF NOT EXISTS idx_mr_review_log_status ON mr_review_log (status);')
                conn.execute('CREATE INDEX IF NOT EXISTS idx_push_review_log_status ON push_review_log (status);')
        except sqlite3.DatabaseError as e:
            print(f"Database initialization failed: {e}")

    @staticmethod
    def insert_mr_review_log(entity: MergeRequestReviewEntity, status: str = "success"):
        """插入合并请求审核日志"""
        try:
            with sqlite3.connect(ReviewService.DB_FILE) as conn:
                cursor = conn.cursor()
                project_url = entity.webhook_data.get('project', {}).get('web_url', '') if entity.webhook_data else ''
                commit_url = entity.url
                cursor.execute('''
                                INSERT INTO mr_review_log (project_name,author, source_branch, target_branch,
                                updated_at, commit_messages, score, url,review_result, additions, deletions,
                                last_commit_id, status, project_url, commit_url)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            ''',
                               (entity.project_name, entity.author, entity.source_branch,
                                 entity.target_branch, entity.updated_at, entity.commit_messages, entity.score,
                                 entity.url, entity.review_result, entity.additions, entity.deletions,
                                 entity.last_commit_id, status, project_url, commit_url))
                conn.commit()
                return cursor.lastrowid
        except sqlite3.DatabaseError as e:
            print(f"Error inserting review log: {e}")
            return None

    @staticmethod
    def update_mr_review_log(record_id: int, score: int, review_result: str, status: str = "success"):
        """更新 MR 审查记录（用于重新审查后）"""
        try:
            with sqlite3.connect(ReviewService.DB_FILE) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE mr_review_log 
                    SET score = ?, review_result = ?, status = ?, updated_at = ?, retry_count = retry_count + 1
                    WHERE id = ?
                ''', (score, review_result, status, int(datetime.datetime.now().timestamp()), record_id))
                conn.commit()
                return cursor.rowcount > 0
        except sqlite3.DatabaseError as e:
            print(f"Error updating review log: {e}")
            return False

    @staticmethod
    def get_mr_review_logs(authors: list = None, project_names: list = None, updated_at_gte: int = None,
                           updated_at_lte: int = None) -> pd.DataFrame:
        """获取符合条件的合并请求审核日志"""
        try:
            with sqlite3.connect(ReviewService.DB_FILE) as conn:
                query = """
                            SELECT id, project_name, project_url, author, source_branch, target_branch, updated_at, commit_messages, score, url, review_result, additions, deletions, status, commit_url
                            FROM mr_review_log
                            WHERE 1=1
                            """
                params = []

                if authors:
                    placeholders = ','.join(['?'] * len(authors))
                    query += f" AND author IN ({placeholders})"
                    params.extend(authors)

                if project_names:
                    placeholders = ','.join(['?'] * len(project_names))
                    query += f" AND project_name IN ({placeholders})"
                    params.extend(project_names)

                if updated_at_gte is not None:
                    query += " AND updated_at >= ?"
                    params.append(updated_at_gte)

                if updated_at_lte is not None:
                    query += " AND updated_at <= ?"
                    params.append(updated_at_lte)
                query += " ORDER BY updated_at DESC"
                df = pd.read_sql_query(sql=query, con=conn, params=params)
            return df
        except sqlite3.DatabaseError as e:
            print(f"Error retrieving review logs: {e}")
            return pd.DataFrame()

    @staticmethod
    def check_mr_last_commit_id_exists(project_name: str, source_branch: str, target_branch: str, last_commit_id: str) -> bool:
        """检查指定项目的Merge Request是否已经存在相同的last_commit_id"""
        try:
            with sqlite3.connect(ReviewService.DB_FILE) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT COUNT(*) FROM mr_review_log 
                    WHERE project_name = ? AND source_branch = ? AND target_branch = ? AND last_commit_id = ?
                ''', (project_name, source_branch, target_branch, last_commit_id))
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
                project_url = entity.webhook_data.get('project', {}).get('web_url', '') if entity.webhook_data else ''
                commit_url = entity.commits[-1].get('url', '') if entity.commits else ''
                cursor.execute('''
                                INSERT INTO push_review_log (project_name,author, branch, updated_at, commit_messages, score,review_result, additions, deletions, status, project_url, commit_url)
                                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            ''',
                               (entity.project_name, entity.author, entity.branch,
                                 entity.updated_at, entity.commit_messages, entity.score,
                                 entity.review_result, entity.additions, entity.deletions, status, project_url, commit_url))
                conn.commit()
                return cursor.lastrowid
        except sqlite3.DatabaseError as e:
            print(f"Error inserting review log: {e}")
            return None

    @staticmethod
    def update_push_review_log(record_id: int, score: int, review_result: str, status: str = "success"):
        """更新 Push 审查记录（用于重新审查后）"""
        try:
            with sqlite3.connect(ReviewService.DB_FILE) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE push_review_log 
                    SET score = ?, review_result = ?, status = ?, updated_at = ?, retry_count = retry_count + 1
                    WHERE id = ?
                ''', (score, review_result, status, int(datetime.datetime.now().timestamp()), record_id))
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
                    SELECT id, project_name, author, source_branch, target_branch, updated_at, 
                           commit_messages, score, url, review_result, additions, deletions, last_commit_id, retry_count
                    FROM mr_review_log
                    WHERE status = 'failed'
                    ORDER BY updated_at DESC
                """
                return pd.read_sql_query(sql=query, con=conn)
        except sqlite3.DatabaseError as e:
            print(f"Error retrieving failed review logs: {e}")
            return pd.DataFrame()

    @staticmethod
    def get_failed_push_review_logs() -> pd.DataFrame:
        """获取失败的 Push 审查记录"""
        try:
            with sqlite3.connect(ReviewService.DB_FILE) as conn:
                query = """
                    SELECT id, project_name, author, branch, updated_at, 
                           commit_messages, score, review_result, additions, deletions, retry_count
                    FROM push_review_log
                    WHERE status = 'failed'
                    ORDER BY updated_at DESC
                """
                return pd.read_sql_query(sql=query, con=conn)
        except sqlite3.DatabaseError as e:
            print(f"Error retrieving failed review logs: {e}")
            return pd.DataFrame()

    @staticmethod
    def get_mr_review_log_by_id(record_id: int) -> dict:
        """根据 ID 获取 MR 审查记录"""
        try:
            with sqlite3.connect(ReviewService.DB_FILE) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT id, project_name, author, source_branch, target_branch, updated_at, 
                           commit_messages, score, url, review_result, additions, deletions, last_commit_id
                    FROM mr_review_log WHERE id = ?
                ''', (record_id,))
                row = cursor.fetchone()
                if row:
                    return {
                        "id": row[0],
                        "project_name": row[1],
                        "author": row[2],
                        "source_branch": row[3],
                        "target_branch": row[4],
                        "updated_at": row[5],
                        "commit_messages": row[6],
                        "score": row[7],
                        "url": row[8],
                        "review_result": row[9],
                        "additions": row[10],
                        "deletions": row[11],
                        "last_commit_id": row[12]
                    }
                return None
        except sqlite3.DatabaseError as e:
            print(f"Error retrieving review log: {e}")
            return None

    @staticmethod
    def get_push_review_log_by_id(record_id: int) -> dict:
        """根据 ID 获取 Push 审查记录"""
        try:
            with sqlite3.connect(ReviewService.DB_FILE) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT id, project_name, author, branch, updated_at, 
                           commit_messages, score, review_result, additions, deletions
                    FROM push_review_log WHERE id = ?
                ''', (record_id,))
                row = cursor.fetchone()
                if row:
                    return {
                        "id": row[0],
                        "project_name": row[1],
                        "author": row[2],
                        "branch": row[3],
                        "updated_at": row[4],
                        "commit_messages": row[5],
                        "score": row[6],
                        "review_result": row[7],
                        "additions": row[8],
                        "deletions": row[9]
                    }
                return None
        except sqlite3.DatabaseError as e:
            print(f"Error retrieving review log: {e}")
            return None

    @staticmethod
    def get_push_review_logs(authors: list = None, project_names: list = None, updated_at_gte: int = None,
                             updated_at_lte: int = None) -> pd.DataFrame:
        """获取符合条件的推送审核日志"""
        try:
            with sqlite3.connect(ReviewService.DB_FILE) as conn:
                # 基础查询
                query = """
                    SELECT id, project_name, project_url, author, branch, updated_at, commit_messages, score, review_result, additions, deletions, status, commit_url
                    FROM push_review_log
                    WHERE 1=1
                """
                params = []

                # 动态添加 authors 条件
                if authors:
                    placeholders = ','.join(['?'] * len(authors))
                    query += f" AND author IN ({placeholders})"
                    params.extend(authors)

                if project_names:
                    placeholders = ','.join(['?'] * len(project_names))
                    query += f" AND project_name IN ({placeholders})"
                    params.extend(project_names)

                # 动态添加 updated_at_gte 条件
                if updated_at_gte is not None:
                    query += " AND updated_at >= ?"
                    params.append(updated_at_gte)

                # 动态添加 updated_at_lte 条件
                if updated_at_lte is not None:
                    query += " AND updated_at <= ?"
                    params.append(updated_at_lte)

                # 按 updated_at 降序排序
                query += " ORDER BY updated_at DESC"

                # 执行查询
                df = pd.read_sql_query(sql=query, con=conn, params=params)
                return df
        except sqlite3.DatabaseError as e:
            print(f"Error retrieving push review logs: {e}")
            return pd.DataFrame()


# Initialize database
ReviewService.init_db()
