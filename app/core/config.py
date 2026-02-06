from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _get_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class AppConfig:
    env: str
    server_port: int
    templates_dir: str
    static_dir: str
    db_file: str
    dashboard_secret_key: str
    dashboard_cookie_secure: bool
    push_review_enabled: bool
    merge_review_only_protected_branches_enabled: bool
    review_style: str
    review_max_tokens: int
    llm_retry_count: int


def load_config() -> AppConfig:
    repo_root = Path(__file__).resolve().parents[2]
    return AppConfig(
        env=os.getenv("APP_ENV", "development"),
        server_port=int(os.getenv("SERVER_PORT", "5001")),
        templates_dir=str(repo_root / "templates"),
        static_dir=str(repo_root / "static"),
        db_file=os.getenv("DB_FILE", "data/data.db"),
        dashboard_secret_key=os.getenv(
            "DASHBOARD_SECRET_KEY",
            "fac8cf149bdd616c07c1a675c4571ccacc40d7f7fe16914cfe0f9f9d966bb773",
        ),
        dashboard_cookie_secure=_get_bool("DASHBOARD_COOKIE_SECURE", False),
        push_review_enabled=_get_bool("PUSH_REVIEW_ENABLED", False),
        merge_review_only_protected_branches_enabled=_get_bool(
            "MERGE_REVIEW_ONLY_PROTECTED_BRANCHES_ENABLED", False
        ),
        review_style=os.getenv("REVIEW_STYLE", "professional"),
        review_max_tokens=int(os.getenv("REVIEW_MAX_TOKENS", "10000")),
        llm_retry_count=int(os.getenv("LLM_RETRY_COUNT", "5")),
    )
