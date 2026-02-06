from __future__ import annotations

from typing import Any, Dict

from app.infra.notify.dingtalk import DingTalkNotifier
from app.infra.notify.feishu import FeishuNotifier
from app.infra.notify.webhook import ExtraWebhookNotifier
from app.infra.notify.wecom import WeComNotifier


def send_notification(
    content: str,
    msg_type: str = "text",
    title: str = "通知",
    is_at_all: bool = False,
    project_name: str | None = None,
    url_slug: str | None = None,
    webhook_data: Dict[str, Any] | None = None,
) -> None:
    webhook_data = webhook_data or {}

    dingtalk = DingTalkNotifier()
    dingtalk.send_message(
        content=content,
        msg_type=msg_type,
        title=title,
        is_at_all=is_at_all,
        project_name=project_name,
        url_slug=url_slug,
    )

    wecom = WeComNotifier()
    wecom.send_message(
        content=content,
        msg_type=msg_type,
        title=title,
        is_at_all=is_at_all,
        project_name=project_name,
        url_slug=url_slug,
    )

    feishu = FeishuNotifier()
    feishu.send_message(
        content=content,
        msg_type=msg_type,
        title=title,
        is_at_all=is_at_all,
        project_name=project_name,
        url_slug=url_slug,
    )

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
