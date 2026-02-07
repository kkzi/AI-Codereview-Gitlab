from __future__ import annotations

import os
from flask import Blueprint, jsonify, request

from app.api.webhook_security import (
    verify_gitlab_signature,
    verify_github_signature,
    verify_gitea_signature,
)
from app.core.config import load_config
from app.core.logging import get_logger
from app.infra.db.sqlite import SQLiteRepository
from app.infra.queue.db_queue import DbQueue
from app.usecases.review import ReviewUseCase
from app.usecases.retry import RetryUseCase


webhook_bp = Blueprint("webhook", __name__)
logger = get_logger(__name__)


@webhook_bp.route("/review/webhook", methods=["POST"])
def handle_webhook():
    if not request.is_json:
        return jsonify({"error": "Invalid data format"}), 400

    payload = request.get_json(silent=True)
    if not payload:
        return jsonify({"error": "Invalid JSON"}), 400

    # 验证 webhook 签名
    headers = dict(request.headers)
    if not _verify_webhook_signature(request.data, headers):
        logger.warning("Webhook signature verification failed from IP: %s", request.remote_addr)
        return jsonify({"error": "Invalid webhook signature"}), 401

    config = load_config()
    repo = SQLiteRepository(config.db_file)
    repo.init_db()
    queue = DbQueue(config.db_file)
    queue.init_db()
    usecase = ReviewUseCase(repo=repo, queue=queue, config=config)

    response, status = usecase.handle_webhook(payload, headers)
    return jsonify(response), status


def _verify_webhook_signature(payload: bytes, headers: dict) -> bool:
    """
    验证 webhook 签名

    根据不同平台的 header 判断平台类型并验证签名
    """
    # GitHub webhook
    if headers.get("X-GitHub-Event"):
        github_signature = headers.get("X-Hub-Signature-256")
        github_secret = os.getenv("GITHUB_WEBHOOK_SECRET", "")

        if github_secret:
            # 如果配置了 secret，必须验证签名
            if not github_signature:
                logger.warning("GitHub webhook missing signature header")
                return False
            return verify_github_signature(payload, github_signature, github_secret)
        else:
            # 未配置 secret，跳过验证（向后兼容）
            logger.debug("GitHub webhook signature verification skipped (no secret configured)")
            return True

    # Gitea webhook
    if headers.get("X-Gitea-Event"):
        gitea_signature = headers.get("X-Gitea-Signature")
        gitea_secret = os.getenv("GITEA_WEBHOOK_SECRET", "")

        if gitea_secret:
            if not gitea_signature:
                logger.warning("Gitea webhook missing signature header")
                return False
            return verify_gitea_signature(payload, gitea_signature, gitea_secret)
        else:
            logger.debug("Gitea webhook signature verification skipped (no secret configured)")
            return True

    # GitLab webhook (默认)
    gitlab_token = headers.get("X-Gitlab-Token")
    gitlab_secret = os.getenv("GITLAB_WEBHOOK_SECRET", "")

    if gitlab_secret:
        if not gitlab_token:
            logger.warning("GitLab webhook missing token header")
            return False
        return verify_gitlab_signature(payload, gitlab_token, gitlab_secret)
    else:
        logger.debug("GitLab webhook signature verification skipped (no secret configured)")
        return True


@webhook_bp.route("/review/retry", methods=["POST"])
def retry_review():
    data = request.get_json(silent=True) if request.is_json else request.form
    record_id = (data or {}).get("record_id") if data is not None else None
    review_type = (data or {}).get("review_type") if data is not None else None
    if not review_type:
        review_type = (data or {}).get("type") if data is not None else None

    try:
        record_id = int(record_id)
    except Exception:
        return jsonify({"error": "Invalid record_id"}), 400

    review_type = (review_type or "mr").strip().lower()
    if review_type not in {"mr", "push"}:
        return jsonify({"error": "Invalid review_type, must be 'mr' or 'push'"}), 400

    config = load_config()
    repo = SQLiteRepository(config.db_file)
    repo.init_db()
    queue = DbQueue(config.db_file)
    queue.init_db()
    usecase = RetryUseCase(repo=repo, queue=queue)

    payload, status = usecase.trigger_retry(record_id, review_type)
    return jsonify(payload), status
