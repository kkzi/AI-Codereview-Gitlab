from __future__ import annotations

import json
import os

import requests

from app.core.logging import get_logger


logger = get_logger(__name__)


class ExtraWebhookNotifier:
    def __init__(self, webhook_url: str | None = None) -> None:
        self.default_webhook_url = webhook_url or os.environ.get("EXTRA_WEBHOOK_URL", "")

    def send_message(self, system_data: dict, webhook_data: dict) -> None:
        if not self.default_webhook_url:
            return

        try:
            data = {"ai_codereview_data": system_data, "webhook_data": webhook_data}
            response = requests.post(
                url=self.default_webhook_url,
                data=json.dumps(data, ensure_ascii=False),
                headers={"Content-Type": "application/json"},
            )
            if response.status_code != 200:
                logger.error("ExtraWebhook消息发送失败: %s", response.text)
            else:
                logger.info("ExtraWebhook消息发送成功")
        except Exception:
            logger.exception("ExtraWebhook消息发送失败")
