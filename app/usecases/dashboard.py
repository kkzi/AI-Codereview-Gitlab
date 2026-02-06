from __future__ import annotations

import datetime
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote, urlparse

from app.infra.db.sqlite import SQLiteRepository


ALLOWED_TYPES = {"mr", "push"}
ALLOWED_SORT_FIELDS = {"updated_at", "score", "project_name", "author", "status"}
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

    author = (args.get("author") or "").strip()
    project = (args.get("project") or "").strip()
    authors = [author] if author else None
    project_names = [project] if project else None

    language = (args.get("language") or "").strip() or None

    status = (args.get("status") or "").strip() or None
    if status not in {None, "success", "failed", "skipped"}:
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


def format_timestamp(ts: Any) -> str:
    if not ts:
        return ""
    try:
        return datetime.datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return ""


def format_delta(additions: Any, deletions: Any) -> str:
    try:
        add = int(additions or 0)
    except Exception:
        add = 0
    try:
        delete = int(deletions or 0)
    except Exception:
        delete = 0
    return f"+{add}\n-{delete}"


def normalize_author(row: Dict[str, Any]) -> str:
    display = (row.get("author_display_name") or "").strip()
    username = (row.get("author_username") or row.get("author") or "").strip()
    if display and display != username:
        return f"{display} ({username})"
    return display or username


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


def _detect_platform(project_url: str, commit_url: str) -> str:
    host = _netloc(project_url) or _netloc(commit_url)
    if not host:
        return ""

    gitlab_url = (os.getenv("GITLAB_URL") or "").strip()
    gitea_url = (os.getenv("GITEA_URL") or "").strip()
    github_url = (os.getenv("GITHUB_URL") or "https://github.com").strip()

    if host in {"api.github.com"}:
        return "github"
    if _netloc(github_url) and host == _netloc(github_url):
        return "github"
    if _netloc(gitlab_url) and host == _netloc(gitlab_url):
        return "gitlab"
    if _netloc(gitea_url) and host == _netloc(gitea_url):
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
    platform = _detect_platform(project_url, commit_url)

    base = _base_url(project_url) or _base_url(commit_url)
    if not base:
        if platform == "github":
            base = _base_url(os.getenv("GITHUB_URL", "https://github.com"))
        elif platform == "gitlab":
            base = _base_url(os.getenv("GITLAB_URL", ""))
        elif platform == "gitea":
            base = _base_url(os.getenv("GITEA_URL", ""))

    if platform == "github" and _netloc(base) == "api.github.com":
        base = "https://github.com"

    if not base:
        return ""
    return f"{base.rstrip('/')}/{quote(username)}"


def _build_branch_url(project_url: str, branch: str) -> str:
    if not project_url or not branch:
        return ""
    base = project_url.rstrip("/")
    b = quote(branch)
    if "/-/" in base or "gitlab" in base:
        return f"{base}/-/tree/{b}"
    if "gitea" in base:
        return f"{base}/src/branch/{b}"
    return f"{base}/tree/{b}"


def serialize_records(rows: List[Dict[str, Any]], data_type: str) -> List[Dict[str, Any]]:
    if not rows:
        return []

    records: List[Dict[str, Any]] = []
    for row in rows:
        record = dict(row)
        raw_updated_at = record.get("updated_at")
        record["updated_at_ts"] = raw_updated_at
        record["updated_at"] = format_timestamp(raw_updated_at)
        record["delta"] = format_delta(record.get("additions"), record.get("deletions"))
        record["score"] = float(record.get("score", 0) or 0)

        username = (record.get("author") or "").strip()
        display_name = (record.get("author_display_name") or "").strip()
        record["author_username"] = username
        record["author_display_name"] = display_name
        record["author"] = normalize_author(record)
        record["author_url"] = _build_author_url(
            record.get("project_url") or "", record.get("commit_url") or "", username
        )

        if data_type == "mr":
            record.setdefault("source_branch", "")
            record.setdefault("target_branch", "")
            project_url = record.get("project_url") or ""
            record["source_branch_url"] = _build_branch_url(
                project_url, record.get("source_branch") or ""
            )
            record["target_branch_url"] = _build_branch_url(
                project_url, record.get("target_branch") or ""
            )
        else:
            record.setdefault("branch", "")
            record["branch_url"] = _build_branch_url(
                record.get("project_url") or "", record.get("branch") or ""
            )

        record.setdefault("model_name", "")
        record.setdefault("language", "")
        records.append(record)

    return records


def fetch_reviews(
    repo: SQLiteRepository, params: ReviewQueryParams
) -> Tuple[List[Dict[str, Any]], Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
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
        page=params.page,
        page_size=params.page_size,
    )

    records = serialize_records(rows, params.data_type)

    filters = {
        "authors": meta.get("authors", []),
        "projects": meta.get("projects", []),
        "languages": meta.get("languages", []),
    }
    stats = {
        "total": meta.get("total", 0),
        "success": meta.get("success", 0),
        "failed": meta.get("failed", 0),
        "avg_score": meta.get("avg_score", 0),
    }

    total = int(meta.get("total", 0) or 0)
    total_pages = max(1, (total + params.page_size - 1) // params.page_size)
    pagination = {
        "total": total,
        "total_pages": total_pages,
        "page": params.page,
        "page_size": params.page_size,
    }
    return records, filters, stats, pagination
