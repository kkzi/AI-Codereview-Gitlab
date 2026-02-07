"""单元测试：配置验证器"""
import os
import unittest
from unittest.mock import patch

from app.core.config_validator import ConfigValidator, ValidationError


class TestConfigValidator(unittest.TestCase):
    def setUp(self):
        """测试前准备"""
        self.validator = ConfigValidator()

    def test_validate_openai_config_success(self):
        """测试 OpenAI 配置验证成功"""
        with patch('app.core.config_validator.get_llm_value') as mock_get:
            mock_get.side_effect = lambda key, default=None: {
                "LLM_PROVIDER": "openai",
                "OPENAI_API_KEY": "sk-test123",
                "OPENAI_API_BASE_URL": "https://api.openai.com/v1",
                "OPENAI_API_MODEL": "gpt-4"
            }.get(key, default)

            self.validator._validate_llm_config()

            # 不应该有错误
            self.assertEqual(len(self.validator.errors), 0)

    def test_validate_openai_config_missing_key(self):
        """测试 OpenAI 配置缺少 API Key"""
        with patch('app.core.config_validator.get_llm_value') as mock_get:
            mock_get.side_effect = lambda key, default=None: {
                "LLM_PROVIDER": "openai",
                "OPENAI_API_BASE_URL": "https://api.openai.com/v1",
                "OPENAI_API_MODEL": "gpt-4"
            }.get(key, default)

            self.validator._validate_llm_config()

            # 应该有一个错误
            self.assertEqual(len(self.validator.errors), 1)
            self.assertEqual(self.validator.errors[0].field, "OPENAI_API_KEY")

    def test_validate_openai_config_invalid_url(self):
        """测试 OpenAI 配置无效的 URL"""
        with patch('app.core.config_validator.get_llm_value') as mock_get:
            mock_get.side_effect = lambda key, default=None: {
                "LLM_PROVIDER": "openai",
                "OPENAI_API_KEY": "sk-test123",
                "OPENAI_API_BASE_URL": "not-a-valid-url",
                "OPENAI_API_MODEL": "gpt-4"
            }.get(key, default)

            self.validator._validate_llm_config()

            # 应该有一个错误
            errors = [e for e in self.validator.errors if e.field == "OPENAI_API_BASE_URL"]
            self.assertEqual(len(errors), 1)

    def test_validate_unsupported_provider(self):
        """测试不支持的 LLM 提供商"""
        with patch('app.core.config_validator.get_llm_value') as mock_get:
            mock_get.side_effect = lambda key, default=None: {
                "LLM_PROVIDER": "unsupported_provider"
            }.get(key, default)

            self.validator._validate_llm_config()

            # 应该有一个错误
            self.assertEqual(len(self.validator.errors), 1)
            self.assertIn("不支持的 LLM 提供商", self.validator.errors[0].message)

    def test_validate_notification_config_dingtalk_enabled_no_url(self):
        """测试钉钉通知启用但未配置 URL"""
        with patch.dict(os.environ, {"DINGTALK_ENABLED": "1"}, clear=False):
            self.validator._validate_notification_config()

            # 应该有一个错误
            errors = [e for e in self.validator.errors if e.field == "DINGTALK_WEBHOOK_URL"]
            self.assertEqual(len(errors), 1)

    def test_validate_notification_config_dingtalk_success(self):
        """测试钉钉通知配置成功"""
        with patch.dict(os.environ, {
            "DINGTALK_ENABLED": "1",
            "DINGTALK_WEBHOOK_URL": "https://oapi.dingtalk.com/robot/send?access_token=xxx"
        }, clear=False):
            self.validator._validate_notification_config()

            # 不应该有钉钉相关的错误
            errors = [e for e in self.validator.errors if "DINGTALK" in e.field]
            self.assertEqual(len(errors), 0)

    def test_validate_git_platform_no_token_warning(self):
        """测试未配置任何 Git 平台 token 时发出警告"""
        with patch.dict(os.environ, {}, clear=True):
            self.validator._validate_git_platform_config()

            # 应该有一个警告
            warnings = [w for w in self.validator.warnings if w.field == "GIT_PLATFORM_TOKEN"]
            self.assertEqual(len(warnings), 1)

    def test_validate_gitea_config_missing_url(self):
        """测试 Gitea 配置了 token 但未配置 URL"""
        with patch.dict(os.environ, {"GITEA_ACCESS_TOKEN": "test-token"}, clear=False):
            self.validator._validate_git_platform_config()

            # 应该有一个错误
            errors = [e for e in self.validator.errors if e.field == "GITEA_URL"]
            self.assertEqual(len(errors), 1)

    def test_validate_dashboard_config_production_no_secret(self):
        """测试生产环境未配置 secret key"""
        with patch.dict(os.environ, {"APP_ENV": "production"}, clear=False):
            if "DASHBOARD_SECRET_KEY" in os.environ:
                del os.environ["DASHBOARD_SECRET_KEY"]

            self.validator._validate_dashboard_config()

            # 应该有一个错误
            errors = [e for e in self.validator.errors if e.field == "DASHBOARD_SECRET_KEY"]
            self.assertEqual(len(errors), 1)

    def test_validate_dashboard_config_default_password_warning(self):
        """测试使用默认密码时发出警告"""
        with patch.dict(os.environ, {"DASHBOARD_PASSWORD": "admin"}, clear=False):
            self.validator._validate_dashboard_config()

            # 应该有一个警告
            warnings = [w for w in self.validator.warnings if w.field == "DASHBOARD_PASSWORD"]
            self.assertGreaterEqual(len(warnings), 1)

    def test_is_valid_url(self):
        """测试 URL 验证方法"""
        # 有效的 URL
        self.assertTrue(self.validator._is_valid_url("https://example.com"))
        self.assertTrue(self.validator._is_valid_url("http://localhost:8080"))
        self.assertTrue(self.validator._is_valid_url("https://api.openai.com/v1"))

        # 无效的 URL
        self.assertFalse(self.validator._is_valid_url("not-a-url"))
        self.assertFalse(self.validator._is_valid_url(""))
        self.assertFalse(self.validator._is_valid_url("example.com"))  # 缺少 scheme


if __name__ == "__main__":
    unittest.main()
