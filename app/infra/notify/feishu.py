from __future__ import annotations

import json
import os

import requests

from app.core.logging import get_logger


logger = get_logger(__name__)


class FeishuNotifier:
    def __init__(self, webhook_url: str | None = None) -> None:
        self.enabled = os.environ.get("FEISHU_ENABLED", "0") == "1"
        self.default_webhook_url = webhook_url or os.environ.get("FEISHU_WEBHOOK_URL", "")

    def _get_webhook_url(self, project_name: str | None = None, url_slug: str | None = None) -> str:
        if not project_name:
            if self.default_webhook_url:
                return self.default_webhook_url
            raise ValueError("未提供项目名称，且未设置默认的飞书 Webhook URL。")

        target_key_project = f"FEISHU_WEBHOOK_URL_{project_name.upper()}" if project_name else None
        target_key_url_slug = f"FEISHU_WEBHOOK_URL_{url_slug.upper()}" if url_slug else None

        for env_key, env_value in os.environ.items():
            env_key_upper = env_key.upper()
            if target_key_project and env_key_upper == target_key_project:
                return env_value
            if target_key_url_slug and env_key_upper == target_key_url_slug:
                return env_value

        if self.default_webhook_url:
            return self.default_webhook_url

        raise ValueError(f"未找到项目 '{project_name}' 对应的飞书Webhook URL，且未设置默认的 Webhook URL。")

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
            logger.info("飞书推送未启用")
            return

        try:
            post_url = self._get_webhook_url(project_name=project_name, url_slug=url_slug)
            if msg_type == "markdown":
                message = {
                    "msg_type": "post",
                    "content": {
                        "post": {
                            "zh_cn": {
                                "title": title or "通知",
                                "content": [[{"tag": "text", "text": content}]],
                            }
                        }
                    },
                }
            else:
                message = {
                    "msg_type": "text",
                    "content": {"text": content},
                }

            response = requests.post(url=post_url, data=json.dumps(message))
            result = response.json()
            if result.get("StatusCode") == 0:
                logger.info("飞书消息发送成功")
            else:
                logger.error("飞书消息发送失败: %s", result)
        except Exception:
            logger.exception("飞书消息发送失败")
