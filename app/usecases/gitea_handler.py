"""Gitea平台处理器实现"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.infra.scm.gitea import GiteaClient, filter_changes as filter_gitea_changes
from app.infra.scm.gitlab import slugify_url
from app.usecases.platform_handler import PlatformHandler


class GiteaHandler(PlatformHandler):
    """Gitea平台处理器"""

    def _create_client(self):
        return GiteaClient(base_url=self.base_url, token=self.token)

    def parse_merge_request_info(
        self, payload: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        pull_request = payload.get("pull_request")
        if not pull_request:
            return None

        repo = payload.get("repository") or {}
        repo_full_name = self._get_repo_full_name(repo)
        base_info = pull_request.get("base") or {}
        head_info = pull_request.get("head") or {}
        author_info = pull_request.get("user") or payload.get("sender") or {}

        last_commit_id = (
            head_info.get("sha")
            or pull_request.get("merge_commit_sha")
            or pull_request.get("last_commit_id")
            or ""
        )

        author_display_name = (
            author_info.get("full_name")
            or author_info.get("name")
            or author_info.get("login")
            or author_info.get("username")
            or ""
        )

        return {
            "project_id": repo_full_name,
            "mr_number": pull_request.get("number")
            or pull_request.get("index")
            or pull_request.get("id"),
            "project_name": repo.get("name") or repo_full_name,
            "project_url": repo.get("html_url") or "",
            "source_branch": head_info.get("ref") or pull_request.get("head_branch", ""),
            "target_branch": base_info.get("ref") or pull_request.get("base_branch", ""),
            "last_commit_id": last_commit_id,
            "author": author_info.get("login") or author_info.get("username") or "",
            "author_display_name": author_display_name,
            "url": pull_request.get("html_url") or pull_request.get("url") or "",
            "action": payload.get("action") or "",
            "is_draft": pull_request.get("draft") or False,
        }

    def parse_push_info(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not payload.get("ref"):
            return None

        repo = payload.get("repository") or {}
        repo_full_name = self._get_repo_full_name(repo)
        sender = payload.get("sender") or {}
        pusher = payload.get("pusher") or {}

        author_display_name = (
            sender.get("name") or pusher.get("name") or ""
        )

        return {
            "project_id": repo_full_name,
            "project_name": repo.get("name") or repo_full_name,
            "project_url": repo.get("html_url") or "",
            "branch": (payload.get("ref") or "").replace("refs/heads/", ""),
            "before": payload.get("before", ""),
            "after": payload.get("after", ""),
            "commit_list": payload.get("commits") or [],
            "author": sender.get("login") or pusher.get("username") or "",
            "author_display_name": author_display_name,
        }

    def get_merge_request_changes(
        self, project_id: str, mr_number: int
    ) -> List[Dict[str, Any]]:
        return self.client.get_pull_request_changes(project_id, mr_number)

    def get_merge_request_commits(
        self, project_id: str, mr_number: int
    ) -> List[Dict[str, Any]]:
        return self.client.get_pull_request_commits(project_id, mr_number)

    def get_push_changes(
        self, project_id: str, payload: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        push_info = self.parse_push_info(payload)
        return self.client.get_push_changes(project_id, push_info["commit_list"])

    def get_push_commits(self, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        return self.client.get_push_commits_from_payload(payload)

    def filter_changes(self, changes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return filter_gitea_changes(changes)

    def add_merge_request_comment(
        self, project_id: str, mr_number: int, comment: str
    ) -> None:
        self.client.add_pull_request_notes(project_id, mr_number, comment)

    def add_push_comment(self, project_id: str, commit_id: str, comment: str) -> None:
        # Gitea doesn't support commit comments in the same way
        pass

    def is_target_branch_protected(self, project_id: str, branch: str) -> bool:
        return self.client.target_branch_protected(project_id, branch)

    def get_url_slug(self) -> str:
        return slugify_url(self.base_url)

    @staticmethod
    def _get_repo_full_name(repo: Dict[str, Any]) -> str:
        """从repo信息中提取完整仓库名"""
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
        return repo_full_name or ""
