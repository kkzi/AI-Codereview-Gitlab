from __future__ import annotations

import os
from typing import Any, Dict

from app.core.logging import get_logger
from app.core.performance import get_monitor
from app.infra.notify.dingtalk import DingTalkNotifier
from app.infra.notify.feishu import FeishuNotifier
from app.infra.notify.webhook import ExtraWebhookNotifier
from app.infra.notify.wecom import WeComNotifier


logger = get_logger(__name__)
monitor = get_monitor()


def send_notification(
    content: str,
    msg_type: str = "text",
    title: str = "通知",
    is_at_all: bool = False,
    project_name: str | None = None,
    url_slug: str | None = None,
    webhook_data: Dict[str, Any] | None = None,
) -> Dict[str, bool]:
    """
    发送通知到所有配置的渠道

    每个通知渠道独立处理，一个失败不影响其他渠道

    Returns:
        Dict[str, bool]: 各渠道的发送结果 {"dingtalk": True, "wecom": False, ...}
    """
    webhook_data = webhook_data or {}
    results = {}

    # DingTalk 通知
    try:
        with monitor.measure("notification_send", {"channel": "dingtalk"}):
            dingtalk = DingTalkNotifier()
            dingtalk.send_message(
                content=content,
                msg_type=msg_type,
                title=title,
                is_at_all=is_at_all,
                project_name=project_name,
                url_slug=url_slug,
            )
        results["dingtalk"] = True
        logger.debug("DingTalk notification sent successfully")
    except Exception as exc:
        results["dingtalk"] = False
        logger.error("DingTalk notification failed: %s", exc, exc_info=True)

    # 企业微信通知
    try:
        with monitor.measure("notification_send", {"channel": "wecom"}):
            wecom = WeComNotifier()
            wecom.send_message(
                content=content,
                msg_type=msg_type,
                title=title,
                is_at_all=is_at_all,
                project_name=project_name,
                url_slug=url_slug,
            )
        results["wecom"] = True
        logger.debug("WeChat Work notification sent successfully")
    except Exception as exc:
        results["wecom"] = False
        logger.error("WeChat Work notification failed: %s", exc, exc_info=True)

    # 飞书通知
    try:
        with monitor.measure("notification_send", {"channel": "feishu"}):
            feishu = FeishuNotifier()
            feishu.send_message(
                content=content,
                msg_type=msg_type,
                title=title,
                is_at_all=is_at_all,
                project_name=project_name,
                url_slug=url_slug,
            )
        results["feishu"] = True
        logger.debug("Feishu notification sent successfully")
    except Exception as exc:
        results["feishu"] = False
        logger.error("Feishu notification failed: %s", exc, exc_info=True)

    # 自定义 Webhook 通知
    extra_enabled = os.getenv("EXTRA_WEBHOOK_ENABLED", "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if not extra_enabled:
        results["extra_webhook"] = True
        logger.info("Extra webhook disabled, skipping")
    else:
        try:
            with monitor.measure("notification_send", {"channel": "extra_webhook"}):
                extra = ExtraWebhookNotifier()
                system_data = {
                    "content": content,
                    "msg_type": msg_type,
                    "title": title,
                    "is_at_all": is_at_all,
                    "project_name": project_name,
                    "url_slug": url_slug,
                }
                extra.send_message(system_data=system_data, webhook_data=webhook_data)
            results["extra_webhook"] = True
            logger.debug("Extra webhook notification sent successfully")
        except Exception as exc:
            results["extra_webhook"] = False
            logger.error("Extra webhook notification failed: %s", exc, exc_info=True)

    # 统计发送结果
    success_count = sum(1 for v in results.values() if v)
    total_count = len(results)
    if success_count < total_count:
        logger.warning(
            "Notification partially failed: %d/%d succeeded",
            success_count,
            total_count,
        )

    return results
