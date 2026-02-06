from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
import urllib.parse

import requests

from app.core.logging import get_logger


logger = get_logger(__name__)


class DingTalkNotifier:
    def __init__(self, webhook_url: str | None = None) -> None:
        self.enabled = os.environ.get("DINGTALK_ENABLED", "0") == "1"
        self.default_webhook_url = webhook_url or os.environ.get("DINGTALK_WEBHOOK_URL")
        self.secret = os.environ.get("DINGTALK_WEBHOOK_SECRET")

    def _get_sign(self) -> tuple[str | None, str | None]:
        if not self.secret:
            return None, None
        timestamp = str(round(time.time() * 1000))
        string_to_sign = f"{timestamp}\n{self.secret}".encode("utf-8")
        secret_enc = self.secret.encode("utf-8")
        hmac_code = hmac.new(secret_enc, string_to_sign, digestmod=hashlib.sha256).digest()
        sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
        return timestamp, sign

    def _get_webhook_url(self, project_name: str | None = None, url_slug: str | None = None) -> str:
        if not project_name:
            if self.default_webhook_url:
                return self.default_webhook_url
            raise ValueError("未提供项目名称，且未设置默认的钉钉 Webhook URL。")

        target_key_project = f"DINGTALK_WEBHOOK_URL_{project_name.upper()}" if project_name else None
        target_key_url_slug = f"DINGTALK_WEBHOOK_URL_{url_slug.upper()}" if url_slug else None

        for env_key, env_value in os.environ.items():
            env_key_upper = env_key.upper()
            if target_key_project and env_key_upper == target_key_project:
                return env_value
            if target_key_url_slug and env_key_upper == target_key_url_slug:
                return env_value

        if self.default_webhook_url:
            return self.default_webhook_url

        raise ValueError(f"未找到项目 '{project_name}' 对应的钉钉Webhook URL，且未设置默认的 Webhook URL。")

    def send_message(
        self,
        content: str,
        msg_type: str = "text",
        title: str = "通知",
        is_at_all: bool = False,
        project_name: str | None = None,
        url_slug: str | None = None,
    ) -> None:
        if not self.enabled:
            logger.info("钉钉推送未启用")
            return

        try:
            post_url = self._get_webhook_url(project_name=project_name, url_slug=url_slug)
            if self.secret:
                timestamp, sign = self._get_sign()
                separator = "&" if "?" in post_url else "?"
                post_url = f"{post_url}{separator}timestamp={timestamp}&sign={sign}"

            headers = {"Content-Type": "application/json", "Charset": "UTF-8"}
            if msg_type == "markdown":
                message = {
                    "msgtype": "markdown",
                    "markdown": {"title": title, "text": content},
                    "at": {"isAtAll": is_at_all},
                }
            else:
                message = {
                    "msgtype": "text",
                    "text": {"content": content},
                    "at": {"isAtAll": is_at_all},
                }

            response = requests.post(url=post_url, data=json.dumps(message), headers=headers)
            response_data = response.json()
            if response_data.get("errmsg") == "ok":
                logger.info("钉钉消息发送成功")
            else:
                logger.error("钉钉消息发送失败: %s", response_data.get("errmsg"))
        except Exception:
            logger.exception("钉钉消息发送失败")
