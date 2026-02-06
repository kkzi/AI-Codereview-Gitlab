import json
import sqlite3
from typing import Any, Dict, Optional

from biz.service.review_service import ReviewService


class EventService:
    @staticmethod
    def insert_event(
        review_type: str,
        source: str,
        event_type: str,
        project_name: str,
        project_url: str,
        payload: Dict[str, Any],
        created_at: int,
    ) -> Optional[int]:
        try:
            with sqlite3.connect(ReviewService.DB_FILE) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO webhook_event_log (review_type, source, event_type, project_name, project_url, created_at, payload)
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

    @staticmethod
    def get_event_payload(event_id: int) -> Optional[Dict[str, Any]]:
        try:
            with sqlite3.connect(ReviewService.DB_FILE) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT payload FROM webhook_event_log WHERE id = ?
                    """,
                    (event_id,),
                )
                row = cursor.fetchone()
                if not row or not row[0]:
                    return None
                return json.loads(row[0])
        except Exception:
            return None

    @staticmethod
    def get_event_record(event_id: int) -> Optional[Dict[str, Any]]:
        try:
            with sqlite3.connect(ReviewService.DB_FILE) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT review_type, source, event_type, project_name, project_url, created_at, payload
                    FROM webhook_event_log WHERE id = ?
                    """,
                    (event_id,),
                )
                row = cursor.fetchone()
                if not row:
                    return None
                payload = json.loads(row[6]) if row[6] else None
                return {
                    "review_type": row[0],
                    "source": row[1],
                    "event_type": row[2],
                    "project_name": row[3],
                    "project_url": row[4],
                    "created_at": row[5],
                    "payload": payload,
                }
        except Exception:
            return None
