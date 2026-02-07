"""集成测试：Webhook 到队列的完整流程

测试 webhook 接收 → 队列入队 → 作业处理的完整流程
"""
import json
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock, patch

from flask import Flask

from app.api.routes.webhook import webhook_bp
from app.infra.queue.db_queue import DbQueue


class TestWebhookIntegration(unittest.TestCase):
    def setUp(self):
        """测试前准备"""
        # 创建临时数据库
        self.db_fd, self.db_path = tempfile.mkstemp()

        # 创建 Flask 测试客户端
        self.app = Flask(__name__)
        self.app.config['TESTING'] = True
        self.app.register_blueprint(webhook_bp)
        self.client = self.app.test_client()

        # 初始化队列
        self.queue = DbQueue(self.db_path)
        self.queue.init_db()

    def tearDown(self):
        """测试后清理"""
        os.close(self.db_fd)
        os.unlink(self.db_path)

    @patch('app.api.routes.webhook.verify_gitlab_signature')
    @patch('app.api.routes.webhook.DbQueue')
    @patch('app.api.routes.webhook.SQLiteRepository')
    def test_gitlab_merge_request_webhook_to_queue(self, mock_repo_class, mock_queue_class, mock_verify):
        """测试 GitLab MR webhook 到队列的完整流程"""
        # 禁用签名验证
        mock_verify.return_value = True

        # 配置 mock
        mock_queue = Mock()
        mock_queue.enqueue_gitlab_event.return_value = 1
        mock_queue_class.return_value = mock_queue

        mock_repo = Mock()
        mock_repo.insert_event.return_value = 100
        mock_repo_class.return_value = mock_repo

        # 构造 GitLab MR webhook payload
        payload = {
            "object_kind": "merge_request",
            "project": {
                "name": "test-project",
                "web_url": "https://gitlab.example.com/test/project"
            },
            "object_attributes": {
                "iid": 1,
                "title": "Test MR",
                "state": "opened",
                "work_in_progress": False,
                "source_branch": "feature",
                "target_branch": "main",
                "last_commit": {
                    "id": "abc123"
                }
            },
            "user": {
                "username": "testuser",
                "name": "Test User"
            }
        }

        # 发送 webhook 请求
        response = self.client.post(
            '/review/webhook',
            data=json.dumps(payload),
            content_type='application/json',
            headers={'X-Gitlab-Token': 'test-token'}
        )

        # 验证响应
        self.assertEqual(response.status_code, 200)

        # 验证事件已插入
        mock_repo.insert_event.assert_called_once()

        # 验证作业已入队
        mock_queue.enqueue_gitlab_event.assert_called_once()

    @patch('app.api.routes.webhook.verify_github_signature')
    @patch('app.api.routes.webhook.DbQueue')
    @patch('app.api.routes.webhook.SQLiteRepository')
    def test_github_pull_request_webhook_to_queue(self, mock_repo_class, mock_queue_class, mock_verify):
        """测试 GitHub PR webhook 到队列的完整流程"""
        # 禁用签名验证
        mock_verify.return_value = True

        # 配置 mock
        mock_queue = Mock()
        mock_queue.enqueue_github_event.return_value = 1
        mock_queue_class.return_value = mock_queue

        mock_repo = Mock()
        mock_repo.insert_event.return_value = 100
        mock_repo_class.return_value = mock_repo

        # 构造 GitHub PR webhook payload
        payload = {
            "action": "opened",
            "pull_request": {
                "number": 1,
                "title": "Test PR",
                "state": "open",
                "draft": False,
                "head": {
                    "ref": "feature",
                    "sha": "abc123"
                },
                "base": {
                    "ref": "main"
                },
                "user": {
                    "login": "testuser"
                }
            },
            "repository": {
                "name": "test-repo",
                "full_name": "test/repo",
                "html_url": "https://github.com/test/repo"
            }
        }

        # 发送 webhook 请求
        response = self.client.post(
            '/review/webhook',
            data=json.dumps(payload),
            content_type='application/json',
            headers={'X-GitHub-Event': 'pull_request'}
        )

        # 验证响应
        self.assertEqual(response.status_code, 200)

        # 验证事件已插入
        mock_repo.insert_event.assert_called_once()

        # 验证作业已入队
        mock_queue.enqueue_github_event.assert_called_once()

    def test_queue_claim_and_process(self):
        """测试队列作业的获取和处理"""
        # 入队一个作业
        job_id = self.queue.enqueue_gitlab_event(
            payload={"test": "data"},
            url="https://gitlab.example.com",
            event_id=1,
            record_id=1
        )

        # 获取作业
        job = self.queue.claim_next_job()

        # 验证作业内容
        self.assertIsNotNone(job)
        self.assertEqual(job["id"], job_id)
        self.assertEqual(job["job_type"], "gitlab_review")
        self.assertEqual(job["payload"]["test"], "data")
        self.assertEqual(job["url"], "https://gitlab.example.com")

        # 标记作业完成
        self.queue.mark_done(job_id)

        # 验证作业状态
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT status FROM review_job WHERE id = ?", (job_id,))
            status = cursor.fetchone()[0]
            self.assertEqual(status, "done")

    def test_queue_job_retry_on_failure(self):
        """测试作业失败后的重试机制"""
        # 入队一个作业
        job_id = self.queue.enqueue_gitlab_event(
            payload={"test": "data"},
            url="https://gitlab.example.com",
            event_id=1,
            record_id=1
        )

        # 获取作业
        job = self.queue.claim_next_job()

        # 标记作业失败（第一次尝试）
        self.queue.mark_failed(
            job_id=job_id,
            attempts=1,
            max_attempts=3,
            error="Test error"
        )

        # 验证作业状态为 pending（等待重试）
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT status, attempts, run_after FROM review_job WHERE id = ?", (job_id,))
            row = cursor.fetchone()
            self.assertEqual(row[0], "pending")
            self.assertEqual(row[1], 1)

            # 手动设置 run_after 为过去的时间，以便立即重试
            import time
            now = int(time.time())
            cursor.execute("UPDATE review_job SET run_after = ? WHERE id = ?", (now - 1, job_id))
            conn.commit()

        # 再次获取作业（重试）
        job2 = self.queue.claim_next_job()
        self.assertIsNotNone(job2)
        self.assertEqual(job2["id"], job_id)
        self.assertEqual(job2["attempts"], 2)

    def test_queue_job_final_failure(self):
        """测试作业达到最大重试次数后标记为失败"""
        # 入队一个作业
        job_id = self.queue.enqueue_gitlab_event(
            payload={"test": "data"},
            url="https://gitlab.example.com",
            event_id=1,
            record_id=1
        )

        # 获取作业
        job = self.queue.claim_next_job()

        # 标记作业失败（达到最大重试次数）
        self.queue.mark_failed(
            job_id=job_id,
            attempts=3,
            max_attempts=3,
            error="Test error"
        )

        # 验证作业状态为 failed
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT status FROM review_job WHERE id = ?", (job_id,))
            status = cursor.fetchone()[0]
            self.assertEqual(status, "failed")


if __name__ == "__main__":
    unittest.main()
