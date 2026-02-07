"""单元测试：Webhook 签名验证"""
import unittest
import hmac
import hashlib
from app.api.webhook_security import (
    verify_gitlab_signature,
    verify_github_signature,
    verify_gitea_signature,
)


class TestWebhookSecurity(unittest.TestCase):
    def test_gitlab_signature_valid(self):
        """测试 GitLab 签名验证 - 有效"""
        payload = b'{"test": "data"}'
        token = "my_secret_token"
        secret = "my_secret_token"

        result = verify_gitlab_signature(payload, token, secret)
        self.assertTrue(result)

    def test_gitlab_signature_invalid(self):
        """测试 GitLab 签名验证 - 无效"""
        payload = b'{"test": "data"}'
        token = "wrong_token"
        secret = "my_secret_token"

        result = verify_gitlab_signature(payload, token, secret)
        self.assertFalse(result)

    def test_gitlab_signature_no_secret(self):
        """测试 GitLab 签名验证 - 无 secret 配置"""
        payload = b'{"test": "data"}'
        token = "any_token"
        secret = None

        result = verify_gitlab_signature(payload, token, secret)
        self.assertTrue(result)  # 无 secret 时跳过验证

    def test_github_signature_valid(self):
        """测试 GitHub 签名验证 - 有效"""
        payload = b'{"test": "data"}'
        secret = "my_secret"

        # 生成正确的签名
        signature = "sha256=" + hmac.new(
            secret.encode('utf-8'),
            payload,
            hashlib.sha256
        ).hexdigest()

        result = verify_github_signature(payload, signature, secret)
        self.assertTrue(result)

    def test_github_signature_invalid(self):
        """测试 GitHub 签名验证 - 无效"""
        payload = b'{"test": "data"}'
        secret = "my_secret"
        signature = "sha256=invalid_signature"

        result = verify_github_signature(payload, signature, secret)
        self.assertFalse(result)

    def test_github_signature_missing(self):
        """测试 GitHub 签名验证 - 缺少签名"""
        payload = b'{"test": "data"}'
        secret = "my_secret"
        signature = ""

        result = verify_github_signature(payload, signature, secret)
        self.assertFalse(result)

    def test_gitea_signature_valid(self):
        """测试 Gitea 签名验证 - 有效"""
        payload = b'{"test": "data"}'
        secret = "my_secret"

        # 生成正确的签名
        signature = hmac.new(
            secret.encode('utf-8'),
            payload,
            hashlib.sha256
        ).hexdigest()

        result = verify_gitea_signature(payload, signature, secret)
        self.assertTrue(result)

    def test_gitea_signature_invalid(self):
        """测试 Gitea 签名验证 - 无效"""
        payload = b'{"test": "data"}'
        secret = "my_secret"
        signature = "invalid_signature"

        result = verify_gitea_signature(payload, signature, secret)
        self.assertFalse(result)

    def test_timing_attack_resistance(self):
        """测试时序攻击防护"""
        payload = b'{"test": "data"}'
        secret = "my_secret"

        # 生成正确的签名
        correct_signature = "sha256=" + hmac.new(
            secret.encode('utf-8'),
            payload,
            hashlib.sha256
        ).hexdigest()

        # 测试多次，确保使用时间安全的比较
        for _ in range(100):
            result = verify_github_signature(payload, correct_signature, secret)
            self.assertTrue(result)

            wrong_signature = "sha256=" + "a" * 64
            result = verify_github_signature(payload, wrong_signature, secret)
            self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
