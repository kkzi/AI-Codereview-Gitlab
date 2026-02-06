from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.core.config import load_config
from app.infra.db.sqlite import SQLiteRepository
from app.infra.queue.db_queue import DbQueue
from app.usecases.review import ReviewUseCase
from app.usecases.retry import RetryUseCase


webhook_bp = Blueprint("webhook", __name__)


@webhook_bp.route("/review/webhook", methods=["POST"])
def handle_webhook():
    if not request.is_json:
        return jsonify({"error": "Invalid data format"}), 400

    payload = request.get_json(silent=True)
    if not payload:
        return jsonify({"error": "Invalid JSON"}), 400

    config = load_config()
    repo = SQLiteRepository(config.db_file)
    repo.init_db()
    queue = DbQueue(config.db_file)
    queue.init_db()
    usecase = ReviewUseCase(repo=repo, queue=queue, config=config)

    response, status = usecase.handle_webhook(payload, dict(request.headers))
    return jsonify(response), status


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
