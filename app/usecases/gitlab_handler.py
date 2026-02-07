"""GitLab平台处理器实现"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.infra.scm.gitlab import (
    GitLabClient,
    extract_mr_iid,
    extract_project_id,
    filter_changes,
    slugify_url,
)
from app.usecases.platform_handler import PlatformHandler


class GitLabHandler(PlatformHandler):
    """GitLab平台处理器"""

    def _create_client(self):
        return GitLabClient(base_url=self.base_url, token=self.token)

    def parse_merge_request_info(
        self, payload: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        project_id = extract_project_id(payload)
        mr_iid = extract_mr_iid(payload)
        if not project_id or not mr_iid:
            return None

        object_attrs = payload.get("object_attributes") or {}
        author_info = payload.get("user") or {}
        last_commit = object_attrs.get("last_commit") or {}

        return {
            "project_id": project_id,
            "mr_number": mr_iid,
            "project_name": (payload.get("project") or {}).get("name", ""),
            "project_url": (payload.get("project") or {}).get("web_url", ""),
            "source_branch": object_attrs.get("source_branch", ""),
            "target_branch": object_attrs.get("target_branch", ""),
            "last_commit_id": last_commit.get("id", ""),
            "author": author_info.get("username", ""),
            "author_display_name": author_info.get("name")
            or author_info.get("username")
            or "",
            "url": object_attrs.get("url", ""),
            "action": object_attrs.get("action") or "",
            "is_draft": object_attrs.get("draft")
            or object_attrs.get("work_in_progress")
            or False,
        }

    def parse_push_info(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        project = payload.get("project") or {}
        # 使用数字 ID 而不是 path_with_namespace，因为 GitLab API 需要数字 ID 或 URL 编码的路径
        project_id = str(payload.get("project_id") or project.get("id") or "")
        return {
            "project_id": project_id,
            "project_name": project.get("name", ""),
            "project_url": project.get("web_url", ""),
            "branch": (payload.get("ref") or "").replace("refs/heads/", ""),
            "before": payload.get("before", ""),
            "after": payload.get("after", ""),
            "commit_list": payload.get("commits") or [],
            "author": payload.get("user_username", ""),
            "author_display_name": payload.get("user_name")
            or payload.get("user_username")
            or "",
        }

    def get_merge_request_changes(
        self, project_id: str, mr_number: int
    ) -> List[Dict[str, Any]]:
        return self.client.get_merge_request_changes(project_id, mr_number)

    def get_merge_request_commits(
        self, project_id: str, mr_number: int
    ) -> List[Dict[str, Any]]:
        return self.client.get_merge_request_commits(project_id, mr_number)

    def get_push_changes(
        self, project_id: str, payload: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        push_info = self.parse_push_info(payload)
        return self.client.get_push_changes(
            project_id,
            push_info["before"],
            push_info["after"],
            push_info["commit_list"],
        )

    def get_push_commits(self, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        return self.client.get_push_commits_from_payload(payload)

    def filter_changes(self, changes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return filter_changes(changes)

    def add_merge_request_comment(
        self, project_id: str, mr_number: int, comment: str
    ) -> None:
        self.client.add_merge_request_notes(project_id, mr_number, comment)

    def add_push_comment(self, project_id: str, commit_id: str, comment: str) -> None:
        self.client.add_push_notes(project_id, commit_id, comment)

    def is_target_branch_protected(self, project_id: str, branch: str) -> bool:
        return self.client.target_branch_protected(project_id, branch)

    def get_url_slug(self) -> str:
        return slugify_url(self.base_url)
