import sqlite3
import tempfile
import time
import unittest
from pathlib import Path


class TestReviewServicePagination(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self._tmp.name) / "test.db")

        from biz.service.review_service import ReviewService

        ReviewService.DB_FILE = self.db_path
        ReviewService.init_db()
        self.ReviewService = ReviewService

    def tearDown(self):
        self._tmp.cleanup()

    def _seed_push(self, rows=8):
        now = int(time.time())
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            for i in range(rows):
                cur.execute(
                    """
                    INSERT INTO push_review_log (
                        project_name, project_url, author, author_display_name,
                        branch, updated_at,
                        commit_messages, score, review_result,
                        additions, deletions,
                        status, retry_count, commit_url, last_commit_id, language
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "projA" if i % 2 == 0 else "projB",
                        "https://gitlab.example.com/group/proj",
                        "alice" if i % 2 == 0 else "bob",
                        "",
                        "main",
                        now - i,
                        f"push commit {i}",
                        90 - i,
                        f"push review {i}",
                        5 + i,
                        1 + i,
                        "success" if i % 3 != 0 else "failed",
                        i,
                        "https://gitlab.example.com/commit/sha",
                        f"c{i}",
                        "Python",
                    ),
                )
            conn.commit()

    def _seed_mr(self, rows=8):
        now = int(time.time())
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            for i in range(rows):
                cur.execute(
                    """
                    INSERT INTO mr_review_log (
                        project_name, project_url, author, author_display_name,
                        source_branch, target_branch, updated_at,
                        commit_messages, score, url, review_result,
                        additions, deletions, last_commit_id,
                        status, retry_count, commit_url, language
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "projA" if i % 2 == 0 else "projB",
                        "https://gitlab.example.com/group/proj",
                        "alice" if i % 2 == 0 else "bob",
                        "",
                        "feat",
                        "main",
                        now - i,
                        f"mr commit {i}",
                        70 - i,
                        "https://gitlab.example.com/mr/1",
                        f"mr review {i}",
                        10 + i,
                        3 + i,
                        f"m{i}",
                        "success" if i % 4 != 0 else "failed",
                        i,
                        "https://gitlab.example.com/commit/sha",
                        "JavaScript",
                    ),
                )
            conn.commit()

    def test_push_paginated_total_and_page_size(self):
        self._seed_push(rows=7)
        df, meta = self.ReviewService.get_push_review_logs_paginated(
            limit=3, offset=0, sort="updated_at", order="desc"
        )
        self.assertEqual(meta["total"], 7)
        self.assertEqual(len(df), 3)

        df2, _meta2 = self.ReviewService.get_push_review_logs_paginated(
            limit=3, offset=6, sort="updated_at", order="desc"
        )
        self.assertEqual(len(df2), 1)

    def test_push_filter_status(self):
        self._seed_push(rows=9)
        df, meta = self.ReviewService.get_push_review_logs_paginated(
            status="failed", limit=50, offset=0
        )
        self.assertGreater(meta["total"], 0)
        self.assertTrue((df["status"] == "failed").all())

    def test_push_filter_author(self):
        self._seed_push(rows=10)
        df, meta = self.ReviewService.get_push_review_logs_paginated(
            authors=["alice"], limit=50, offset=0
        )
        self.assertGreaterEqual(meta["total"], 1)
        self.assertTrue((df["author"] == "alice").all())

    def test_push_sort_score_asc(self):
        self._seed_push(rows=6)
        df, _meta = self.ReviewService.get_push_review_logs_paginated(
            limit=6, offset=0, sort="score", order="asc"
        )
        scores = df["score"].tolist()
        self.assertEqual(scores, sorted(scores))

    def test_mr_paginated_total_and_filters(self):
        self._seed_mr(rows=9)

        df, meta = self.ReviewService.get_mr_review_logs_paginated(
            limit=4, offset=0, sort="updated_at", order="desc"
        )
        self.assertEqual(meta["total"], 9)
        self.assertEqual(len(df), 4)

        df2, meta2 = self.ReviewService.get_mr_review_logs_paginated(
            authors=["alice"], status="failed", limit=50, offset=0
        )
        # If there are no failed entries for alice, total could be 0; still should be consistent.
        self.assertEqual(int(meta2["total"]), len(df2))
        if meta2["total"]:
            self.assertTrue((df2["author"] == "alice").all())
            self.assertTrue((df2["status"] == "failed").all())

    def test_push_filter_language(self):
        self._seed_push(rows=6)
        df, meta = self.ReviewService.get_push_review_logs_paginated(
            language="Python", limit=50, offset=0
        )
        self.assertGreaterEqual(meta["total"], 1)
        self.assertTrue((df["language"] == "Python").all())


if __name__ == "__main__":
    unittest.main()
