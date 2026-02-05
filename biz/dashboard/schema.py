import datetime
from typing import Any, Dict


def format_timestamp(ts: Any) -> str:
    if isinstance(ts, (int, float)):
        return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
    return "" if ts is None else str(ts)


def format_delta(additions: Any, deletions: Any) -> str:
    a = int(additions or 0)
    d = int(deletions or 0)
    return f"+{a}\n-{d}"


def normalize_author(row: Dict[str, Any]) -> str:
    # Prefer display name when available.
    author_display_name = (row.get("author_display_name") or "").strip()
    return author_display_name or (row.get("author") or "")
