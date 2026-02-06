from __future__ import annotations

import json
import os
import requests

from app.core.logging import get_logger


logger = get_logger(__name__)


class WeComNotifier:
    def __init__(self, webhook_url: str | None = None) -> None:
        self.enabled = os.environ.get("WECOM_ENABLED", "0") == "1"
        self.default_webhook_url = webhook_url or os.environ.get("WECOM_WEBHOOK_URL", "")

    def _get_webhook_url(self, project_name: str | None = None, url_slug: str | None = None) -> str:
        if not project_name:
            if self.default_webhook_url:
                return self.default_webhook_url
            raise ValueError("未提供项目名称，且未设置默认的企业微信 Webhook URL。")

        target_key_project = f"WECOM_WEBHOOK_URL_{project_name.upper()}" if project_name else None
        target_key_url_slug = f"WECOM_WEBHOOK_URL_{url_slug.upper()}" if url_slug else None

        for env_key, env_value in os.environ.items():
            env_key_upper = env_key.upper()
            if target_key_project and env_key_upper == target_key_project:
                return env_value
            if target_key_url_slug and env_key_upper == target_key_url_slug:
                return env_value

        if self.default_webhook_url:
            return self.default_webhook_url

        raise ValueError(f"未找到项目 '{project_name}' 对应的企业微信Webhook URL，且未设置默认的 Webhook URL。")

    def format_markdown_content(self, content: str, title: str | None = None) -> str:
        if not title:
            return content
        return f"# {title}\n\n{content}"

    def send_message(
        self,
        content: str,
        msg_type: str = "text",
        title: str | None = None,
        is_at_all: bool = False,
        project_name: str | None = None,
        url_slug: str | None = None,
    ) -> None:
        if not self.enabled:
            logger.info("企业微信推送未启用")
            return

        try:
            post_url = self._get_webhook_url(project_name=project_name, url_slug=url_slug)
            if msg_type == "markdown":
                content = self.format_markdown_content(content, title=title)
                data = self._build_markdown_message(content)
            else:
                data = self._build_text_message(content, is_at_all)

            self._send_request(post_url, data)
        except Exception:
            logger.exception("企业微信消息发送失败")

    def _send_request(self, url: str, data: dict) -> None:
        headers = {"Content-Type": "application/json"}
        response = requests.post(url, data=json.dumps(data), headers=headers)
        result = response.json()
        if result.get("errmsg") == "ok":
            logger.info("企业微信消息发送成功")
        else:
            logger.error("企业微信消息发送失败: %s", result)

    def _build_text_message(self, content: str, is_at_all: bool) -> dict:
        return {
            "msgtype": "text",
            "text": {"content": content, "mentioned_list": ["@all"] if is_at_all else []},
        }

    def _build_markdown_message(self, content: str) -> dict:
        return {"msgtype": "markdown", "markdown": {"content": content}}
