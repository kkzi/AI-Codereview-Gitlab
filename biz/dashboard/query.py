import datetime
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote
from urllib.parse import urlparse

import pandas as pd

from biz.dashboard.schema import format_delta, format_timestamp, normalize_author
from biz.service.review_service import ReviewService


ALLOWED_TYPES = {"mr", "push"}
ALLOWED_SORT_FIELDS = {
    # Note: DB column names, not display names.
    "updated_at",
    "score",
    "project_name",
    "author",
    "status",
}
ALLOWED_ORDER = {"asc", "desc"}


@dataclass(frozen=True)
class ReviewQueryParams:
    data_type: str
    updated_at_gte: Optional[int]
    updated_at_lte: Optional[int]
    authors: Optional[List[str]]
    project_names: Optional[List[str]]
    language: Optional[str]
    status: Optional[str]
    page: int
    page_size: int
    sort: str
    order: str


def _parse_date(s: Optional[str]) -> Optional[datetime.date]:
    if not s:
        return None
    return datetime.datetime.strptime(s, "%Y-%m-%d").date()


def parse_query_args(args: Dict[str, Any]) -> ReviewQueryParams:
    data_type = (args.get("type") or "mr").strip()
    if data_type not in ALLOWED_TYPES:
        data_type = "mr"

    start_date = _parse_date(args.get("start_date"))
    end_date = _parse_date(args.get("end_date"))

    updated_at_gte = (
        int(datetime.datetime.combine(start_date, datetime.time.min).timestamp())
        if start_date
        else None
    )
    updated_at_lte = (
        int(
            datetime.datetime.combine(end_date, datetime.time.max)
            .replace(hour=23, minute=59, second=59)
            .timestamp()
        )
        if end_date
        else None
    )

    # Backward compatible single-value filters.
    author = (args.get("author") or "").strip()
    project = (args.get("project") or "").strip()
    authors = [author] if author else None
    project_names = [project] if project else None

    language = (args.get("language") or "").strip() or None

    status = (args.get("status") or "").strip() or None
    if status not in {None, "success", "failed"}:
        status = None

    def _to_int(v: Any, default: int) -> int:
        try:
            return int(v)
        except Exception:
            return default

    page = max(1, _to_int(args.get("page"), 1))
    page_size = _to_int(args.get("page_size"), 50)
    page_size = min(max(page_size, 10), 200)

    sort = (args.get("sort") or "updated_at").strip()
    if sort not in ALLOWED_SORT_FIELDS:
        sort = "updated_at"

    order = (args.get("order") or "desc").strip().lower()
    if order not in ALLOWED_ORDER:
        order = "desc"

    return ReviewQueryParams(
        data_type=data_type,
        updated_at_gte=updated_at_gte,
        updated_at_lte=updated_at_lte,
        authors=authors,
        project_names=project_names,
        language=language,
        status=status,
        page=page,
        page_size=page_size,
        sort=sort,
        order=order,
    )


def serialize_dataframe(df: pd.DataFrame, data_type: str) -> List[Dict[str, Any]]:
    if df.empty:
        return []

    records: List[Dict[str, Any]] = df.to_dict(orient="records")

    def _netloc(url: str) -> str:
        if not url:
            return ""
        try:
            return (urlparse(url).netloc or "").lower()
        except Exception:
            return ""

    def _base_url(url: str) -> str:
        if not url:
            return ""
        try:
            u = urlparse(url)
            if not u.scheme or not u.netloc:
                return ""
            return f"{u.scheme}://{u.netloc}"
        except Exception:
            return ""

    gitlab_url = (os.getenv("GITLAB_URL") or "").strip()
    gitea_url = (os.getenv("GITEA_URL") or "").strip()
    github_url = (os.getenv("GITHUB_URL") or "https://github.com").strip()

    gitlab_netloc = _netloc(gitlab_url)
    gitea_netloc = _netloc(gitea_url)
    github_netloc = _netloc(github_url)

    def _detect_platform(project_url: str, commit_url: str) -> str:
        """Detect platform by URL host (supports self-hosted instances)."""
        host = _netloc(project_url) or _netloc(commit_url)
        if not host:
            return ""

        if host in {"api.github.com"}:
            return "github"
        if github_netloc and host == github_netloc:
            return "github"
        if gitlab_netloc and host == gitlab_netloc:
            return "gitlab"
        if gitea_netloc and host == gitea_netloc:
            return "gitea"

        if "github.com" in host:
            return "github"
        if "gitlab" in host:
            return "gitlab"
        if "gitea" in host:
            return "gitea"
        return ""

    def _build_author_url(project_url: str, commit_url: str, username: str) -> str:
        if not username:
            return ""
        try:
            platform = _detect_platform(project_url, commit_url)

            base = _base_url(project_url) or _base_url(commit_url)
            if not base:
                if platform == "github":
                    base = _base_url(github_url)
                elif platform == "gitlab":
                    base = _base_url(gitlab_url)
                elif platform == "gitea":
                    base = _base_url(gitea_url)

            if platform == "github" and _netloc(base) == "api.github.com":
                base = "https://github.com"

            if not base:
                return ""
            return f"{base.rstrip('/')}/{quote(username)}"
        except Exception:
            return ""

    def _build_branch_url(project_url: str, branch: str) -> str:
        if not project_url or not branch:
            return ""

        base = project_url.rstrip("/")
        b = quote(branch)

        # GitLab branch url uses /-/tree/...
        if "/-/" in base or "gitlab" in base:
            return f"{base}/-/tree/{b}"

        # Gitea commonly uses /src/branch/...
        if "gitea" in base:
            return f"{base}/src/branch/{b}"

        # GitHub (and many others) use /tree/...
        return f"{base}/tree/{b}"

    for row in records:
        raw_updated_at = row.get("updated_at")
        row["updated_at_ts"] = raw_updated_at
        row["updated_at"] = format_timestamp(raw_updated_at)
        row["delta"] = format_delta(row.get("additions"), row.get("deletions"))
        row["score"] = float(row.get("score", 0) or 0)

        # Preserve username vs display name for link + display.
        username = (row.get("author") or "").strip()
        display_name = (row.get("author_display_name") or "").strip()
        row["author_username"] = username
        row["author_display_name"] = display_name
        row["author"] = normalize_author(row)
        row["author_url"] = _build_author_url(
            row.get("project_url") or "", row.get("commit_url") or "", username
        )

        if data_type == "mr":
            row.setdefault("source_branch", "")
            row.setdefault("target_branch", "")

            project_url = row.get("project_url") or ""
            row["source_branch_url"] = _build_branch_url(project_url, row.get("source_branch") or "")
            row["target_branch_url"] = _build_branch_url(project_url, row.get("target_branch") or "")
        else:
            row.setdefault("branch", "")
            row["branch_url"] = _build_branch_url(row.get("project_url") or "", row.get("branch") or "")

        row.setdefault("model_name", "")
        row.setdefault("language", "")

    return records


def fetch_reviews(params: ReviewQueryParams) -> Tuple[List[Dict[str, Any]], Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    """Return (records, filters, stats, pagination)."""

    # Paginated query backed by SQL (preferred for UI).
    limit = params.page_size
    offset = (params.page - 1) * params.page_size

    if params.data_type == "push":
        df_page, meta = ReviewService().get_push_review_logs_paginated(
            authors=params.authors,
            project_names=params.project_names,
            language=params.language,
            updated_at_gte=params.updated_at_gte,
            updated_at_lte=params.updated_at_lte,
            status=params.status,
            limit=limit,
            offset=offset,
            sort=params.sort,
            order=params.order,
        )
    else:
        df_page, meta = ReviewService().get_mr_review_logs_paginated(
            authors=params.authors,
            project_names=params.project_names,
            language=params.language,
            updated_at_gte=params.updated_at_gte,
            updated_at_lte=params.updated_at_lte,
            status=params.status,
            limit=limit,
            offset=offset,
            sort=params.sort,
            order=params.order,
        )

    records = serialize_dataframe(df_page, params.data_type)

    total_rows = int(meta.get("total", 0) or 0)
    total_pages = (total_rows + params.page_size - 1) // params.page_size if params.page_size else 1
    pagination = {
        "page": params.page,
        "page_size": params.page_size,
        "total": total_rows,
        "total_pages": total_pages,
    }

    filters = {
        "authors": meta.get("authors", []),
        "projects": meta.get("projects", []),
        "languages": meta.get("languages", []),
    }
    stats = meta.get("stats", {"total": total_rows, "success": 0, "failed": 0, "avg_score": 0})

    return records, filters, stats, pagination
