from __future__ import annotations

import os
import re
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

from app.core.logging import get_logger
from app.infra.scm.gitlab import request_with_retry


logger = get_logger(__name__)


def _base_url(url: str) -> str:
    if not url:
        return ""
    try:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return ""
        return f"{parsed.scheme}://{parsed.netloc}"
    except Exception:
        return ""


def resolve_github_url(payload: Dict[str, Any]) -> Optional[str]:
    env_url = (os.getenv("GITHUB_URL") or "").strip()
    if env_url:
        return env_url
    repo = payload.get("repository") or {}
    for candidate in (repo.get("html_url"), repo.get("url"), repo.get("clone_url")):
        base = _base_url(candidate or "")
        if base:
            return base
    return None


def resolve_github_token() -> Optional[str]:
    token = os.getenv("GITHUB_ACCESS_TOKEN")
    return token or None


def _resolve_api_base_url(github_url: str) -> str:
    api_override = (os.getenv("GITHUB_API_BASE_URL") or "").strip()
    if api_override:
        return api_override
    base = github_url.rstrip("/") if github_url else "https://github.com"
    if base == "https://github.com":
        return "https://api.github.com"
    return f"{base}/api/v3"


def filter_changes(changes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    supported = [
        ext.strip()
        for ext in os.getenv("SUPPORTED_EXTENSIONS", ".java,.py,.php").split(",")
        if ext.strip()
    ]

    filtered: List[Dict[str, Any]] = []
    for item in changes or []:
        status = (item.get("status") or "").lower()
        if status == "removed":
            continue

        diff = item.get("diff", "") or ""
        if diff:
            header_match = re.match(r"@@ -\d+,\d+ \+0,0 @@", diff)
            if header_match:
                diff_lines = diff.split("\\n")[1:]
                if all(line.startswith("-") or not line for line in diff_lines):
                    continue

        new_path = item.get("new_path", "") or item.get("filename", "") or ""
        if not new_path:
            continue
        if supported and not any(new_path.endswith(ext) for ext in supported):
            continue

        additions = item.get("additions")
        deletions = item.get("deletions")
        if additions is None:
            additions = len(re.findall(r"^\+(?!\+\+)", diff, re.MULTILINE))
        if deletions is None:
            deletions = len(re.findall(r"^-(?!--)", diff, re.MULTILINE))

        filtered.append(
            {
                "diff": diff,
                "new_path": new_path,
                "additions": additions,
                "deletions": deletions,
            }
        )
    return filtered


class GitHubClient:
    def __init__(self, base_url: str, token: str) -> None:
        self.web_base_url = (base_url or "https://github.com").rstrip("/")
        self.api_base_url = _resolve_api_base_url(self.web_base_url)
        self.token = token

    def _headers(self) -> Dict[str, str]:
        headers = {"Accept": "application/vnd.github.v3+json"}
        if self.token:
            headers["Authorization"] = f"token {self.token}"
        return headers

    def _request(self, method: str, path: str, **kwargs: Any):
        url = urljoin(f"{self.api_base_url.rstrip('/')}/", path.lstrip("/"))
        headers = kwargs.pop("headers", {}) or {}
        headers.update(self._headers())
        return request_with_retry(method, url, headers=headers, **kwargs)

    def get_pull_request_changes(self, repo_full_name: str, pr_number: int) -> List[Dict[str, Any]]:
        if not repo_full_name or not pr_number:
            return []
        max_retries = 3
        retry_delay = 10
        path = f"repos/{repo_full_name}/pulls/{pr_number}/files"
        for attempt in range(max_retries):
            resp = self._request("GET", path, retries=1)
            if resp.status_code == 200:
                files = resp.json() or []
                if files:
                    changes = []
                    for file in files:
                        changes.append(
                            {
                                "old_path": file.get("filename"),
                                "new_path": file.get("filename"),
                                "diff": file.get("patch", "") or "",
                                "additions": file.get("additions", 0),
                                "deletions": file.get("deletions", 0),
                                "status": file.get("status", ""),
                            }
                        )
                    return changes
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
            else:
                return []
        return []

    def get_pull_request_commits(self, repo_full_name: str, pr_number: int) -> List[Dict[str, Any]]:
        if not repo_full_name or not pr_number:
            return []
        path = f"repos/{repo_full_name}/pulls/{pr_number}/commits"
        resp = self._request("GET", path)
        if resp.status_code != 200:
            return []
        commits = resp.json() or []
        results: List[Dict[str, Any]] = []
        for commit in commits:
            commit_data = commit.get("commit", {}) or {}
            author_data = commit_data.get("author", {}) or {}
            results.append(
                {
                    "id": commit.get("sha"),
                    "title": (commit_data.get("message") or "").split("\\n")[0],
                    "message": commit_data.get("message") or "",
                    "author_name": author_data.get("name"),
                    "author_email": author_data.get("email"),
                    "created_at": author_data.get("date"),
                    "web_url": commit.get("html_url"),
                }
            )
        return results

    def add_pull_request_notes(self, repo_full_name: str, pr_number: int, review_result: str) -> None:
        if not repo_full_name or not pr_number:
            return
        path = f"repos/{repo_full_name}/issues/{pr_number}/comments"
        resp = self._request("POST", path, json={"body": review_result}, retries=1)
        if resp.status_code != 201:
            logger.error("Failed to add GitHub PR comment: %s", resp.text[:200])

    def target_branch_protected(self, repo_full_name: str, target_branch: str) -> bool:
        if not repo_full_name or not target_branch:
            return False
        path = f"repos/{repo_full_name}/branches?protected=true"
        resp = self._request("GET", path)
        if resp.status_code != 200:
            return False
        data = resp.json() or []
        return any(self._match_branch(target_branch, item.get("name", "")) for item in data)

    @staticmethod
    def _match_branch(branch: str, pattern: str) -> bool:
        if not branch or not pattern:
            return False
        if pattern == branch:
            return True
        if "*" in pattern:
            regex = re.escape(pattern).replace("\\*", ".*")
            return re.fullmatch(regex, branch) is not None
        return False

    def get_parent_commit_id(self, repo_full_name: str, commit_id: str) -> str:
        if not repo_full_name or not commit_id:
            return ""
        path = f"repos/{repo_full_name}/commits/{commit_id}"
        resp = self._request("GET", path)
        if resp.status_code != 200:
            return ""
        parents = (resp.json() or {}).get("parents") or []
        if parents:
            return parents[0].get("sha") or ""
        return ""

    def repository_compare(self, repo_full_name: str, base: str, head: str) -> List[Dict[str, Any]]:
        if not repo_full_name or not base or not head:
            return []
        path = f"repos/{repo_full_name}/compare/{base}...{head}"
        resp = self._request("GET", path)
        if resp.status_code != 200:
            return []
        files = (resp.json() or {}).get("files") or []
        diffs: List[Dict[str, Any]] = []
        for file in files:
            diffs.append(
                {
                    "old_path": file.get("filename"),
                    "new_path": file.get("filename"),
                    "diff": file.get("patch", "") or "",
                    "status": file.get("status", ""),
                    "additions": file.get("additions", 0),
                    "deletions": file.get("deletions", 0),
                }
            )
        return diffs

    def get_push_changes(
        self,
        repo_full_name: str,
        before: str,
        after: str,
        commit_list: List[Dict[str, Any]],
        created: bool = False,
        deleted: bool = False,
    ) -> List[Dict[str, Any]]:
        if not repo_full_name or not after or deleted:
            return []
        if before and after:
            if created and commit_list:
                first_commit = commit_list[0].get("id")
                parent = self.get_parent_commit_id(repo_full_name, first_commit)
                if parent:
                    before = parent
            return self.repository_compare(repo_full_name, before, after)

        changes: List[Dict[str, Any]] = []
        for commit in commit_list or []:
            commit_id = commit.get("id")
            if not commit_id:
                continue
            parent_id = self.get_parent_commit_id(repo_full_name, commit_id)
            if not parent_id:
                continue
            changes.extend(self.repository_compare(repo_full_name, parent_id, commit_id))
        return changes

    @staticmethod
    def get_push_commits_from_payload(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        commits = payload.get("commits") or []
        results: List[Dict[str, Any]] = []
        for commit in commits:
            results.append(
                {
                    "message": commit.get("message"),
                    "author": (commit.get("author") or {}).get("name"),
                    "timestamp": commit.get("timestamp"),
                    "url": commit.get("url"),
                }
            )
        return results

    def add_push_notes(self, repo_full_name: str, commit_id: str, message: str) -> None:
        if not repo_full_name or not commit_id:
            return
        path = f"repos/{repo_full_name}/commits/{commit_id}/comments"
        resp = self._request("POST", path, json={"body": message}, retries=1)
        if resp.status_code != 201:
            logger.error("Failed to add GitHub commit comment: %s", resp.text[:200])
