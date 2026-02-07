"""平台处理器抽象层 - 封装不同Git平台的特定逻辑"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple


class PlatformHandler(ABC):
    """Git平台处理器抽象基类"""

    def __init__(self, base_url: str, token: str):
        self.base_url = base_url
        self.token = token
        self.client = self._create_client()

    @abstractmethod
    def _create_client(self):
        """创建平台特定的客户端"""
        pass

    @abstractmethod
    def parse_merge_request_info(
        self, payload: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        解析MR/PR信息
        返回: {
            'project_id': str,
            'mr_number': int,
            'project_name': str,
            'project_url': str,
            'source_branch': str,
            'target_branch': str,
            'last_commit_id': str,
            'author': str,
            'author_display_name': str,
            'url': str,
            'action': str,
            'is_draft': bool,
        }
        """
        pass

    @abstractmethod
    def parse_push_info(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        解析Push信息
        返回: {
            'project_name': str,
            'project_url': str,
            'branch': str,
            'before': str,
            'after': str,
            'commit_list': List[Dict],
            'author': str,
            'author_display_name': str,
        }
        """
        pass

    @abstractmethod
    def get_merge_request_changes(
        self, project_id: str, mr_number: int
    ) -> List[Dict[str, Any]]:
        """获取MR/PR的变更"""
        pass

    @abstractmethod
    def get_merge_request_commits(
        self, project_id: str, mr_number: int
    ) -> List[Dict[str, Any]]:
        """获取MR/PR的提交记录"""
        pass

    @abstractmethod
    def get_push_changes(
        self, project_id: str, payload: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """获取Push的变更"""
        pass

    @abstractmethod
    def get_push_commits(self, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        """获取Push的提交记录"""
        pass

    @abstractmethod
    def filter_changes(self, changes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """过滤变更（按文件类型）"""
        pass

    @abstractmethod
    def add_merge_request_comment(
        self, project_id: str, mr_number: int, comment: str
    ) -> None:
        """在MR/PR上添加评论"""
        pass

    @abstractmethod
    def add_push_comment(self, project_id: str, commit_id: str, comment: str) -> None:
        """在Push提交上添加评论"""
        pass

    @abstractmethod
    def is_target_branch_protected(
        self, project_id: str, branch: str
    ) -> bool:
        """检查目标分支是否受保护"""
        pass

    @abstractmethod
    def get_url_slug(self) -> str:
        """获取URL slug用于通知"""
        pass
