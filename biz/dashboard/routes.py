import datetime
import os
import time
from flask import (
    Blueprint,
    Response,
    jsonify,
    redirect,
    render_template,
    request,
    session,
)

from biz.api import push_review_enabled
from biz.dashboard.auth import (
    DASHBOARD_PASSWORD,
    DASHBOARD_USER,
    authenticate,
    is_rate_limited,
    login_required,
    register_failed_login,
)
from biz.dashboard.query import fetch_reviews, parse_query_args
from biz.service.review_service import ReviewService
from biz.llm.factory import Factory
from biz.utils.log import logger
from biz.utils.llm_status import get_llm_status, set_llm_status


dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/dashboard")
@login_required
def dashboard_page():
    model_name = ReviewService._get_model_name_from_env()
    return render_template(
        "dashboard.html",
        push_enabled=push_review_enabled,
        llm_model_name=model_name or "unknown",
    )


@dashboard_bp.route("/dashboard/api/llm/check", methods=["POST"])
@login_required
def api_llm_check():
    model_name = ReviewService._get_model_name_from_env()
    try:
        client = Factory().getClient()
        available = bool(client.ping())
    except Exception:
        logger.exception("LLM ping failed")
        available = False

    checked_at = int(time.time())
    set_llm_status(available, checked_at)
    return jsonify(
        {
            "available": available,
            "checked_at": checked_at,
            "model_name": model_name or "unknown",
        }
    )


@dashboard_bp.route("/dashboard/api/llm/status", methods=["GET"])
@login_required
def api_llm_status():
    model_name = ReviewService._get_model_name_from_env()
    status = get_llm_status()
    return jsonify(
        {
            "available": status.get("available"),
            "checked_at": status.get("checked_at"),
            "model_name": model_name or "unknown",
        }
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
            f"用户名或密码错误（剩余尝试次数：{remaining}）"
            if remaining
            else "用户名或密码错误"
        )

    # Keep template behavior that warns when still admin/admin.
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


# New API (preferred)
@dashboard_bp.route("/dashboard/api/reviews")
@login_required
def api_reviews():
    params = parse_query_args(request.args)
    records, filters, stats, pagination = fetch_reviews(params)
    return jsonify(
        {
            "data": records,
            "filters": filters,
            "stats": stats,
            "pagination": pagination,
        }
    )


# Backward compatible API (existing clients)
@dashboard_bp.route("/dashboard/api/data")
@login_required
def api_data_compat():
    # Adapt old endpoint to new implementation.
    params = parse_query_args(request.args)
    records, filters, stats, _pagination = fetch_reviews(params)
    return jsonify({"data": records, "filters": filters, "stats": stats})


@dashboard_bp.route("/dashboard/api/reviews/<int:record_id>")
@login_required
def api_review_detail(record_id: int):
    data_type = (request.args.get("type") or "mr").strip()
    if data_type == "push":
        record = ReviewService().get_push_review_log_by_id(record_id)
    else:
        record = ReviewService().get_mr_review_log_by_id(record_id)

    if not record:
        return jsonify({"error": "Record not found"}), 404

    # Keep consistent formatting for the UI.
    from biz.dashboard.schema import format_delta, format_timestamp

    record["updated_at"] = format_timestamp(record.get("updated_at"))
    record["delta"] = format_delta(record.get("additions"), record.get("deletions"))
    return jsonify({"data": record})


@dashboard_bp.route("/dashboard/api/reviews/export")
@login_required
def api_export_csv():
    # Export should ignore pagination. We query the full filtered dataset via ReviewService.
    params = parse_query_args(request.args)

    if params.data_type == "push":
        df = ReviewService().get_push_review_logs(
            authors=params.authors,
            project_names=params.project_names,
            updated_at_gte=params.updated_at_gte,
            updated_at_lte=params.updated_at_lte,
        )
    else:
        df = ReviewService().get_mr_review_logs(
            authors=params.authors,
            project_names=params.project_names,
            updated_at_gte=params.updated_at_gte,
            updated_at_lte=params.updated_at_lte,
        )

    if params.status and not df.empty and "status" in df.columns:
        df = df[df["status"] == params.status]

    if not df.empty and params.sort in df.columns:
        ascending = params.order == "asc"
        df = df.sort_values(by=params.sort, ascending=ascending, kind="mergesort")

    from biz.dashboard.query import serialize_dataframe

    records = serialize_dataframe(df, params.data_type)

    # Minimal CSV (escape by quoting with double quotes)
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

    def q(v):
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

    from biz.api.retry import trigger_retry

    try:
        payload, status_code = trigger_retry(
            record_id=record_id, review_type=review_type
        )
        return jsonify(payload), status_code
    except Exception as e:
        logger.exception("Retry failed")
        return jsonify({"error": str(e) or "Retry failed"}), 500
