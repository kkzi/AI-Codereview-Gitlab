"""Retry review trigger logic.

This module centralizes the retry implementation so multiple HTTP endpoints can
reuse it without duplicating request parsing.
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, Tuple
from urllib.parse import quote, urlparse

import requests

from biz.service.review_service import ReviewService
from biz.platforms.gitlab.webhook_handler import slugify_url
from biz.utils.log import logger
from biz.utils.http import request_with_retry
from biz.queue.worker import (
    handle_merge_request_event,
    handle_push_event,
    handle_github_pull_request_event,
    handle_github_push_event,
    handle_gitea_pull_request_event,
    handle_gitea_push_event,
)
from biz.service.event_service import EventService
from biz.utils.queue import handle_queue


def _base_url(url: str) -> str:
    if not url:
        return ""
    try:
        u = urlparse(url)
        if not u.scheme or not u.netloc:
            return ""
        return f"{u.scheme}://{u.netloc}"
    except Exception:
        return ""


def _strip_base(url: str, base: str) -> str:
    if not url or not base:
        return ""
    try:
        if url.startswith(base):
            return url[len(base) :]
    except Exception:
        pass
    return ""


def _extract_project_path(project_url: str, gitlab_base_url: str) -> str:
    """Extract GitLab project path from its web URL.

    Example:
      project_url=https://git.example.com/group/proj -> group/proj
    """

    base = _base_url(gitlab_base_url) or _base_url(project_url)
    if not project_url or not base:
        return ""

    path = _strip_base(project_url.rstrip("/"), base.rstrip("/"))
    path = (path or "").strip("/")
    if not path:
        return ""
    if path.endswith(".git"):
        path = path[: -len(".git")]
    return path


def _extract_gitlab_mr_iid(mr_url: str) -> int:
    if not mr_url:
        return 0
    m = re.search(r"/merge_requests/(\d+)", mr_url)
    if not m:
        return 0
    try:
        return int(m.group(1))
    except Exception:
        return 0


def _gitlab_get_json(base_url: str, token: str, path: str) -> Any:
    url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
    headers = {"Private-Token": token} if token else {}
    resp = request_with_retry("GET", url, headers=headers, verify=False)
    if resp.status_code != 200:
        raise RuntimeError(f"GitLab API error {resp.status_code}: {resp.text[:200]}")
    return resp.json()


def _resolve_gitlab_project_id(base_url: str, token: str, project_path: str) -> int:
    if not base_url or not project_path:
        return 0
    # GitLab allows url-encoded full path as :id.
    data = _gitlab_get_json(
        base_url, token, f"api/v4/projects/{quote(project_path, safe='')}"
    )
    try:
        return int(data.get("id") or 0)
    except Exception:
        return 0


def _resolve_gitlab_commit_parent(
    base_url: str, token: str, project_id: Any, sha: str
) -> str:
    if not base_url or not project_id or not sha:
        return ""
    data = _gitlab_get_json(
        base_url, token, f"api/v4/projects/{project_id}/repository/commits/{quote(sha)}"
    )
    parents = data.get("parent_ids") or []
    if parents and isinstance(parents, list):
        return str(parents[0] or "")
    return ""


def trigger_retry(record_id: int, review_type: str) -> Tuple[Dict[str, Any], int]:
    """Trigger an asynchronous retry for a MR or push record.

    Returns: (payload, http_status)
    """

    if review_type == "mr":
        record = ReviewService().get_mr_review_log_by_id(record_id)
        if not record:
            return {"error": "Record not found"}, 404

        event_id = record.get("event_id")
        if event_id:
            event = EventService.get_event_record(event_id) or {}
            payload = event.get("payload") if event else None
            if payload:
                source = event.get("source")
                if source == "github":
                    github_token = os.getenv("GITHUB_ACCESS_TOKEN", "")
                    github_url = os.getenv("GITHUB_URL") or "https://github.com"
                    if not github_token:
                        return {"error": "Missing GitHub access token"}, 400
                    github_url_slug = slugify_url(github_url)
                    handle_queue(
                        handle_github_pull_request_event,
                        payload,
                        github_token,
                        github_url,
                        github_url_slug,
                        record_id=record_id,
                        event_id=event_id,
                    )
                elif source == "gitea":
                    gitea_token = os.getenv("GITEA_ACCESS_TOKEN", "")
                    gitea_url = os.getenv("GITEA_URL") or "https://gitea.com"
                    if not gitea_token:
                        return {"error": "Missing Gitea access token"}, 400
                    gitea_url_slug = slugify_url(gitea_url)
                    handle_queue(
                        handle_gitea_pull_request_event,
                        payload,
                        gitea_token,
                        gitea_url,
                        gitea_url_slug,
                        record_id=record_id,
                        event_id=event_id,
                    )
                else:
                    gitlab_token = os.getenv("GITLAB_ACCESS_TOKEN", "")
                    gitlab_url = os.getenv("GITLAB_URL", "https://gitlab.com")
                    gitlab_url_slug = slugify_url(gitlab_url)
                    handle_queue(
                        handle_merge_request_event,
                        payload,
                        gitlab_token,
                        gitlab_url,
                        gitlab_url_slug,
                        record_id=record_id,
                        event_id=event_id,
                    )
                return {
                    "message": f"Retry review triggered for record_id={record_id}"
                }, 200

        logger.info(
            f"Retrying MR review for record_id={record_id}, project={record['project_name']}"
        )

        gitlab_token = os.getenv("GITLAB_ACCESS_TOKEN", "")
        gitlab_url = os.getenv("GITLAB_URL", "https://gitlab.com")

        project_url = (record.get("project_url") or "").strip()
        project_path = _extract_project_path(project_url, gitlab_url)
        project_id: Any = ""
        mr_iid = _extract_gitlab_mr_iid(record.get("url") or "")

        if gitlab_token and project_path:
            try:
                project_id = _resolve_gitlab_project_id(
                    _base_url(gitlab_url) or _base_url(project_url),
                    gitlab_token,
                    project_path,
                )
            except Exception:
                logger.exception("Failed to resolve GitLab project id for retry")

        if not project_id and project_path:
            project_id = quote(project_path, safe="")

        webhook_data = {
            "object_kind": "merge_request",
            "project": {"name": record["project_name"], "id": project_id},
            "user": {"username": record.get("author_username") or record["author"]},
            "object_attributes": {
                "iid": mr_iid,
                "target_project_id": project_id,
                "source_branch": record["source_branch"],
                "target_branch": record["target_branch"],
                "url": record["url"],
                "last_commit": {"id": record.get("last_commit_id", "")},
            },
            "repository": {"homepage": project_url},
        }
        gitlab_url_slug = slugify_url(gitlab_url)
        handle_queue(
            handle_merge_request_event,
            webhook_data,
            gitlab_token,
            gitlab_url,
            gitlab_url_slug,
            record_id=record_id,
        )
        return {"message": f"Retry review triggered for record_id={record_id}"}, 200

    if review_type == "push":
        record = ReviewService().get_push_review_log_by_id(record_id)
        if not record:
            return {"error": "Record not found"}, 404

        event_id = record.get("event_id")
        if event_id:
            event = EventService.get_event_record(event_id) or {}
            payload = event.get("payload") if event else None
            if payload:
                source = event.get("source")
                if source == "github":
                    github_token = os.getenv("GITHUB_ACCESS_TOKEN", "")
                    github_url = os.getenv("GITHUB_URL") or "https://github.com"
                    if not github_token:
                        return {"error": "Missing GitHub access token"}, 400
                    github_url_slug = slugify_url(github_url)
                    handle_queue(
                        handle_github_push_event,
                        payload,
                        github_token,
                        github_url,
                        github_url_slug,
                        record_id=record_id,
                        event_id=event_id,
                    )
                elif source == "gitea":
                    gitea_token = os.getenv("GITEA_ACCESS_TOKEN", "")
                    gitea_url = os.getenv("GITEA_URL") or "https://gitea.com"
                    if not gitea_token:
                        return {"error": "Missing Gitea access token"}, 400
                    gitea_url_slug = slugify_url(gitea_url)
                    handle_queue(
                        handle_gitea_push_event,
                        payload,
                        gitea_token,
                        gitea_url,
                        gitea_url_slug,
                        record_id=record_id,
                        event_id=event_id,
                    )
                else:
                    gitlab_token = os.getenv("GITLAB_ACCESS_TOKEN", "")
                    gitlab_url = os.getenv("GITLAB_URL", "https://gitlab.com")
                    gitlab_url_slug = slugify_url(gitlab_url)
                    handle_queue(
                        handle_push_event,
                        payload,
                        gitlab_token,
                        gitlab_url,
                        gitlab_url_slug,
                        record_id=record_id,
                        event_id=event_id,
                    )
                return {
                    "message": f"Retry review triggered for record_id={record_id}"
                }, 200

        logger.info(
            f"Retrying Push review for record_id={record_id}, project={record['project_name']}"
        )

        gitlab_token = os.getenv("GITLAB_ACCESS_TOKEN", "")
        gitlab_url = os.getenv("GITLAB_URL", "https://gitlab.com")

        project_url = (record.get("project_url") or "").strip()
        commit_id = (record.get("last_commit_id") or "").strip()
        project_path = _extract_project_path(project_url, gitlab_url)
        base_url = _base_url(gitlab_url) or _base_url(project_url)

        project_id: Any = ""
        before = ""
        if gitlab_token and base_url and project_path:
            try:
                project_id = _resolve_gitlab_project_id(
                    base_url, gitlab_token, project_path
                )
                before = _resolve_gitlab_commit_parent(
                    base_url, gitlab_token, project_id, commit_id
                )
            except Exception:
                logger.exception("Failed to resolve GitLab push retry context")

        if not project_id and project_path:
            project_id = quote(project_path, safe="")

        if not before:
            before = "0000000"

        raw_commit_message = (record.get("commit_messages") or "").strip()
        commit_message = (
            raw_commit_message.split(";", 1)[0] if raw_commit_message else "retry"
        ).strip()
        author_name = (record.get("author_display_name") or "").strip() or (
            record.get("author_username") or ""
        ).strip()

        webhook_data = {
            "event_name": "push",
            "ref": f"refs/heads/{record['branch']}",
            "before": before,
            "after": commit_id,
            "project": {"name": record["project_name"], "id": project_id},
            "project_id": project_id,
            "user_username": record.get("author_username") or record["author"],
            "user_name": record.get("author_display_name") or "",
            "commits": [
                {
                    "id": commit_id,
                    "message": commit_message,
                    "author": {"name": author_name},
                    "timestamp": "",
                    "url": record.get("commit_url") or "",
                }
            ]
            if commit_id
            else [],
            "repository": {"homepage": project_url},
        }
        gitlab_url_slug = slugify_url(gitlab_url)
        handle_queue(
            handle_push_event,
            webhook_data,
            gitlab_token,
            gitlab_url,
            gitlab_url_slug,
            record_id=record_id,
        )
        return {"message": f"Retry review triggered for record_id={record_id}"}, 200

    return {"error": "Invalid review_type, must be 'mr' or 'push'"}, 400
