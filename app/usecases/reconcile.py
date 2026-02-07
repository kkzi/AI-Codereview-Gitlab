from __future__ import annotations

import os
import time
from typing import Any, Dict
from urllib.parse import urlparse

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


def _resolve_gitlab_url(event: Dict[str, Any], payload: Dict[str, Any]) -> str:
    env_url = (os.getenv("GITLAB_URL") or "").strip()
    if env_url:
        return env_url

    for candidate in (
        event.get("project_url"),
        (payload.get("project") or {}).get("web_url"),
        (payload.get("repository") or {}).get("homepage"),
    ):
        base = _base_url(candidate or "")
        if base:
            return base
    return ""


def _get_bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def requeue_unreviewed_events(
    repo: SQLiteRepository,
    queue: DbQueue,
    *,
    days: int = 7,
) -> int:
    if not _get_bool_env("RECONCILE_ON_STARTUP", True):
        return 0

    cutoff = int(time.time()) - max(days, 0) * 24 * 3600
    events = repo.get_unreviewed_events_since(cutoff)
    enqueued = 0

    for event in events:
        event_id = int(event.get("id") or 0)
        if not event_id:
            continue
        if queue.has_active_event(event_id):
            continue

        payload = event.get("payload")
        if not isinstance(payload, dict):
            logger.warning("跳过无效 payload 的事件: event_id=%s", event_id)
            continue

        source = (event.get("source") or "").strip().lower() or "gitlab"
        if _is_draft_event(source, payload):
            continue

        if source == "github":
            base_url = resolve_github_url(payload)
            if not base_url:
                logger.warning("缺少 GitHub URL，跳过事件: event_id=%s", event_id)
                continue
            queue.enqueue_github_event(
                payload=payload,
                url=base_url,
                event_id=event_id,
            )
            enqueued += 1
            continue

        if source == "gitea":
            base_url = resolve_gitea_url(payload)
            if not base_url:
                logger.warning("缺少 Gitea URL，跳过事件: event_id=%s", event_id)
                continue
            queue.enqueue_gitea_event(
                payload=payload,
                url=base_url,
                event_id=event_id,
            )
            enqueued += 1
            continue

        base_url = _resolve_gitlab_url(event, payload)
        if not base_url:
            logger.warning("缺少 GitLab URL，跳过事件: event_id=%s", event_id)
            continue
        queue.enqueue_gitlab_event(
            payload=payload,
            url=base_url,
            event_id=event_id,
        )
        enqueued += 1

    if events:
        logger.info(
            "启动对账完成: 扫描=%s 入列=%s",
            len(events),
            enqueued,
        )
    return enqueued


def _is_draft_event(source: str, payload: Dict[str, Any]) -> bool:
    if source == "gitlab":
        object_attrs = payload.get("object_attributes") or {}
        return bool(object_attrs.get("draft") or object_attrs.get("work_in_progress"))
    if source in {"github", "gitea"}:
        pull_request = payload.get("pull_request") or {}
        return bool(pull_request.get("draft"))
    return False
