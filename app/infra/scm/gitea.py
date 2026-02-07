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


def resolve_gitea_url(payload: Dict[str, Any]) -> Optional[str]:
    env_url = (os.getenv("GITEA_URL") or "").strip()
    if env_url:
        return env_url
    repo = payload.get("repository") or {}
    for candidate in (repo.get("html_url"), repo.get("clone_url"), repo.get("url")):
        base = _base_url(candidate or "")
        if base:
            return base
    return None


def resolve_gitea_token() -> Optional[str]:
    token = os.getenv("GITEA_ACCESS_TOKEN")
    return token or None


def filter_changes(changes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    supported = [
        ext.strip()
        for ext in os.getenv("SUPPORTED_EXTENSIONS", ".java,.py,.php").split(",")
        if ext.strip()
    ]

    filtered: List[Dict[str, Any]] = []
    for item in changes or []:
        status = (item.get("status") or "").lower()
        if status in {"removed", "deleted"}:
            continue

        new_path = item.get("new_path") or item.get("filename") or item.get("path") or ""
        if not new_path:
            continue
        if supported and not any(new_path.endswith(ext) for ext in supported):
            continue

        diff_text = item.get("diff") or item.get("patch") or ""
        additions = item.get("additions")
        deletions = item.get("deletions")
        if additions is None:
            additions = len(re.findall(r"^\+(?!\+\+)", diff_text, re.MULTILINE))
        if deletions is None:
            deletions = len(re.findall(r"^-(?!--)", diff_text, re.MULTILINE))

        filtered.append(
            {
                "diff": diff_text,
                "new_path": new_path,
                "additions": additions,
                "deletions": deletions,
            }
        )
    return filtered


class GiteaClient:
    def __init__(self, base_url: str, token: str) -> None:
        self.base_url = (base_url or "").rstrip("/")
        self.token = token

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"token {self.token}"
        return headers

    def _request(self, method: str, path: str, **kwargs: Any):
        url = urljoin(f"{self.base_url.rstrip('/')}/", path.lstrip("/"))
        headers = kwargs.pop("headers", {}) or {}
        headers.update(self._headers())
        return request_with_retry(method, url, headers=headers, verify=False, **kwargs)

    def get_pull_request_changes(self, repo_full_name: str, pr_index: int) -> List[Dict[str, Any]]:
        if not repo_full_name or not pr_index:
            return []
        max_retries = 3
        retry_delay = 10
        path = f"api/v1/repos/{repo_full_name}/pulls/{pr_index}/files"
        for attempt in range(max_retries):
            resp = self._request("GET", path, retries=1)
            if resp.status_code == 200:
                files = resp.json() or []
                if files:
                    changes = []
                    for file in files:
                        changes.append(
                            {
                                "diff": file.get("patch") or file.get("diff") or "",
                                "new_path": file.get("filename") or file.get("path") or "",
                                "status": file.get("status", ""),
                                "additions": file.get("additions"),
                                "deletions": file.get("deletions"),
                            }
                        )
                    return changes
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
            else:
                logger.warning(
                    "Gitea PR files request failed: status=%s url=%s body=%s",
                    resp.status_code,
                    resp.url,
                    resp.text[:200],
                )
                return []
        return []

    def get_pull_request_commits(self, repo_full_name: str, pr_index: int) -> List[Dict[str, Any]]:
        if not repo_full_name or not pr_index:
            return []
        path = f"api/v1/repos/{repo_full_name}/pulls/{pr_index}/commits"
        resp = self._request("GET", path)
        if resp.status_code != 200:
            logger.warning(
                "Gitea PR commits request failed: status=%s url=%s body=%s",
                resp.status_code,
                resp.url,
                resp.text[:200],
            )
            return []
        commits = resp.json() or []
        results: List[Dict[str, Any]] = []
        for commit in commits:
            commit_data = commit.get("commit", {}) or {}
            author_data = commit_data.get("author", {}) or {}
            results.append(
                {
                    "id": commit.get("sha") or commit.get("id"),
                    "title": (commit_data.get("message") or "").split("\\n")[0],
                    "message": commit_data.get("message") or "",
                    "author_name": author_data.get("name"),
                    "author_email": author_data.get("email"),
                    "created_at": author_data.get("date") or commit.get("created_at"),
                    "web_url": commit.get("html_url") or commit.get("url"),
                }
            )
        return results

    def add_pull_request_notes(self, repo_full_name: str, pr_index: int, review_result: str) -> None:
        if not repo_full_name or not pr_index:
            return
        path = f"api/v1/repos/{repo_full_name}/issues/{pr_index}/comments"
        resp = self._request("POST", path, json={"body": review_result}, retries=1)
        if resp.status_code != 201:
            logger.error("Failed to add Gitea PR comment: %s", resp.text[:200])

    def target_branch_protected(self, repo_full_name: str, target_branch: str) -> bool:
        if not repo_full_name or not target_branch:
            return False
        path = f"api/v1/repos/{repo_full_name}/branches?protected=true"
        resp = self._request("GET", path)
        if resp.status_code != 200:
            logger.warning(
                "Gitea protected branches request failed: status=%s url=%s body=%s",
                resp.status_code,
                resp.url,
                resp.text[:200],
            )
            return False
        branches = resp.json() or []
        return any(self._match_branch(target_branch, branch.get("name", "")) for branch in branches)

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

    def _get_commit_diff(self, repo_full_name: str, commit_id: str) -> str:
        if not repo_full_name or not commit_id:
            return ""
        path = f"api/v1/repos/{repo_full_name}/git/commits/{commit_id}.diff"
        resp = self._request("GET", path)
        if resp.status_code == 200:
            return resp.text or ""
        logger.warning(
            "Gitea commit diff request failed: status=%s url=%s body=%s",
            resp.status_code,
            resp.url,
            resp.text[:200],
        )
        return ""

    @staticmethod
    def _parse_diff_to_changes(diff_text: str) -> List[Dict[str, Any]]:
        if not diff_text:
            return []

        changes: List[Dict[str, Any]] = []
        current = None
        additions = deletions = 0
        lines_buffer: List[str] = []
        new_path = ""
        status = ""

        def finalize():
            if current is None:
                return
            diff_str = "\\n".join(lines_buffer)
            changes.append(
                {
                    "diff": diff_str,
                    "new_path": new_path,
                    "status": status,
                    "additions": additions,
                    "deletions": deletions,
                }
            )

        for line in diff_text.splitlines():
            if line.startswith("diff --git"):
                if current is not None:
                    finalize()
                current = True
                additions = deletions = 0
                lines_buffer = [line]
                new_path = ""
                status = ""
                continue

            if current is None:
                continue

            lines_buffer.append(line)

            if line.startswith("new file mode"):
                status = "added"
            elif line.startswith("deleted file mode"):
                status = "removed"
            elif line.startswith("+++ "):
                path = line[4:]
                if path.startswith("b/"):
                    path = path[2:]
                if path == "/dev/null":
                    path = ""
                new_path = path
            elif line.startswith("--- "):
                if status != "removed" and line.endswith("/dev/null"):
                    status = "removed"
            elif line.startswith("+") and not line.startswith("+++"):
                additions += 1
            elif line.startswith("-") and not line.startswith("---"):
                deletions += 1

        if current is not None:
            finalize()

        return [change for change in changes if change.get("new_path")]

    def get_push_changes(self, repo_full_name: str, commit_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not repo_full_name:
            return []
        changes: List[Dict[str, Any]] = []
        for commit in commit_list or []:
            commit_id = commit.get("id")
            if not commit_id:
                continue
            diff_text = self._get_commit_diff(repo_full_name, commit_id)
            changes.extend(self._parse_diff_to_changes(diff_text))
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
                    "id": commit.get("id"),
                }
            )
        return results

    def add_push_notes(self, *_: Any, **__: Any) -> None:
        return
