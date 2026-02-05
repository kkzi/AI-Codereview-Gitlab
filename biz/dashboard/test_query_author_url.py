import os
import unittest

import pandas as pd


class TestDashboardAuthorUrl(unittest.TestCase):
    def tearDown(self):
        # Keep env clean across tests.
        for k in ("GITLAB_URL", "GITEA_URL", "GITHUB_URL"):
            os.environ.pop(k, None)

    def _serialize(self, rows):
        from biz.dashboard.query import serialize_dataframe

        df = pd.DataFrame(rows)
        return serialize_dataframe(df, data_type="push")

    def test_gitlab_self_hosted_author_url_uses_env_host(self):
        os.environ["GITLAB_URL"] = "https://code.example.com"
        records = self._serialize(
            [
                {
                    "id": 1,
                    "project_url": "https://code.example.com/group/proj",
                    "commit_url": "https://code.example.com/group/proj/-/commit/abc",
                    "author": "alice",
                    "author_display_name": "Alice",
                    "additions": 1,
                    "deletions": 1,
                    "score": 10,
                    "updated_at": 0,
                }
            ]
        )
        self.assertEqual(records[0]["author_url"], "https://code.example.com/alice")

    def test_gitea_self_hosted_author_url_uses_env_host(self):
        os.environ["GITEA_URL"] = "https://git.example.net"
        records = self._serialize(
            [
                {
                    "id": 1,
                    "project_url": "https://git.example.net/org/proj",
                    "commit_url": "https://git.example.net/api/v1/repos/org/proj/git/commits/abc",
                    "author": "bob",
                    "author_display_name": "",
                    "additions": 0,
                    "deletions": 0,
                    "score": 0,
                    "updated_at": 0,
                }
            ]
        )
        self.assertEqual(records[0]["author_url"], "https://git.example.net/bob")

    def test_github_enterprise_author_url_uses_env_host(self):
        os.environ["GITHUB_URL"] = "https://github.company.com"
        records = self._serialize(
            [
                {
                    "id": 1,
                    "project_url": "https://github.company.com/acme/proj",
                    "commit_url": "https://api.github.com/repos/acme/proj/commits/abc",
                    "author": "carol",
                    "author_display_name": "Carol",
                    "additions": 2,
                    "deletions": 1,
                    "score": 50,
                    "updated_at": 0,
                }
            ]
        )
        self.assertEqual(records[0]["author_url"], "https://github.company.com/carol")

    def test_github_api_commit_url_does_not_force_api_base(self):
        os.environ["GITHUB_URL"] = "https://github.com"
        records = self._serialize(
            [
                {
                    "id": 1,
                    "project_url": "",
                    "commit_url": "https://api.github.com/repos/openai/codex/commits/abc",
                    "author": "octocat",
                    "author_display_name": "",
                    "additions": 0,
                    "deletions": 0,
                    "score": 0,
                    "updated_at": 0,
                }
            ]
        )
        self.assertEqual(records[0]["author_url"], "https://github.com/octocat")


if __name__ == "__main__":
    unittest.main()

