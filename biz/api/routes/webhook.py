"""
Webhook 路由模块
"""

import json
import os
import time
from urllib.parse import urlparse
from flask import Blueprint, request, jsonify

from biz.platforms.gitlab.webhook_handler import slugify_url
from biz.queue.worker import (
    handle_merge_request_event,
    handle_push_event,
    handle_github_pull_request_event,
    handle_github_push_event,
    handle_gitea_pull_request_event,
    handle_gitea_push_event,
)
from biz.service.event_service import EventService
from biz.utils.log import logger
from biz.utils.queue import handle_queue

webhook_bp = Blueprint("webhook", __name__)


@webhook_bp.route("/review/webhook", methods=["POST"])
def handle_webhook():
    """
    处理 Webhook 请求的主路由
    """
    # 获取请求的JSON数据
    if request.is_json:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid JSON"}), 400
        # 判断webhook来源
        webhook_source_github = request.headers.get("X-GitHub-Event")
        webhook_source_gitea = request.headers.get("X-Gitea-Event")

        if webhook_source_gitea:  # Gitea webhook优先处理
            return handle_gitea_webhook(webhook_source_gitea, data)
        elif webhook_source_github:  # GitHub webhook
            return handle_github_webhook(webhook_source_github, data)
        else:  # GitLab webhook
            return handle_gitlab_webhook(data)
    else:
        return jsonify({"message": "Invalid data format"}), 400


def handle_github_webhook(event_type, data):
    """
    处理 GitHub Webhook
    """
    # 获取GitHub配置
    github_token = os.getenv("GITHUB_ACCESS_TOKEN") or request.headers.get(
        "X-GitHub-Token"
    )
    if not github_token:
        return jsonify({"message": "Missing GitHub access token"}), 400

    github_url = os.getenv("GITHUB_URL") or "https://github.com"
    github_url_slug = slugify_url(github_url)

    # 打印整个payload数据
    logger.info(f"Received GitHub event: {event_type}")
    logger.info(f"Payload: {json.dumps(data)}")

    if event_type == "pull_request":
        event_id = EventService.insert_event(
            review_type="mr",
            source="github",
            event_type=event_type,
            project_name=(data.get("repository") or {}).get("name", ""),
            project_url=(data.get("repository") or {}).get("html_url", ""),
            payload=data,
            created_at=int(time.time()),
        )
        # 使用handle_queue进行异步处理
        handle_queue(
            handle_github_pull_request_event,
            data,
            github_token,
            github_url,
            github_url_slug,
            event_id=event_id,
        )
        # 立马返回响应
        return jsonify(
            {
                "message": f"GitHub request received(event_type={event_type}), will process asynchronously."
            }
        ), 200
    elif event_type == "push":
        event_id = EventService.insert_event(
            review_type="push",
            source="github",
            event_type=event_type,
            project_name=(data.get("repository") or {}).get("name", ""),
            project_url=(data.get("repository") or {}).get("html_url", ""),
            payload=data,
            created_at=int(time.time()),
        )
        # 使用handle_queue进行异步处理
        handle_queue(
            handle_github_push_event,
            data,
            github_token,
            github_url,
            github_url_slug,
            event_id=event_id,
        )
        # 立马返回响应
        return jsonify(
            {
                "message": f"GitHub request received(event_type={event_type}), will process asynchronously."
            }
        ), 200
    else:
        error_message = f"Only pull_request and push events are supported for GitHub webhook, but received: {event_type}."
        logger.error(error_message)
        return jsonify(error_message), 400


def handle_gitlab_webhook(data):
    """
    处理 GitLab Webhook
    """
    object_kind = data.get("object_kind")

    # 优先从请求头获取，如果没有，则从环境变量获取，如果没有，则从推送事件中获取
    gitlab_url = os.getenv("GITLAB_URL") or request.headers.get("X-Gitlab-Instance")
    if not gitlab_url:
        repository = data.get("repository")
        if not repository:
            return jsonify({"message": "Missing GitLab URL"}), 400
        homepage = repository.get("homepage")
        if not homepage:
            return jsonify({"message": "Missing GitLab URL"}), 400
        try:
            parsed_url = urlparse(homepage)
            gitlab_url = f"{parsed_url.scheme}://{parsed_url.netloc}/"
        except Exception as e:
            return jsonify({"error": f"Failed to parse homepage URL: {str(e)}"}), 400

    # 优先从环境变量获取，如果没有，则从请求头获取
    gitlab_token = os.getenv("GITLAB_ACCESS_TOKEN") or request.headers.get(
        "X-Gitlab-Token"
    )
    # 如果gitlab_token为空，返回错误
    if not gitlab_token:
        return jsonify({"message": "Missing GitLab access token"}), 400

    gitlab_url_slug = slugify_url(gitlab_url)

    # 打印整个payload数据，或根据需求进行处理
    logger.info(f"Received event: {object_kind}")
    logger.info(f"Payload: {json.dumps(data)}")

    # 处理Merge Request Hook
    if object_kind == "merge_request":
        event_id = EventService.insert_event(
            review_type="mr",
            source="gitlab",
            event_type=object_kind,
            project_name=(data.get("project") or {}).get("name", ""),
            project_url=(data.get("project") or {}).get("web_url", ""),
            payload=data,
            created_at=int(time.time()),
        )
        # 创建一个新进程进行异步处理
        handle_queue(
            handle_merge_request_event,
            data,
            gitlab_token,
            gitlab_url,
            gitlab_url_slug,
            event_id=event_id,
        )
        # 立马返回响应
        return jsonify(
            {
                "message": f"Request received(object_kind={object_kind}), will process asynchronously."
            }
        ), 200
    elif object_kind == "push":
        event_id = EventService.insert_event(
            review_type="push",
            source="gitlab",
            event_type=object_kind,
            project_name=(data.get("project") or {}).get("name", ""),
            project_url=(data.get("project") or {}).get("web_url", ""),
            payload=data,
            created_at=int(time.time()),
        )
        # 创建一个新进程进行异步处理
        # TODO check if PUSH_REVIEW_ENABLED is needed here
        handle_queue(
            handle_push_event,
            data,
            gitlab_token,
            gitlab_url,
            gitlab_url_slug,
            event_id=event_id,
        )
        # 立马返回响应
        return jsonify(
            {
                "message": f"Request received(object_kind={object_kind}), will process asynchronously."
            }
        ), 200
    else:
        error_message = f"Only merge_request and push events are supported (both Webhook and System Hook), but received: {object_kind}."
        logger.error(error_message)
        return jsonify(error_message), 400


def handle_gitea_webhook(event_type, data):
    """
    处理 Gitea Webhook
    """
    gitea_token = os.getenv("GITEA_ACCESS_TOKEN") or request.headers.get(
        "X-Gitea-Token"
    )
    if not gitea_token:
        return jsonify({"message": "Missing Gitea access token"}), 400

    gitea_url = os.getenv("GITEA_URL") or "https://gitea.com"
    gitea_url_slug = slugify_url(gitea_url)

    logger.info(f"Received Gitea event: {event_type}")
    logger.info(f"Payload: {json.dumps(data)}")

    if event_type == "pull_request":
        event_id = EventService.insert_event(
            review_type="mr",
            source="gitea",
            event_type=event_type,
            project_name=(data.get("repository") or {}).get("name", ""),
            project_url=(data.get("repository") or {}).get("html_url", ""),
            payload=data,
            created_at=int(time.time()),
        )
        handle_queue(
            handle_gitea_pull_request_event,
            data,
            gitea_token,
            gitea_url,
            gitea_url_slug,
            event_id=event_id,
        )
        return jsonify(
            {
                "message": f"Gitea request received(event_type={event_type}), will process asynchronously."
            }
        ), 200
    elif event_type == "push":
        event_id = EventService.insert_event(
            review_type="push",
            source="gitea",
            event_type=event_type,
            project_name=(data.get("repository") or {}).get("name", ""),
            project_url=(data.get("repository") or {}).get("html_url", ""),
            payload=data,
            created_at=int(time.time()),
        )
        handle_queue(
            handle_gitea_push_event,
            data,
            gitea_token,
            gitea_url,
            gitea_url_slug,
            event_id=event_id,
        )
        return jsonify(
            {
                "message": f"Gitea request received(event_type={event_type}), will process asynchronously."
            }
        ), 200
    else:
        error_message = f"Only pull_request and push events are supported for Gitea webhook, but received: {event_type}."
        logger.error(error_message)
        return jsonify(error_message), 400


@webhook_bp.route("/review/retry", methods=["POST"])
def retry_review():
    """
    重新触发代码审查
    请求体: {"record_id": int, "review_type": "mr" | "push"}
    """
    from biz.api.retry import trigger_retry

    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid JSON"}), 400

        record_id = data.get("record_id")
        review_type = data.get("review_type")  # 'mr' 或 'push'

        if not record_id or not review_type:
            return jsonify({"error": "Missing record_id or review_type"}), 400

        payload, status = trigger_retry(record_id=record_id, review_type=review_type)
        return jsonify(payload), status

    except Exception as e:
        logger.error(f"Error retrying review: {e}")
        return jsonify({"error": str(e)}), 500
