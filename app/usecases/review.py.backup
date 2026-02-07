from __future__ import annotations

import time
from typing import Any, Dict, Tuple

from app.core.logging import get_logger
from app.core.token_util import count_tokens, truncate_text_by_tokens
from app.infra.db.sqlite import SQLiteRepository
from app.infra.llm.factory import LLMRetryExhaustedError, get_client, get_model_name
from app.infra.scm.gitlab import (
    GitLabClient,
    extract_mr_iid,
    extract_project_id,
    filter_changes,
    resolve_gitlab_token,
    resolve_gitlab_url,
    slugify_url,
)
from app.infra.scm.github import (
    GitHubClient,
    filter_changes as filter_github_changes,
    resolve_github_token,
    resolve_github_url,
)
from app.infra.scm.gitea import (
    GiteaClient,
    filter_changes as filter_gitea_changes,
    resolve_gitea_token,
    resolve_gitea_url,
)
from app.usecases.prompt_builder import PromptBuilder, parse_review_score
from app.core.config import AppConfig
from app.infra.notify.notifier import send_notification


logger = get_logger(__name__)


class ReviewUseCase:
    def __init__(self, repo: SQLiteRepository, queue: object, config: AppConfig) -> None:
        self.repo = repo
        self.queue = queue
        self.config = config

    def handle_webhook(
        self, payload: Dict[str, Any], headers: Dict[str, str]
    ) -> Tuple[Dict[str, Any], int]:
        if headers.get("X-GitHub-Event"):
            return self._handle_github(payload, headers)
        if headers.get("X-Gitea-Event"):
            return self._handle_gitea(payload, headers)
        return self._handle_gitlab(payload, headers)

    def _handle_gitlab(
        self, payload: Dict[str, Any], headers: Dict[str, str]
    ) -> Tuple[Dict[str, Any], int]:
        object_kind = payload.get("object_kind")
        if object_kind not in {"merge_request", "push"}:
            return {
                "error": "Only merge_request and push events are supported",
                "event_type": object_kind,
            }, 400

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
            token=gitlab_token,
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
        event_type = headers.get("X-GitHub-Event")
        if event_type not in {"pull_request", "push"}:
            return {"error": "Only pull_request and push events are supported"}, 400

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
            token=github_token,
            url=github_url,
            event_id=event_id,
        )

        return {"message": "Request received, processing asynchronously", "event_id": event_id}, 200

    def _handle_gitea(
        self, payload: Dict[str, Any], headers: Dict[str, str]
    ) -> Tuple[Dict[str, Any], int]:
        event_type = headers.get("X-Gitea-Event")
        if event_type not in {"pull_request", "push"}:
            return {"error": "Only pull_request and push events are supported"}, 400

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
            token=gitea_token,
            url=gitea_url,
            event_id=event_id,
        )

        return {"message": "Request received, processing asynchronously", "event_id": event_id}, 200

    def process_job(self, job: Dict[str, object]) -> None:
        job_type = job.get("job_type")
        payload = job.get("payload") or {}
        token = job.get("token") or ""
        url = job.get("url") or ""
        event_id = job.get("event_id")
        record_id = job.get("record_id")
        if job_type == "gitlab_review":
            self._process_gitlab_event(
                payload, token, url, event_id=event_id, record_id=record_id
            )
            return
        if job_type == "github_review":
            self._process_github_event(
                payload, token, url, event_id=event_id, record_id=record_id
            )
            return
        if job_type == "gitea_review":
            self._process_gitea_event(
                payload, token, url, event_id=event_id, record_id=record_id
            )
            return
        raise ValueError(f"Unsupported job_type: {job_type}")

    def _mark_skipped(
        self,
        review_type: str,
        record_id: int | None,
        reason: str,
        *,
        language: str = "",
        model_name: str = "",
    ) -> None:
        logger.info("[SKIP_LLM] %s %s", review_type, reason)
        if record_id is None:
            return
        message = f"跳过 AI 审查：{reason}"
        if review_type == "mr":
            self.repo.update_mr_review_log(
                record_id=int(record_id),
                score=0,
                review_result=message,
                status="skipped",
                language=language,
                model_name=model_name or "",
            )
        elif review_type == "push":
            self.repo.update_push_review_log(
                record_id=int(record_id),
                score=0,
                review_result=message,
                status="skipped",
                language=language,
                model_name=model_name or "",
            )

    def _process_gitlab_event(
        self,
        payload: Dict[str, Any],
        token: str,
        url: str,
        event_id: int | None = None,
        record_id: int | None = None,
    ) -> None:
        logger.info("Queued GitLab event for processing: event_id=%s", event_id)
        client = GitLabClient(base_url=url, token=token)
        llm_client = get_client()
        model_name = get_model_name()
        prompt_builder = PromptBuilder(self.config.review_style, model_name)

        object_kind = payload.get("object_kind")
        project_id = extract_project_id(payload)
        if not project_id:
            logger.warning("Missing project id in GitLab payload")
            return None

        if object_kind == "merge_request":
            mr_iid = extract_mr_iid(payload)
            if not mr_iid:
                logger.warning("Missing MR iid in GitLab payload")
                return None
            object_attrs = payload.get("object_attributes") or {}
            project_name = (payload.get("project") or {}).get("name", "")
            project_url = (payload.get("project") or {}).get("web_url", "")
            source_branch = object_attrs.get("source_branch", "")
            target_branch = object_attrs.get("target_branch", "")
            action = object_attrs.get("action") or ""

            if object_attrs.get("draft") or object_attrs.get("work_in_progress"):
                msg = (
                    f"[通知] MR为草稿（draft），未触发AI审查。\n"
                    f"项目: {project_name}\n"
                    f"作者: {(payload.get('user') or {}).get('username', '')}\n"
                    f"源分支: {source_branch}\n"
                    f"目标分支: {target_branch}\n"
                    f"链接: {object_attrs.get('url', '')}"
                )
                send_notification(
                    content=msg,
                    msg_type="text",
                    title="Merge Request Review",
                    project_name=project_name,
                    url_slug=slugify_url(url),
                    webhook_data=payload,
                )
                self._mark_skipped("mr", record_id, "MR 为 draft", model_name=model_name)
                return None

            if self.config.merge_review_only_protected_branches_enabled and not client.target_branch_protected(
                project_id, target_branch
            ):
                self._mark_skipped("mr", record_id, "目标分支非受保护分支", model_name=model_name)
                return None

            if action and action not in {"open", "update"}:
                self._mark_skipped(
                    "mr",
                    record_id,
                    f"action={action} 非 open/update",
                    model_name=model_name,
                )
                return None

            author_info = payload.get("user") or {}
            author_display_name = author_info.get("name") or author_info.get("username") or ""
            last_commit = object_attrs.get("last_commit") or {}
            last_commit_id = last_commit.get("id", "")
            if last_commit_id and self.repo.check_mr_last_commit_id_exists(
                project_name, source_branch, target_branch, last_commit_id
            ):
                self._mark_skipped(
                    "mr",
                    record_id,
                    f"last_commit_id={last_commit_id} 已存在",
                    model_name=model_name,
                )
                return None

            changes = client.get_merge_request_changes(project_id, mr_iid)
            filtered = filter_changes(changes)
            if not filtered:
                self._mark_skipped(
                    "mr",
                    record_id,
                    "未检测到有效变更或文件类型不支持",
                    model_name=model_name,
                )
                return None

            commits = client.get_merge_request_commits(project_id, mr_iid)
            if not commits and record_id is not None:
                self._mark_skipped("mr", record_id, "未获取到提交记录", model_name=model_name)
                return None

            review_text, score, language, status = self._review_changes(
                filtered,
                commits,
                llm_client,
                prompt_builder,
                empty_message="未检测到有效变更或文件类型不支持",
            )

            if status == "failed" and record_id is not None:
                return None

            if status == "success":
                client.add_merge_request_notes(project_id, mr_iid, review_text)

            if record_id:
                updated = self.repo.update_mr_review_log(
                    record_id=int(record_id),
                    score=score,
                    review_result=review_text,
                    status=status,
                    language=language,
                    model_name=model_name or "",
                )
            else:
                self.repo.insert_mr_review_log(
                    project_name=project_name,
                    author=author_info.get("username", ""),
                    author_display_name=author_display_name,
                    source_branch=source_branch,
                    target_branch=target_branch,
                    updated_at=int(time.time()),
                    commit_messages=self._join_commit_messages(commits, key="message"),
                    score=score,
                    model_name=model_name,
                    language=language,
                    url=object_attrs.get("url", ""),
                    review_result=review_text,
                    additions=self._sum_changes(filtered)[0],
                    deletions=self._sum_changes(filtered)[1],
                    last_commit_id=last_commit_id,
                    status=status,
                    project_url=project_url,
                    commit_url=object_attrs.get("url", ""),
                    event_id=event_id,
                )
            if status == "success":
                self._notify_merge_request(
                    project_name=project_name,
                    display_author=author_display_name or author_info.get("username", ""),
                    source_branch=source_branch,
                    target_branch=target_branch,
                    updated_at=int(time.time()),
                    commit_messages=self._join_commit_messages(commits, key="message"),
                    url=object_attrs.get("url", ""),
                    review_text=review_text,
                    url_slug=slugify_url(url),
                    webhook_data=payload,
                )
            logger.info(
                "MR review stored: total=%s, filtered=%s, commits=%s",
                len(changes),
                len(filtered),
                len(commits),
            )
            return None

        if object_kind == "push":
            before = payload.get("before", "")
            after = payload.get("after", "")
            commit_list = payload.get("commits") or []
            changes: list[dict] = []
            filtered: list[dict] = []
            commits = client.get_push_commits_from_payload(payload)
            if not commits:
                self._mark_skipped("push", record_id, "未获取到提交记录", model_name=model_name)
                if record_id is not None:
                    return None
            if not self.config.push_review_enabled:
                review_text = "AI 审查未启用"
                score = 0
                language = ""
                status = "skipped" if record_id is not None else "success"
            else:
                changes = client.get_push_changes(project_id, before, after, commit_list)
                filtered = filter_changes(changes)
                if not filtered:
                    if record_id is not None:
                        self._mark_skipped(
                            "push",
                            record_id,
                            "未检测到有效变更或文件类型不支持",
                            model_name=model_name,
                        )
                        return None
                    review_text = "关注的文件没有修改"
                    score = 0
                    language = prompt_builder.detect_primary_language_name(filtered)
                    status = "success"
                else:
                    review_text, score, language, status = self._review_changes(
                        filtered,
                        commits,
                        llm_client,
                        prompt_builder,
                        empty_message="关注的文件没有修改",
                    )

            author_display_name = payload.get("user_name") or payload.get("user_username") or ""
            commit_url = commits[-1].get("url", "") if commits else ""
            last_commit_id = after or (commit_list[-1].get("id") if commit_list else "")

            if status == "success" and last_commit_id and filtered and self.config.push_review_enabled:
                client.add_push_notes(project_id, last_commit_id, review_text)

            if status == "failed" and record_id is not None:
                return None

            if record_id:
                updated = self.repo.update_push_review_log(
                    record_id=int(record_id),
                    score=score,
                    review_result=review_text,
                    status=status,
                    language=language,
                    model_name=model_name or "",
                )
            else:
                self.repo.insert_push_review_log(
                    project_name=(payload.get("project") or {}).get("name", ""),
                    author=payload.get("user_username", ""),
                    author_display_name=author_display_name,
                    branch=(payload.get("ref") or "").replace("refs/heads/", ""),
                    updated_at=int(time.time()),
                    commit_messages=self._join_commit_messages(commits, key="message"),
                    score=score,
                    model_name=model_name,
                    language=language,
                    review_result=review_text,
                    additions=self._sum_changes(filtered)[0],
                    deletions=self._sum_changes(filtered)[1],
                    last_commit_id=last_commit_id or "",
                    status=status,
                    project_url=(payload.get("project") or {}).get("web_url", ""),
                    commit_url=commit_url,
                    event_id=event_id,
                )
            if status == "success":
                self._notify_push(
                    project_name=(payload.get("project") or {}).get("name", ""),
                    commits=commits,
                    review_text=review_text,
                    url_slug=slugify_url(url),
                    webhook_data=payload,
                )
            logger.info(
                "Push review stored: total=%s, filtered=%s, commits=%s",
                len(changes),
                len(filtered),
                len(commits),
            )
            return None

        logger.info("Unsupported GitLab event type: %s", object_kind)
        return None

    def _process_github_event(
        self,
        payload: Dict[str, Any],
        token: str,
        url: str,
        event_id: int | None = None,
        record_id: int | None = None,
    ) -> None:
        logger.info("Queued GitHub event for processing: event_id=%s", event_id)
        client = GitHubClient(base_url=url, token=token)
        llm_client = get_client()
        model_name = get_model_name()
        prompt_builder = PromptBuilder(self.config.review_style, model_name)

        if payload.get("pull_request"):
            pull_request = payload.get("pull_request") or {}
            action = payload.get("action") or ""
            repo = payload.get("repository") or {}
            repo_full_name = repo.get("full_name") or ""
            project_name = repo.get("name") or repo_full_name
            project_url = repo.get("html_url") or ""

            base_info = pull_request.get("base") or {}
            head_info = pull_request.get("head") or {}
            source_branch = head_info.get("ref") or ""
            target_branch = base_info.get("ref") or ""
            last_commit_id = head_info.get("sha") or ""

            if self.config.merge_review_only_protected_branches_enabled and not client.target_branch_protected(
                repo_full_name, target_branch
            ):
                self._mark_skipped("mr", record_id, "目标分支非受保护分支", model_name=model_name)
                return None

            if action and action not in {"opened", "synchronize"}:
                self._mark_skipped(
                    "mr",
                    record_id,
                    f"action={action} 非 opened/synchronize",
                    model_name=model_name,
                )
                return None

            if last_commit_id and self.repo.check_mr_last_commit_id_exists(
                project_name, source_branch, target_branch, last_commit_id
            ):
                self._mark_skipped(
                    "mr",
                    record_id,
                    f"last_commit_id={last_commit_id} 已存在",
                    model_name=model_name,
                )
                return None

            pr_number = pull_request.get("number")
            changes = client.get_pull_request_changes(repo_full_name, pr_number)
            filtered = filter_github_changes(changes)
            if not filtered:
                self._mark_skipped(
                    "mr",
                    record_id,
                    "未检测到有效变更或文件类型不支持",
                    model_name=model_name,
                )
                return None

            commits = client.get_pull_request_commits(repo_full_name, pr_number)
            if not commits:
                self._mark_skipped("mr", record_id, "未获取到提交记录", model_name=model_name)
                return None

            review_text, score, language, status = self._review_changes(
                filtered,
                commits,
                llm_client,
                prompt_builder,
                empty_message="未检测到有效变更或文件类型不支持",
            )

            if status == "failed" and record_id is not None:
                return None

            if status == "success":
                client.add_pull_request_notes(repo_full_name, pr_number, review_text)

            author_info = pull_request.get("user") or payload.get("sender") or {}
            author_display_name = author_info.get("name") or author_info.get("login") or ""

            if record_id:
                updated = self.repo.update_mr_review_log(
                    record_id=int(record_id),
                    score=score,
                    review_result=review_text,
                    status=status,
                    language=language,
                    model_name=model_name or "",
                )
            else:
                self.repo.insert_mr_review_log(
                    project_name=project_name,
                    author=author_info.get("login") or "",
                    author_display_name=author_display_name,
                    source_branch=source_branch,
                    target_branch=target_branch,
                    updated_at=int(time.time()),
                    commit_messages=self._join_commit_messages(commits, key="message"),
                    score=score,
                    model_name=model_name,
                    language=language,
                    url=pull_request.get("html_url") or "",
                    review_result=review_text,
                    additions=self._sum_changes(filtered)[0],
                    deletions=self._sum_changes(filtered)[1],
                    last_commit_id=last_commit_id,
                    status=status,
                    project_url=project_url,
                    commit_url=pull_request.get("html_url") or "",
                    event_id=event_id,
                )

            if status == "success":
                self._notify_merge_request(
                    project_name=project_name,
                    display_author=author_display_name or author_info.get("login", ""),
                    source_branch=source_branch,
                    target_branch=target_branch,
                    updated_at=int(time.time()),
                    commit_messages=self._join_commit_messages(commits, key="message"),
                    url=pull_request.get("html_url") or "",
                    review_text=review_text,
                    url_slug=slugify_url(url),
                    webhook_data=payload,
                )
            return None

        if payload.get("ref"):
            repo = payload.get("repository") or {}
            repo_full_name = repo.get("full_name") or ""
            project_name = repo.get("name") or repo_full_name
            project_url = repo.get("html_url") or ""
            before = payload.get("before", "")
            after = payload.get("after", "")
            commit_list = payload.get("commits") or []
            changes: list[dict] = []
            filtered: list[dict] = []

            commits = client.get_push_commits_from_payload(payload)
            if not commits:
                self._mark_skipped("push", record_id, "未获取到提交记录", model_name=model_name)
                return None

            sender = payload.get("sender") or {}
            pusher = payload.get("pusher") or {}
            head_commit = payload.get("head_commit") or {}
            head_author = head_commit.get("author") if isinstance(head_commit, dict) else {}
            author_display_name = (
                pusher.get("name")
                or (head_author or {}).get("name")
                or sender.get("login")
                or ""
            )

            if not self.config.push_review_enabled:
                review_text = "AI 审查未启用"
                score = 0
                language = ""
                status = "skipped" if record_id is not None else "success"
            else:
                changes = client.get_push_changes(
                    repo_full_name,
                    before,
                    after,
                    commit_list,
                    created=bool(payload.get("created")),
                    deleted=bool(payload.get("deleted")),
                )
                filtered = filter_github_changes(changes)
                if not filtered:
                    if record_id is not None:
                        self._mark_skipped(
                            "push",
                            record_id,
                            "未检测到有效变更或文件类型不支持",
                            model_name=model_name,
                        )
                        return None
                    review_text = "关注的文件没有修改"
                    score = 0
                    language = prompt_builder.detect_primary_language_name(filtered)
                    status = "success"
                else:
                    review_text, score, language, status = self._review_changes(
                        filtered,
                        commits,
                        llm_client,
                        prompt_builder,
                        empty_message="关注的文件没有修改",
                    )

            commit_url = commits[-1].get("url", "") if commits else ""
            last_commit_id = after or (commit_list[-1].get("id") if commit_list else "")

            if status == "success" and last_commit_id and filtered and self.config.push_review_enabled:
                client.add_push_notes(repo_full_name, last_commit_id, review_text)

            if status == "failed" and record_id is not None:
                return None

            if record_id:
                updated = self.repo.update_push_review_log(
                    record_id=int(record_id),
                    score=score,
                    review_result=review_text,
                    status=status,
                    language=language,
                    model_name=model_name or "",
                )
            else:
                self.repo.insert_push_review_log(
                    project_name=project_name,
                    author=(payload.get("sender") or {}).get("login", ""),
                    author_display_name=author_display_name,
                    branch=(payload.get("ref") or "").replace("refs/heads/", ""),
                    updated_at=int(time.time()),
                    commit_messages=self._join_commit_messages(commits, key="message"),
                    score=score,
                    model_name=model_name,
                    language=language,
                    review_result=review_text,
                    additions=self._sum_changes(filtered)[0],
                    deletions=self._sum_changes(filtered)[1],
                    last_commit_id=last_commit_id or "",
                    status=status,
                    project_url=project_url,
                    commit_url=commit_url,
                    event_id=event_id,
                )

            if status == "success":
                self._notify_push(
                    project_name=project_name,
                    commits=commits,
                    review_text=review_text,
                    url_slug=slugify_url(url),
                    webhook_data=payload,
                )
            return None

        logger.info("Unsupported GitHub event payload")
        return None

    def _process_gitea_event(
        self,
        payload: Dict[str, Any],
        token: str,
        url: str,
        event_id: int | None = None,
        record_id: int | None = None,
    ) -> None:
        logger.info("Queued Gitea event for processing: event_id=%s", event_id)
        client = GiteaClient(base_url=url, token=token)
        llm_client = get_client()
        model_name = get_model_name()
        prompt_builder = PromptBuilder(self.config.review_style, model_name)

        if payload.get("pull_request"):
            pull_request = payload.get("pull_request") or {}
            action = payload.get("action") or ""
            repo = payload.get("repository") or {}
            repo_full_name = repo.get("full_name")
            if not repo_full_name:
                owner_info = repo.get("owner") or {}
                owner = (
                    owner_info.get("login")
                    or owner_info.get("name")
                    or owner_info.get("username")
                )
                name = repo.get("name")
                if owner and name:
                    repo_full_name = f"{owner}/{name}"
            repo_full_name = repo_full_name or ""
            project_name = repo.get("name") or repo_full_name
            project_url = repo.get("html_url") or ""

            base_info = pull_request.get("base") or {}
            head_info = pull_request.get("head") or {}
            source_branch = head_info.get("ref") or pull_request.get("head_branch", "")
            target_branch = base_info.get("ref") or pull_request.get("base_branch", "")

            if self.config.merge_review_only_protected_branches_enabled and not client.target_branch_protected(
                repo_full_name, target_branch
            ):
                self._mark_skipped("mr", record_id, "目标分支非受保护分支", model_name=model_name)
                return None

            if action and action not in {
                "opened",
                "open",
                "reopened",
                "synchronize",
                "synchronized",
            }:
                self._mark_skipped(
                    "mr",
                    record_id,
                    f"action={action} 非允许范围",
                    model_name=model_name,
                )
                return None

            last_commit_id = (
                head_info.get("sha")
                or pull_request.get("merge_commit_sha")
                or pull_request.get("last_commit_id")
                or ""
            )
            if last_commit_id and self.repo.check_mr_last_commit_id_exists(
                project_name, source_branch, target_branch, last_commit_id
            ):
                self._mark_skipped(
                    "mr",
                    record_id,
                    f"last_commit_id={last_commit_id} 已存在",
                    model_name=model_name,
                )
                return None

            pr_number = (
                pull_request.get("number")
                or pull_request.get("index")
                or pull_request.get("id")
            )
            changes = client.get_pull_request_changes(repo_full_name, pr_number)
            filtered = filter_gitea_changes(changes)
            if not filtered:
                self._mark_skipped(
                    "mr",
                    record_id,
                    "未检测到有效变更或文件类型不支持",
                    model_name=model_name,
                )
                return None

            commits = client.get_pull_request_commits(repo_full_name, pr_number)
            if not commits:
                self._mark_skipped("mr", record_id, "未获取到提交记录", model_name=model_name)
                return None

            review_text, score, language, status = self._review_changes(
                filtered,
                commits,
                llm_client,
                prompt_builder,
                empty_message="未检测到有效变更或文件类型不支持",
            )

            if status == "failed" and record_id is not None:
                return None

            if status == "success":
                client.add_pull_request_notes(repo_full_name, pr_number, review_text)

            author_info = pull_request.get("user") or payload.get("sender") or {}
            author_display_name = (
                author_info.get("full_name")
                or author_info.get("name")
                or author_info.get("login")
                or author_info.get("username")
                or ""
            )

            pr_url = pull_request.get("html_url") or pull_request.get("url") or ""

            if record_id:
                updated = self.repo.update_mr_review_log(
                    record_id=int(record_id),
                    score=score,
                    review_result=review_text,
                    status=status,
                    language=language,
                    model_name=model_name or "",
                )
            else:
                self.repo.insert_mr_review_log(
                    project_name=project_name,
                    author=author_info.get("login") or author_info.get("username") or "",
                    author_display_name=author_display_name,
                    source_branch=source_branch,
                    target_branch=target_branch,
                    updated_at=int(time.time()),
                    commit_messages=self._join_commit_messages(commits, key="message"),
                    score=score,
                    model_name=model_name,
                    language=language,
                    url=pr_url,
                    review_result=review_text,
                    additions=self._sum_changes(filtered)[0],
                    deletions=self._sum_changes(filtered)[1],
                    last_commit_id=last_commit_id,
                    status=status,
                    project_url=project_url,
                    commit_url=pr_url,
                    event_id=event_id,
                )

            if status == "success":
                self._notify_merge_request(
                    project_name=project_name,
                    display_author=author_display_name or author_info.get("login", ""),
                    source_branch=source_branch,
                    target_branch=target_branch,
                    updated_at=int(time.time()),
                    commit_messages=self._join_commit_messages(commits, key="message"),
                    url=pr_url,
                    review_text=review_text,
                    url_slug=slugify_url(url),
                    webhook_data=payload,
                )
            return None

        if payload.get("ref"):
            repo = payload.get("repository") or {}
            repo_full_name = repo.get("full_name")
            if not repo_full_name:
                owner_info = repo.get("owner") or {}
                owner = (
                    owner_info.get("login")
                    or owner_info.get("name")
                    or owner_info.get("username")
                )
                name = repo.get("name")
                if owner and name:
                    repo_full_name = f"{owner}/{name}"
            repo_full_name = repo_full_name or ""
            project_name = repo.get("name") or repo_full_name
            project_url = repo.get("html_url") or ""

            commit_list = payload.get("commits") or []
            changes: list[dict] = []
            filtered: list[dict] = []
            commits = client.get_push_commits_from_payload(payload)
            if not commits:
                self._mark_skipped("push", record_id, "未获取到提交记录", model_name=model_name)
                return None

            if not self.config.push_review_enabled:
                review_text = "AI 审查未启用"
                score = 0
                language = ""
                status = "skipped" if record_id is not None else "success"
            else:
                changes = client.get_push_changes(repo_full_name, commit_list)
                filtered = filter_gitea_changes(changes)
                if not filtered:
                    if record_id is not None:
                        self._mark_skipped(
                            "push",
                            record_id,
                            "未检测到有效变更或文件类型不支持",
                            model_name=model_name,
                        )
                        return None
                    review_text = "关注的文件没有修改"
                    score = 0
                    language = prompt_builder.detect_primary_language_name(filtered)
                    status = "success"
                else:
                    review_text, score, language, status = self._review_changes(
                        filtered,
                        commits,
                        llm_client,
                        prompt_builder,
                        empty_message="关注的文件没有修改",
                    )

            commit_url = commits[-1].get("url", "") if commits else ""
            last_commit_id = commit_list[-1].get("id") if commit_list else ""

            if status == "failed" and record_id is not None:
                return None

            if record_id:
                updated = self.repo.update_push_review_log(
                    record_id=int(record_id),
                    score=score,
                    review_result=review_text,
                    status=status,
                    language=language,
                    model_name=model_name or "",
                )
            else:
                self.repo.insert_push_review_log(
                    project_name=project_name,
                    author=(payload.get("sender") or {}).get("login")
                    or (payload.get("pusher") or {}).get("username")
                    or "",
                    author_display_name=(payload.get("sender") or {}).get("name")
                    or (payload.get("pusher") or {}).get("name")
                    or "",
                    branch=(payload.get("ref") or "").replace("refs/heads/", ""),
                    updated_at=int(time.time()),
                    commit_messages=self._join_commit_messages(commits, key="message"),
                    score=score,
                    model_name=model_name,
                    language=language,
                    review_result=review_text,
                    additions=self._sum_changes(filtered)[0],
                    deletions=self._sum_changes(filtered)[1],
                    last_commit_id=last_commit_id or "",
                    status=status,
                    project_url=project_url,
                    commit_url=commit_url,
                    event_id=event_id,
                )

            if status == "success":
                self._notify_push(
                    project_name=project_name,
                    commits=commits,
                    review_text=review_text,
                    url_slug=slugify_url(url),
                    webhook_data=payload,
                )
            return None

        logger.info("Unsupported Gitea event payload")
        return None

    def _review_changes(
        self,
        changes: list[dict],
        commits: list[dict],
        llm_client,
        prompt_builder: PromptBuilder,
        empty_message: str,
    ) -> tuple[str, int, str, str]:
        language = prompt_builder.detect_primary_language_name(changes)
        if not changes:
            return empty_message, 0, language, "skipped"

        changes_text = str(changes)
        if count_tokens(changes_text) > self.config.review_max_tokens:
            changes_text = truncate_text_by_tokens(
                changes_text, self.config.review_max_tokens
            )

        commits_text = self._join_commit_messages(commits, key="message")
        messages, language = prompt_builder.build_messages(
            changes_text, commits_text, changes
        )
        try:
            review_text = llm_client.completions(messages=messages)
            status = "success"
        except LLMRetryExhaustedError as exc:
            review_text = f"AI 审查失败（{get_model_name()}）：{str(exc)[:200]}"
            status = "failed"

        review_text = self._strip_markdown_fences(review_text)
        score = parse_review_score(review_text)
        return review_text, score, language, status

    @staticmethod
    def _strip_markdown_fences(text: str) -> str:
        if not text:
            return text
        if text.startswith("```markdown") and text.endswith("```"):
            return text[11:-3].strip()
        if text.startswith("```") and text.endswith("```"):
            return text[3:-3].strip()
        return text

    @staticmethod
    def _sum_changes(changes: list[dict]) -> tuple[int, int]:
        additions = 0
        deletions = 0
        for item in changes or []:
            additions += int(item.get("additions", 0) or 0)
            deletions += int(item.get("deletions", 0) or 0)
        return additions, deletions

    @staticmethod
    def _join_commit_messages(commits: list[dict], key: str) -> str:
        return ";".join((commit.get(key) or "").strip() for commit in commits)


    def _notify_merge_request(
        self,
        *,
        project_name: str,
        display_author: str,
        source_branch: str,
        target_branch: str,
        updated_at: int,
        commit_messages: str,
        url: str,
        review_text: str,
        url_slug: str,
        webhook_data: Dict[str, Any],
    ) -> None:
        im_msg = f"""
### 🔀 {project_name}: Merge Request

#### 合并请求信息:
- **提交者:** {display_author}

- **源分支**: {source_branch}
- **目标分支**: {target_branch}
- **更新时间**: {updated_at}
- **提交信息:** {commit_messages}

- [查看合并详情]({url})

- **AI Review 结果:** 

{review_text}
"""
        send_notification(
            content=im_msg,
            msg_type="markdown",
            title="Merge Request Review",
            project_name=project_name,
            url_slug=url_slug,
            webhook_data=webhook_data,
        )

    def _notify_push(
        self,
        *,
        project_name: str,
        commits: list[dict],
        review_text: str,
        url_slug: str,
        webhook_data: Dict[str, Any],
    ) -> None:
        im_msg = f"### 🚀 {project_name}: Push\n\n"
        im_msg += "#### 提交记录:\n"

        display_author = (
            webhook_data.get("user_name")
            or webhook_data.get("user_username")
            or (webhook_data.get("pusher") or {}).get("name")
            or (webhook_data.get("sender") or {}).get("login")
            or ""
        )
        if commits:
            latest = commits[0]
            message = (latest.get("message") or "").strip()
            author = latest.get("author") or display_author
            timestamp = latest.get("timestamp", "")
            url = latest.get("url", "#")
            im_msg += (
                f"- **提交信息**: {message}\n"
                f"- **提交者**: {author}\n"
                f"- **时间**: {timestamp}\n"
                f"- [查看提交详情]({url})\n\n"
            )
            if len(commits) > 1:
                im_msg += f"- 和其它 {len(commits) - 1} 条提交记录\n\n"

        if review_text:
            im_msg += f"#### AI Review 结果: \n {review_text}\n\n"

        send_notification(
            content=im_msg,
            msg_type="markdown",
            title=f"{project_name} Push Event",
            project_name=project_name,
            url_slug=url_slug,
            webhook_data=webhook_data,
        )
