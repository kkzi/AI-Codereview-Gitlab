from __future__ import annotations

import os
import re
from typing import Any, Dict, Optional, Tuple
from urllib.parse import quote, urlparse

from app.core.logging import get_logger
from app.infra.db.sqlite import SQLiteRepository
from app.infra.queue.db_queue import DbQueue
from app.infra.scm.github import resolve_github_url
from app.infra.scm.gitea import resolve_gitea_url


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


def _strip_base(url: str, base: str) -> str:
    if not url or not base:
        return ""
    if url.startswith(base):
        return url[len(base) :]
    return ""


def _extract_project_path(project_url: str, gitlab_base_url: str) -> str:
    base = _base_url(gitlab_base_url) or _base_url(project_url)
    if not project_url or not base:
        return ""
    path = _strip_base(project_url.rstrip("/"), base.rstrip("/"))
    path = (path or "").strip("/")
    if path.endswith(".git"):
        path = path[: -len(".git")]
    return path


def _extract_project_path_from_mr_url(mr_url: str, gitlab_base_url: str) -> str:
    base = _base_url(gitlab_base_url)
    if not mr_url or not base:
        return ""
    path = _strip_base(mr_url.rstrip("/"), base.rstrip("/")).strip("/")
    if not path:
        return ""
    for marker in ("/-/merge_requests/", "/merge_requests/"):
        idx = path.find(marker)
        if idx != -1:
            return path[:idx].strip("/")
    return ""


def _extract_gitlab_mr_iid(mr_url: str) -> int:
    if not mr_url:
        return 0
    match = re.search(r"/merge_requests/(\d+)", mr_url)
    if not match:
        return 0
    try:
        return int(match.group(1))
    except Exception:
        return 0


def _resolve_gitlab_url(record: Dict[str, Any], payload: Dict[str, Any]) -> str:
    env_url = (os.getenv("GITLAB_URL") or "").strip()
    if env_url:
        return env_url

    for candidate in (
        record.get("project_url"),
        record.get("commit_url"),
        record.get("url"),
    ):
        base = _base_url(candidate or "")
        if base:
            return base

    project = payload.get("project") or {}
    repository = payload.get("repository") or {}
    for candidate in (project.get("web_url"), repository.get("homepage")):
        base = _base_url(candidate or "")
        if base:
            return base

    return ""


class RetryUseCase:
    def __init__(self, repo: SQLiteRepository, queue: DbQueue) -> None:
        self.repo = repo
        self.queue = queue

    def trigger_retry(self, record_id: int, review_type: str) -> Tuple[Dict[str, Any], int]:
        if review_type not in {"mr", "push"}:
            return {"error": "Invalid review_type, must be 'mr' or 'push'"}, 400

        record = self.repo.get_review_by_id("push" if review_type == "push" else "mr", record_id)
        if not record:
            return {"error": "Record not found"}, 404

        event_id = record.get("event_id")
        payload = None
        source = ""
        if event_id:
            event = self.repo.get_event_by_id(int(event_id)) or {}
            payload = event.get("payload")
            if not isinstance(payload, dict):
                payload = None
            source = (event.get("source") or "").strip()

        if payload and source in {"github", "gitea"}:
            if source == "github":
                token = os.getenv("GITHUB_ACCESS_TOKEN", "")
                if not token:
                    return {"error": "Missing GitHub access token"}, 400
                base_url = resolve_github_url(payload)
                if not base_url:
                    return {"error": "Missing GitHub URL"}, 400
                job_id = self.queue.enqueue_github_event(
                    payload=payload,
                    token=token,
                    url=base_url,
                    event_id=event_id,
                    record_id=record_id,
                )
            else:
                token = os.getenv("GITEA_ACCESS_TOKEN", "")
                if not token:
                    return {"error": "Missing Gitea access token"}, 400
                base_url = resolve_gitea_url(payload)
                if not base_url:
                    return {"error": "Missing Gitea URL"}, 400
                job_id = self.queue.enqueue_gitea_event(
                    payload=payload,
                    token=token,
                    url=base_url,
                    event_id=event_id,
                    record_id=record_id,
                )

            logger.info("Retry enqueued: record_id=%s job_id=%s", record_id, job_id)
            return {
                "message": f"Retry review triggered for record_id={record_id}",
                "job_id": job_id,
            }, 200

        if not payload:
            payload = self._build_payload_from_record(record, review_type)

        if not payload:
            return {"error": "Unable to rebuild payload for retry"}, 400

        gitlab_token = os.getenv("GITLAB_ACCESS_TOKEN", "")
        if not gitlab_token:
            return {"error": "Missing GitLab access token"}, 400

        gitlab_url = _resolve_gitlab_url(record, payload)
        if not gitlab_url:
            return {"error": "Missing GitLab URL"}, 400

        job_id = self.queue.enqueue_gitlab_event(
            payload=payload,
            token=gitlab_token,
            url=gitlab_url,
            event_id=event_id,
            record_id=record_id,
        )

        logger.info("Retry enqueued: record_id=%s job_id=%s", record_id, job_id)
        return {
            "message": f"Retry review triggered for record_id={record_id}",
            "job_id": job_id,
        }, 200

    def _build_payload_from_record(
        self, record: Dict[str, Any], review_type: str
    ) -> Optional[Dict[str, Any]]:
        project_url = (record.get("project_url") or "").strip()
        gitlab_base_url = (os.getenv("GITLAB_URL") or "").strip()
        base_url = (
            _base_url(gitlab_base_url)
            or _base_url(project_url)
            or _base_url(record.get("url") or "")
            or _base_url(record.get("commit_url") or "")
        )

        project_path = _extract_project_path(project_url, base_url)
        if not project_path and review_type == "mr":
            project_path = _extract_project_path_from_mr_url(record.get("url") or "", base_url)

        if not project_path:
            return None

        project_id = quote(project_path, safe="")

        if review_type == "mr":
            mr_url = (record.get("url") or "").strip()
            mr_iid = _extract_gitlab_mr_iid(mr_url)
            if not mr_iid:
                return None

            author = (record.get("author") or "").strip()
            display_name = (record.get("author_display_name") or "").strip()
            source_branch = record.get("source_branch") or ""
            target_branch = record.get("target_branch") or ""
            last_commit_id = record.get("last_commit_id") or ""

            return {
                "object_kind": "merge_request",
                "project": {
                    "name": record.get("project_name") or "",
                    "id": project_id,
                    "web_url": project_url,
                },
                "user": {"username": author, "name": display_name},
                "object_attributes": {
                    "iid": mr_iid,
                    "target_project_id": project_id,
                    "source_branch": source_branch,
                    "target_branch": target_branch,
                    "url": mr_url,
                    "last_commit": {"id": last_commit_id},
                },
                "repository": {"homepage": project_url},
            }

        branch = record.get("branch") or ""
        commit_id = (record.get("last_commit_id") or "").strip()
        raw_commit = (record.get("commit_messages") or "").strip()
        commit_message = raw_commit.split(";", 1)[0].strip() if raw_commit else "retry"
        author_name = (record.get("author_display_name") or "").strip() or (
            record.get("author") or ""
        ).strip()

        commits = []
        if commit_id:
            commits.append(
                {
                    "id": commit_id,
                    "message": commit_message,
                    "author": {"name": author_name},
                    "timestamp": "",
                    "url": record.get("commit_url") or "",
                }
            )

        return {
            "object_kind": "push",
            "event_name": "push",
            "ref": f"refs/heads/{branch}",
            "before": "0000000",
            "after": commit_id,
            "project": {
                "name": record.get("project_name") or "",
                "id": project_id,
                "web_url": project_url,
            },
            "project_id": project_id,
            "user_username": record.get("author") or "",
            "user_name": record.get("author_display_name") or "",
            "commits": commits,
            "repository": {"homepage": project_url},
        }
