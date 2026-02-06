from __future__ import annotations

import datetime
from flask import Blueprint, Response, jsonify, redirect, render_template, request, session

from app.api.auth import (
    DASHBOARD_PASSWORD,
    DASHBOARD_USER,
    authenticate,
    is_rate_limited,
    login_required,
    register_failed_login,
)
from app.core.config import load_config
from app.core.llm_status import get_llm_status, set_llm_status
from app.infra.db.sqlite import SQLiteRepository
from app.infra.queue.db_queue import DbQueue
from app.infra.llm.factory import get_client, get_model_name
from app.usecases.dashboard import fetch_reviews, parse_query_args, serialize_records, format_delta, format_timestamp
from app.usecases.retry import RetryUseCase


dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/dashboard")
@login_required
def dashboard_page():
    config = load_config()
    return render_template(
        "dashboard.html",
        push_enabled=config.push_review_enabled,
        llm_model_name=get_model_name() or "unknown",
    )


@dashboard_bp.route("/dashboard/login", methods=["GET", "POST"])
def login_page():
    error = None
    if request.method == "POST":
        if is_rate_limited():
            error = "登录失败次数过多，请稍后再试"
            return render_template(
                "login.html",
                error=error,
                DASHBOARD_USER=DASHBOARD_USER,
                DASHBOARD_PASSWORD=DASHBOARD_PASSWORD,
            )

        username = request.form.get("username", "")
        password = request.form.get("password", "")
        if authenticate(username, password):
            session["logged_in"] = True
            session["username"] = username
            return redirect("/dashboard")
        remaining = register_failed_login()
        error = (
            f"用户名或密码错误（剩余尝试次数：{remaining}）" if remaining else "用户名或密码错误"
        )

    return render_template(
        "login.html",
        error=error,
        DASHBOARD_USER=DASHBOARD_USER,
        DASHBOARD_PASSWORD=DASHBOARD_PASSWORD,
    )


@dashboard_bp.route("/dashboard/logout")
def logout_page():
    session.clear()
    return redirect("/dashboard/login")


@dashboard_bp.route("/dashboard/api/llm/check", methods=["POST"])
@login_required
def api_llm_check():
    try:
        client = get_client()
        available = bool(client.ping())
    except Exception:
        available = False

    checked_at = int(datetime.datetime.now().timestamp())
    set_llm_status(available, checked_at)
    return jsonify(
        {
            "available": available,
            "checked_at": checked_at,
            "model_name": get_model_name() or "unknown",
        }
    )


@dashboard_bp.route("/dashboard/api/llm/status", methods=["GET"])
@login_required
def api_llm_status():
    status = get_llm_status()
    return jsonify(
        {
            "available": status.get("available"),
            "checked_at": status.get("checked_at"),
            "model_name": get_model_name() or "unknown",
        }
    )


@dashboard_bp.route("/dashboard/api/reviews")
@login_required
def api_reviews():
    config = load_config()
    repo = SQLiteRepository(config.db_file)
    repo.init_db()
    params = parse_query_args(request.args)
    records, filters, stats, pagination = fetch_reviews(repo, params)
    return jsonify(
        {
            "data": records,
            "filters": filters,
            "stats": stats,
            "pagination": pagination,
        }
    )


@dashboard_bp.route("/dashboard/api/data")
@login_required
def api_data_compat():
    config = load_config()
    repo = SQLiteRepository(config.db_file)
    repo.init_db()
    params = parse_query_args(request.args)
    records, filters, stats, _pagination = fetch_reviews(repo, params)
    return jsonify({"data": records, "filters": filters, "stats": stats})


@dashboard_bp.route("/dashboard/api/reviews/<int:record_id>")
@login_required
def api_review_detail(record_id: int):
    data_type = (request.args.get("type") or "mr").strip()
    config = load_config()
    repo = SQLiteRepository(config.db_file)
    repo.init_db()
    record = repo.get_review_by_id("push" if data_type == "push" else "mr", record_id)
    if not record:
        return jsonify({"error": "Record not found"}), 404

    record["updated_at"] = format_timestamp(record.get("updated_at"))
    record["delta"] = format_delta(record.get("additions"), record.get("deletions"))
    return jsonify({"data": record})


@dashboard_bp.route("/dashboard/api/reviews/export")
@login_required
def api_export_csv():
    config = load_config()
    repo = SQLiteRepository(config.db_file)
    repo.init_db()
    params = parse_query_args(request.args)

    rows, meta = repo.get_reviews_paginated(
        data_type=params.data_type,
        authors=params.authors,
        project_names=params.project_names,
        language=params.language,
        status=params.status,
        updated_at_gte=params.updated_at_gte,
        updated_at_lte=params.updated_at_lte,
        sort=params.sort,
        order=params.order,
        page=1,
        page_size=10000,
    )

    records = serialize_records(rows, params.data_type)

    headers = [
        "project_name",
        "author",
        "updated_at",
        "status",
        "score",
        "delta",
        "commit_messages",
    ]
    if params.data_type == "mr":
        headers.insert(2, "source_branch")
        headers.insert(3, "target_branch")
    else:
        headers.insert(2, "branch")

    def q(v: object) -> str:
        s = "" if v is None else str(v)
        s = s.replace('"', '""')
        return f'"{s}"'

    lines = [",".join(headers)]
    for r in records:
        lines.append(",".join(q(r.get(h, "")) for h in headers))

    csv_data = "\n".join(lines) + "\n"
    filename = f"review_{params.data_type}_{datetime.date.today().isoformat()}.csv"
    return Response(
        csv_data,
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@dashboard_bp.route("/dashboard/api/reviews/<int:record_id>/retry", methods=["POST"])
@login_required
def api_retry(record_id: int):
    data_type = (request.args.get("type") or request.form.get("type") or "mr").strip()
    review_type = "push" if data_type == "push" else "mr"

    config = load_config()
    repo = SQLiteRepository(config.db_file)
    repo.init_db()
    queue = DbQueue(config.db_file)
    queue.init_db()
    usecase = RetryUseCase(repo=repo, queue=queue)

    try:
        payload, status_code = usecase.trigger_retry(record_id, review_type)
        return jsonify(payload), status_code
    except Exception as exc:
        return jsonify({"error": str(exc) or "Retry failed"}), 500
