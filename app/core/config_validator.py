"""配置验证模块

在系统启动时验证所有必需的配置项，提供清晰的错误提示。
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List, Optional
from urllib.parse import urlparse

from app.core.logging import get_logger
from app.infra.llm.config import get_llm_profiles, get_llm_value

logger = get_logger(__name__)


@dataclass
class ValidationError:
    """配置验证错误"""
    field: str
    message: str
    severity: str  # "error" or "warning"


class ConfigValidator:
    """配置验证器"""

    def __init__(self):
        self.errors: List[ValidationError] = []
        self.warnings: List[ValidationError] = []

    def validate_all(self) -> bool:
        """验证所有配置项

        Returns:
            bool: 如果所有必需配置都有效则返回 True
        """
        self._validate_llm_config()
        self._validate_git_platform_config()
        self._validate_notification_config()
        self._validate_database_config()
        self._validate_dashboard_config()

        # 输出验证结果
        if self.warnings:
            logger.warning("配置验证警告:")
            for warning in self.warnings:
                logger.warning(f"  - {warning.field}: {warning.message}")

        if self.errors:
            logger.error("配置验证失败:")
            for error in self.errors:
                logger.error(f"  - {error.field}: {error.message}")
            return False

        logger.info("✓ 配置验证通过")
        return True

    def _validate_llm_config(self):
        """验证 LLM 配置"""
        profiles = get_llm_profiles()
        if profiles:
            self._validate_llm_profiles(profiles)
            return
        self.errors.append(ValidationError(
            field="llm_profiles",
            message="未配置 LLM Profiles。请在 conf/llm.yml 中设置 llm_profiles",
            severity="error"
        ))

    def _validate_llm_profiles(self, profiles):
        """验证 LLM 多配置列表"""
        if not profiles:
            self.errors.append(ValidationError(
                field="llm_profiles",
                message="未配置 LLM Profiles 列表",
                severity="error"
            ))
            return

        supported = {"chat", "responses", "deepseek", "anthropic", "zhipuai", "qwen", "ollama"}
        for idx, profile in enumerate(profiles):
            name = profile.get("name") or f"profile_{idx + 1}"
            provider = str(profile.get("type") or "").strip().lower()
            if not provider:
                self.errors.append(ValidationError(
                    field=f"llm_profiles[{idx}].type",
                    message=f"{name} 未配置 type",
                    severity="error"
                ))
                continue
            if provider not in supported:
                self.errors.append(ValidationError(
                    field=f"llm_profiles[{idx}].type",
                    message=f"{name} 不支持的 LLM 提供商: {provider}",
                    severity="error"
                ))
                continue

            base_url = profile.get("base_url")
            if base_url and not self._is_valid_url(base_url):
                self.errors.append(ValidationError(
                    field=f"llm_profiles[{idx}].base_url",
                    message=f"{name} 无效的 URL: {base_url}",
                    severity="error"
                ))

            if provider == "ollama":
                if not base_url:
                    self.errors.append(ValidationError(
                        field=f"llm_profiles[{idx}].base_url",
                        message=f"{name} 未配置 Ollama API Base URL",
                        severity="error"
                    ))
            else:
                if not profile.get("key"):
                    self.errors.append(ValidationError(
                        field=f"llm_profiles[{idx}].key",
                        message=f"{name} 未配置 API Key",
                        severity="error"
                    ))

            if not profile.get("model"):
                self.errors.append(ValidationError(
                    field=f"llm_profiles[{idx}].model",
                    message=f"{name} 未配置模型名称",
                    severity="error"
                ))

    def _validate_openai_config(self):
        """验证 OpenAI 配置"""
        api_key = get_llm_value("OPENAI_API_KEY")
        api_base = get_llm_value("OPENAI_API_BASE_URL")
        model = get_llm_value("OPENAI_API_MODEL")

        if not api_key:
            self.errors.append(ValidationError(
                field="OPENAI_API_KEY",
                message="未配置 OpenAI API Key",
                severity="error"
            ))

        if not api_base:
            self.warnings.append(ValidationError(
                field="OPENAI_API_BASE_URL",
                message="未配置 OpenAI API Base URL，将使用默认值",
                severity="warning"
            ))
        elif not self._is_valid_url(api_base):
            self.errors.append(ValidationError(
                field="OPENAI_API_BASE_URL",
                message=f"无效的 URL: {api_base}",
                severity="error"
            ))

        if not model:
            self.errors.append(ValidationError(
                field="OPENAI_API_MODEL",
                message="未配置 OpenAI 模型名称",
                severity="error"
            ))

    def _validate_deepseek_config(self):
        """验证 DeepSeek 配置"""
        api_key = get_llm_value("DEEPSEEK_API_KEY")
        api_base = get_llm_value("DEEPSEEK_API_BASE_URL")
        model = get_llm_value("DEEPSEEK_API_MODEL")

        if not api_key:
            self.errors.append(ValidationError(
                field="DEEPSEEK_API_KEY",
                message="未配置 DeepSeek API Key",
                severity="error"
            ))

        if not api_base:
            self.warnings.append(ValidationError(
                field="DEEPSEEK_API_BASE_URL",
                message="未配置 DeepSeek API Base URL，将使用默认值",
                severity="warning"
            ))

        if not model:
            self.errors.append(ValidationError(
                field="DEEPSEEK_API_MODEL",
                message="未配置 DeepSeek 模型名称",
                severity="error"
            ))

    def _validate_anthropic_config(self):
        """验证 Anthropic 配置"""
        api_key = get_llm_value("ANTHROPIC_API_KEY")
        api_base = get_llm_value("ANTHROPIC_API_BASE_URL")
        model = get_llm_value("ANTHROPIC_API_MODEL")

        if not api_key:
            self.errors.append(ValidationError(
                field="ANTHROPIC_API_KEY",
                message="未配置 Anthropic API Key",
                severity="error"
            ))

        if api_base and not self._is_valid_url(api_base):
            self.errors.append(ValidationError(
                field="ANTHROPIC_API_BASE_URL",
                message=f"无效的 URL: {api_base}",
                severity="error"
            ))

        if not model:
            self.errors.append(ValidationError(
                field="ANTHROPIC_API_MODEL",
                message="未配置 Anthropic 模型名称",
                severity="error"
            ))

    def _validate_zhipuai_config(self):
        """验证智谱 AI 配置"""
        api_key = get_llm_value("ZHIPUAI_API_KEY")
        model = get_llm_value("ZHIPUAI_API_MODEL")

        if not api_key:
            self.errors.append(ValidationError(
                field="ZHIPUAI_API_KEY",
                message="未配置智谱 AI API Key",
                severity="error"
            ))

        if not model:
            self.errors.append(ValidationError(
                field="ZHIPUAI_API_MODEL",
                message="未配置智谱 AI 模型名称",
                severity="error"
            ))

    def _validate_qwen_config(self):
        """验证通义千问配置"""
        api_key = get_llm_value("QWEN_API_KEY")
        api_base = get_llm_value("QWEN_API_BASE_URL")
        model = get_llm_value("QWEN_API_MODEL")

        if not api_key:
            self.errors.append(ValidationError(
                field="QWEN_API_KEY",
                message="未配置通义千问 API Key",
                severity="error"
            ))

        if not api_base:
            self.warnings.append(ValidationError(
                field="QWEN_API_BASE_URL",
                message="未配置通义千问 API Base URL，将使用默认值",
                severity="warning"
            ))

        if not model:
            self.errors.append(ValidationError(
                field="QWEN_API_MODEL",
                message="未配置通义千问模型名称",
                severity="error"
            ))

    def _validate_ollama_config(self):
        """验证 Ollama 配置"""
        api_base = get_llm_value("OLLAMA_API_BASE_URL")
        model = get_llm_value("OLLAMA_API_MODEL")

        if not api_base:
            self.errors.append(ValidationError(
                field="OLLAMA_API_BASE_URL",
                message="未配置 Ollama API Base URL",
                severity="error"
            ))
        elif not self._is_valid_url(api_base):
            self.errors.append(ValidationError(
                field="OLLAMA_API_BASE_URL",
                message=f"无效的 URL: {api_base}",
                severity="error"
            ))

        if not model:
            self.errors.append(ValidationError(
                field="OLLAMA_API_MODEL",
                message="未配置 Ollama 模型名称",
                severity="error"
            ))

    def _validate_git_platform_config(self):
        """验证 Git 平台配置"""
        # 至少需要配置一个平台的 token
        gitlab_token = os.getenv("GITLAB_ACCESS_TOKEN")
        github_token = os.getenv("GITHUB_ACCESS_TOKEN")
        gitea_token = os.getenv("GITEA_ACCESS_TOKEN")

        if not any([gitlab_token, github_token, gitea_token]):
            self.warnings.append(ValidationError(
                field="GIT_PLATFORM_TOKEN",
                message="未配置任何 Git 平台的 Access Token。请至少配置 GITLAB_ACCESS_TOKEN、GITHUB_ACCESS_TOKEN 或 GITEA_ACCESS_TOKEN 之一",
                severity="warning"
            ))

        # 验证 Gitea URL（如果配置了 token）
        if gitea_token:
            gitea_url = os.getenv("GITEA_URL")
            if not gitea_url:
                self.errors.append(ValidationError(
                    field="GITEA_URL",
                    message="配置了 GITEA_ACCESS_TOKEN 但未配置 GITEA_URL",
                    severity="error"
                ))
            elif not self._is_valid_url(gitea_url):
                self.errors.append(ValidationError(
                    field="GITEA_URL",
                    message=f"无效的 URL: {gitea_url}",
                    severity="error"
                ))

    def _validate_notification_config(self):
        """验证通知配置"""
        # 钉钉配置
        dingtalk_enabled = os.getenv("DINGTALK_ENABLED", "0") == "1"
        if dingtalk_enabled:
            webhook_url = os.getenv("DINGTALK_WEBHOOK_URL")
            if not webhook_url:
                self.errors.append(ValidationError(
                    field="DINGTALK_WEBHOOK_URL",
                    message="启用了钉钉通知但未配置 DINGTALK_WEBHOOK_URL",
                    severity="error"
                ))
            elif not self._is_valid_url(webhook_url):
                self.errors.append(ValidationError(
                    field="DINGTALK_WEBHOOK_URL",
                    message=f"无效的 URL: {webhook_url}",
                    severity="error"
                ))

        # 企业微信配置
        wecom_enabled = os.getenv("WECOM_ENABLED", "0") == "1"
        if wecom_enabled:
            webhook_url = os.getenv("WECOM_WEBHOOK_URL")
            if not webhook_url:
                self.errors.append(ValidationError(
                    field="WECOM_WEBHOOK_URL",
                    message="启用了企业微信通知但未配置 WECOM_WEBHOOK_URL",
                    severity="error"
                ))
            elif not self._is_valid_url(webhook_url):
                self.errors.append(ValidationError(
                    field="WECOM_WEBHOOK_URL",
                    message=f"无效的 URL: {webhook_url}",
                    severity="error"
                ))

        # 飞书配置
        feishu_enabled = os.getenv("FEISHU_ENABLED", "0") == "1"
        if feishu_enabled:
            webhook_url = os.getenv("FEISHU_WEBHOOK_URL")
            if not webhook_url:
                self.errors.append(ValidationError(
                    field="FEISHU_WEBHOOK_URL",
                    message="启用了飞书通知但未配置 FEISHU_WEBHOOK_URL",
                    severity="error"
                ))
            elif not self._is_valid_url(webhook_url):
                self.errors.append(ValidationError(
                    field="FEISHU_WEBHOOK_URL",
                    message=f"无效的 URL: {webhook_url}",
                    severity="error"
                ))

        # 自定义 webhook 配置
        extra_webhook_enabled = os.getenv("EXTRA_WEBHOOK_ENABLED", "0") == "1"
        if extra_webhook_enabled:
            webhook_url = os.getenv("EXTRA_WEBHOOK_URL")
            if not webhook_url:
                self.errors.append(ValidationError(
                    field="EXTRA_WEBHOOK_URL",
                    message="启用了自定义 webhook 但未配置 EXTRA_WEBHOOK_URL",
                    severity="error"
                ))
            elif not self._is_valid_url(webhook_url):
                self.errors.append(ValidationError(
                    field="EXTRA_WEBHOOK_URL",
                    message=f"无效的 URL: {webhook_url}",
                    severity="error"
                ))

    def _validate_database_config(self):
        """验证数据库配置"""
        db_file = os.getenv("DB_FILE", "data/data.db")

        # 检查数据库目录是否存在
        db_dir = os.path.dirname(db_file)
        if db_dir and not os.path.exists(db_dir):
            self.warnings.append(ValidationError(
                field="DB_FILE",
                message=f"数据库目录不存在: {db_dir}，将在首次运行时创建",
                severity="warning"
            ))

    def _validate_dashboard_config(self):
        """验证 Dashboard 配置"""
        env = os.getenv("APP_ENV", "development")
        secret_key = os.getenv("DASHBOARD_SECRET_KEY")

        if env == "production" and not secret_key:
            self.errors.append(ValidationError(
                field="DASHBOARD_SECRET_KEY",
                message="生产环境必须配置 DASHBOARD_SECRET_KEY。生成方法: python -c 'import secrets; print(secrets.token_hex(32))'",
                severity="error"
            ))

        # 验证用户名和密码
        username = os.getenv("DASHBOARD_USER")
        password = os.getenv("DASHBOARD_PASSWORD")

        if not username:
            self.warnings.append(ValidationError(
                field="DASHBOARD_USER",
                message="未配置 Dashboard 用户名，将使用默认值 'admin'",
                severity="warning"
            ))

        if not password:
            self.warnings.append(ValidationError(
                field="DASHBOARD_PASSWORD",
                message="未配置 Dashboard 密码，将使用默认值 'admin'",
                severity="warning"
            ))
        elif password == "admin":
            self.warnings.append(ValidationError(
                field="DASHBOARD_PASSWORD",
                message="Dashboard 密码使用默认值 'admin'，建议在生产环境中修改",
                severity="warning"
            ))

    def _is_valid_url(self, url: str) -> bool:
        """验证 URL 格式"""
        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except Exception:
            return False


def validate_config() -> bool:
    """验证配置并返回结果

    Returns:
        bool: 配置是否有效
    """
    validator = ConfigValidator()
    return validator.validate_all()
