"""重构后的ReviewUseCase - 使用策略模式消除代码重复"""
from __future__ import annotations

import time
from typing import Any, Dict, Tuple

from app.core.config import AppConfig
from app.core.logging import get_logger
from app.infra.db.sqlite import SQLiteRepository
from app.infra.scm.gitlab import resolve_gitlab_token, resolve_gitlab_url
from app.infra.scm.github import resolve_github_token, resolve_github_url
from app.infra.scm.gitea import resolve_gitea_token, resolve_gitea_url
from app.usecases.gitlab_handler import GitLabHandler
from app.usecases.github_handler import GitHubHandler
from app.usecases.gitea_handler import GiteaHandler
from app.usecases.review_orchestrator import ReviewOrchestrator

logger = get_logger(__name__)


class ReviewUseCase:
    """代码审查用例 - 重构后使用策略模式"""

    def __init__(self, repo: SQLiteRepository, queue: object, config: AppConfig) -> None:
        self.repo = repo
        self.queue = queue
        self.config = config

    def handle_webhook(
        self, payload: Dict[str, Any], headers: Dict[str, str]
    ) -> Tuple[Dict[str, Any], int]:
        """处理webhook请求 - 路由到对应平台"""
        if headers.get("X-GitHub-Event"):
            return self._handle_github(payload, headers)
        if headers.get("X-Gitea-Event"):
            return self._handle_gitea(payload, headers)
        return self._handle_gitlab(payload, headers)

    def _handle_gitlab(
        self, payload: Dict[str, Any], headers: Dict[str, str]
    ) -> Tuple[Dict[str, Any], int]:
        """处理GitLab webhook"""
        object_kind = payload.get("object_kind")
        if object_kind not in {"merge_request", "push"}:
            return {
                "error": "Only merge_request and push events are supported",
                "event_type": object_kind,
            }, 400
        if object_kind == "merge_request":
            object_attrs = payload.get("object_attributes") or {}
            if object_attrs.get("draft") or object_attrs.get("work_in_progress"):
                return {"message": "Draft MR ignored"}, 200

        gitlab_url = resolve_gitlab_url(payload, headers)
        gitlab_token = resolve_gitlab_token(headers)
        if not gitlab_url:
            return {"error": "Missing GitLab URL"}, 400
        if not gitlab_token:
            return {"error": "Missing GitLab access token"}, 400

        event_id = self.repo.insert_event(
            review_type="mr" if object_kind == "merge_request" else "push",
            source="gitlab",
            event_type=object_kind,
            project_name=(payload.get("project") or {}).get("name", ""),
            project_url=(payload.get("project") or {}).get("web_url", ""),
            created_at=int(time.time()),
            payload=payload,
        )

        self.queue.enqueue_gitlab_event(
            payload=payload,
            url=gitlab_url,
            event_id=event_id,
        )

        return {
            "message": "Request received, processing asynchronously",
            "event_id": event_id,
        }, 200

    def _handle_github(
        self, payload: Dict[str, Any], headers: Dict[str, str]
    ) -> Tuple[Dict[str, Any], int]:
        """处理GitHub webhook"""
        event_type = headers.get("X-GitHub-Event")
        if event_type not in {"pull_request", "push"}:
            return {"error": "Only pull_request and push events are supported"}, 400
        if event_type == "pull_request":
            pull_request = payload.get("pull_request") or {}
            if pull_request.get("draft"):
                return {"message": "Draft PR ignored"}, 200

        github_url = resolve_github_url(payload)
        github_token = resolve_github_token() or headers.get("X-GitHub-Token")
        if not github_url:
            return {"error": "Missing GitHub URL"}, 400
        if not github_token:
            return {"error": "Missing GitHub access token"}, 400

        repo = payload.get("repository") or {}
        event_id = self.repo.insert_event(
            review_type="mr" if event_type == "pull_request" else "push",
            source="github",
            event_type=event_type,
            project_name=repo.get("name", ""),
            project_url=repo.get("html_url", ""),
            created_at=int(time.time()),
            payload=payload,
        )

        self.queue.enqueue_github_event(
            payload=payload,
            url=github_url,
            event_id=event_id,
        )

        return {"message": "Request received, processing asynchronously", "event_id": event_id}, 200

    def _handle_gitea(
        self, payload: Dict[str, Any], headers: Dict[str, str]
    ) -> Tuple[Dict[str, Any], int]:
        """处理Gitea webhook"""
        event_type = headers.get("X-Gitea-Event")
        if event_type not in {"pull_request", "push"}:
            return {"error": "Only pull_request and push events are supported"}, 400
        if event_type == "pull_request":
            pull_request = payload.get("pull_request") or {}
            if pull_request.get("draft"):
                return {"message": "Draft PR ignored"}, 200

        gitea_url = resolve_gitea_url(payload)
        gitea_token = resolve_gitea_token() or headers.get("X-Gitea-Token")
        if not gitea_url:
            return {"error": "Missing Gitea URL"}, 400
        if not gitea_token:
            return {"error": "Missing Gitea access token"}, 400

        repo = payload.get("repository") or {}
        event_id = self.repo.insert_event(
            review_type="mr" if event_type == "pull_request" else "push",
            source="gitea",
            event_type=event_type,
            project_name=repo.get("name", ""),
            project_url=repo.get("html_url", ""),
            created_at=int(time.time()),
            payload=payload,
        )

        self.queue.enqueue_gitea_event(
            payload=payload,
            url=gitea_url,
            event_id=event_id,
        )

        return {"message": "Request received, processing asynchronously", "event_id": event_id}, 200

    def process_job(self, job: Dict[str, object]) -> None:
        """处理队列中的作业 - 使用策略模式"""
        job_type = job.get("job_type")
        payload = job.get("payload") or {}
        url = job.get("url") or ""
        event_id = job.get("event_id")
        record_id = job.get("record_id")

        # 根据job_type从环境变量获取token并创建对应的handler
        if job_type == "gitlab_review":
            token = resolve_gitlab_token({})
            if not token:
                raise ValueError("GitLab access token not configured in environment")
            handler = GitLabHandler(base_url=url, token=token)
            event_type = payload.get("object_kind")
        elif job_type == "github_review":
            token = resolve_github_token()
            if not token:
                raise ValueError("GitHub access token not configured in environment")
            handler = GitHubHandler(base_url=url, token=token)
            event_type = "pull_request" if payload.get("pull_request") else "push"
        elif job_type == "gitea_review":
            token = resolve_gitea_token()
            if not token:
                raise ValueError("Gitea access token not configured in environment")
            handler = GiteaHandler(base_url=url, token=token)
            event_type = "pull_request" if payload.get("pull_request") else "push"
        else:
            raise ValueError(f"Unsupported job_type: {job_type}")

        # 创建编排器并处理
        orchestrator = ReviewOrchestrator(
            repo=self.repo,
            config=self.config,
            handler=handler,
        )

        # 根据事件类型调用对应的处理方法
        if event_type in {"merge_request", "pull_request"}:
            orchestrator.process_merge_request(
                payload=payload,
                event_id=event_id,
                record_id=record_id,
            )
        elif event_type == "push" or payload.get("ref"):
            orchestrator.process_push(
                payload=payload,
                event_id=event_id,
                record_id=record_id,
            )
        else:
            logger.warning("Unsupported event type: %s", event_type)
