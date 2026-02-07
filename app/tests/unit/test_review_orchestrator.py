"""单元测试：ReviewOrchestrator"""
import unittest
from unittest.mock import Mock, MagicMock, patch
from app.usecases.review_orchestrator import ReviewOrchestrator
from app.core.config import AppConfig


class TestReviewOrchestrator(unittest.TestCase):
    def setUp(self):
        """测试前准备"""
        self.mock_repo = Mock()
        self.mock_handler = Mock()
        self.config = AppConfig(
            env="test",
            server_port=5001,
            templates_dir="templates",
            static_dir="static",
            db_file=":memory:",
            dashboard_secret_key="test_key",
            dashboard_cookie_secure=False,
            push_review_enabled=True,
            merge_review_only_protected_branches_enabled=False,
            review_style="professional",
            review_max_tokens=10000,
            llm_retry_count=3,
        )

    @patch('app.usecases.review_orchestrator.get_client')
    @patch('app.usecases.review_orchestrator.get_model_name')
    def test_process_merge_request_draft(self, mock_model, mock_client):
        """测试草稿 MR 被跳过"""
        mock_model.return_value = "test-model"

        orchestrator = ReviewOrchestrator(
            repo=self.mock_repo,
            config=self.config,
            handler=self.mock_handler,
        )

        # 模拟草稿 MR
        self.mock_handler.parse_merge_request_info.return_value = {
            "project_id": "test/project",
            "mr_number": 1,
            "project_name": "test-project",
            "project_url": "https://gitlab.com/test/project",
            "source_branch": "feature",
            "target_branch": "main",
            "last_commit_id": "abc123",
            "author": "testuser",
            "author_display_name": "Test User",
            "url": "https://gitlab.com/test/project/-/merge_requests/1",
            "action": "open",
            "is_draft": True,  # 草稿
        }

        orchestrator.process_merge_request(payload={}, event_id=1, record_id=1)

        # 验证：不应该获取变更
        self.mock_handler.get_merge_request_changes.assert_not_called()

    def test_sum_changes(self):
        """测试变更统计"""
        changes = [
            {"additions": 10, "deletions": 5},
            {"additions": 20, "deletions": 15},
        ]
        additions, deletions = ReviewOrchestrator._sum_changes(changes)
        self.assertEqual(additions, 30)
        self.assertEqual(deletions, 20)

    def test_strip_markdown_fences(self):
        """测试 markdown 代码块移除"""
        text = "```markdown\ntest content\n```"
        result = ReviewOrchestrator._strip_markdown_fences(text)
        self.assertEqual(result, "test content")

        text = "```\ntest content\n```"
        result = ReviewOrchestrator._strip_markdown_fences(text)
        self.assertEqual(result, "test content")

        text = "plain text"
        result = ReviewOrchestrator._strip_markdown_fences(text)
        self.assertEqual(result, "plain text")


if __name__ == "__main__":
    unittest.main()
