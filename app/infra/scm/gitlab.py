from __future__ import annotations

import os
import re
import time
from typing import Any, Dict, List, Optional
import fnmatch
from urllib.parse import urlparse, urljoin

import requests

from app.core.logging import get_logger


logger = get_logger(__name__)


def slugify_url(original_url: str) -> str:
    original_url = re.sub(r"^https?://", "", original_url)
    target = re.sub(r"[^a-zA-Z0-9]", "_", original_url)
    return target.rstrip("_")


def resolve_gitlab_url(payload: Dict[str, Any], headers: Dict[str, str]) -> Optional[str]:
    gitlab_url = os.getenv("GITLAB_URL") or headers.get("X-Gitlab-Instance")
    if gitlab_url:
        return gitlab_url

    repository = payload.get("repository") or {}
    homepage = repository.get("homepage")
    if not homepage:
        return None
    try:
        parsed = urlparse(homepage)
        return f"{parsed.scheme}://{parsed.netloc}/"
    except Exception:
        return None


def resolve_gitlab_token(headers: Dict[str, str]) -> Optional[str]:
    return os.getenv("GITLAB_ACCESS_TOKEN") or headers.get("X-Gitlab-Token")


def _get_timeout() -> float:
    try:
        return float(os.getenv("HTTP_TIMEOUT", "15"))
    except Exception:
        return 15.0


def _get_retries() -> int:
    try:
        return int(os.getenv("HTTP_RETRY_COUNT", "2"))
    except Exception:
        return 2


def _get_backoff() -> float:
    try:
        return float(os.getenv("HTTP_RETRY_BACKOFF", "1"))
    except Exception:
        return 1.0


def request_with_retry(
    method: str,
    url: str,
    *,
    timeout: float | None = None,
    retries: int | None = None,
    backoff: float | None = None,
    **kwargs: Any,
) -> requests.Response:
    timeout = _get_timeout() if timeout is None else timeout
    retries = _get_retries() if retries is None else retries
    backoff = _get_backoff() if backoff is None else backoff

    last_error: Exception | None = None
    for attempt in range(max(retries, 1)):
        try:
            return requests.request(method, url, timeout=timeout, **kwargs)
        except requests.exceptions.RequestException as exc:
            last_error = exc
            if attempt < retries - 1:
                sleep_time = backoff * (2**attempt) if backoff else 0
                if sleep_time > 0:
                    time.sleep(sleep_time)
            else:
                break

    if last_error:
        raise last_error
    raise RuntimeError("HTTP request failed without exception")


def filter_changes(changes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """过滤变更，只保留支持的文件类型并计算增删行。"""
    supported = os.getenv("SUPPORTED_EXTENSIONS", ".java,.py,.php").split(",")
    filtered: List[Dict[str, Any]] = []
    for item in changes or []:
        if item.get("deleted_file"):
            continue
        new_path = item.get("new_path", "")
        if not any(new_path.endswith(ext) for ext in supported):
            continue
        diff = item.get("diff", "") or ""
        filtered.append(
            {
                "diff": diff,
                "new_path": new_path,
                "additions": len(
                    re.findall(r"^\+(?!\+\+)", diff, re.MULTILINE)
                ),
                "deletions": len(
                    re.findall(r"^-(?!--)", diff, re.MULTILINE)
                ),
            }
        )
    return filtered


def extract_project_id(payload: Dict[str, Any]) -> Optional[int]:
    project_id = payload.get("project_id") or (payload.get("project") or {}).get("id")
    if project_id:
        return project_id
    object_attrs = payload.get("object_attributes") or {}
    return object_attrs.get("target_project_id")


def extract_mr_iid(payload: Dict[str, Any]) -> Optional[int]:
    object_attrs = payload.get("object_attributes") or {}
    return object_attrs.get("iid")


class GitLabClient:
    def __init__(self, base_url: str, token: str) -> None:
        self.base_url = base_url
        self.token = token

    def _headers(self) -> Dict[str, str]:
        return {"Private-Token": self.token}

    def _request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        url = urljoin(f"{self.base_url.rstrip('/')}/", path.lstrip("/"))
        headers = kwargs.pop("headers", {}) or {}
        headers.update(self._headers())
        return request_with_retry(method, url, headers=headers, verify=False, **kwargs)

    def get_merge_request_changes(self, project_id: int, mr_iid: int) -> List[Dict[str, Any]]:
        retries = 3
        delay = 10
        for attempt in range(retries):
            resp = self._request(
                "GET",
                f"api/v4/projects/{project_id}/merge_requests/{mr_iid}/changes?access_raw_diffs=true",
                retries=1,
            )
            if resp.status_code != 200:
                return []
            changes = resp.json().get("changes", [])
            if changes:
                return changes
            if attempt < retries - 1:
                time.sleep(delay)
        return []

    def get_merge_request_commits(self, project_id: int, mr_iid: int) -> List[Dict[str, Any]]:
        resp = self._request(
            "GET",
            f"api/v4/projects/{project_id}/merge_requests/{mr_iid}/commits",
        )
        if resp.status_code == 200:
            return resp.json()
        return []

    def add_merge_request_notes(self, project_id: int, mr_iid: int, review_result: str) -> None:
        resp = self._request(
            "POST",
            f"api/v4/projects/{project_id}/merge_requests/{mr_iid}/notes",
            json={"body": review_result},
            retries=1,
        )
        if resp.status_code != 201:
            logger.error("Failed to add GitLab MR note: %s", resp.text[:200])

    def target_branch_protected(self, project_id: int, target_branch: str) -> bool:
        if not project_id or not target_branch:
            return False
        resp = self._request(
            "GET",
            f"api/v4/projects/{project_id}/protected_branches",
        )
        if resp.status_code != 200:
            return False
        data = resp.json() or []
        return any(fnmatch.fnmatch(target_branch, item.get("name", "")) for item in data)

    def repository_compare(self, project_id: int, before: str, after: str) -> List[Dict[str, Any]]:
        resp = self._request(
            "GET",
            f"api/v4/projects/{project_id}/repository/compare?from={before}&to={after}",
        )
        if resp.status_code == 200:
            return resp.json().get("diffs", [])
        return []

    def get_commit_diff(self, project_id: int, commit_sha: str) -> List[Dict[str, Any]]:
        resp = self._request(
            "GET",
            f"api/v4/projects/{project_id}/repository/commits/{commit_sha}/diff",
        )
        if resp.status_code == 200:
            return resp.json()
        return []

    def get_push_changes(
        self,
        project_id: int,
        before: str,
        after: str,
        commit_list: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        if not before or not after:
            return []
        if after.startswith("0000000"):
            return []
        if before.startswith("0000000"):
            if commit_list:
                return self.get_commit_diff(project_id, after)
            return []
        return self.repository_compare(project_id, before, after)

    def add_push_notes(self, project_id: int, commit_id: str, message: str) -> None:
        if not project_id or not commit_id:
            return
        resp = self._request(
            "POST",
            f"api/v4/projects/{project_id}/repository/commits/{commit_id}/comments",
            json={"note": message},
            retries=1,
        )
        if resp.status_code != 201:
            logger.error("Failed to add GitLab commit comment: %s", resp.text[:200])

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
