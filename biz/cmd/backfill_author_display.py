import os
import sqlite3
from urllib.parse import urlparse, quote

import requests
from dotenv import load_dotenv


DB_FILE = "data/data.db"
TABLES = ["mr_review_log", "push_review_log"]


def detect_platform(project_url: str, commit_url: str, gitlab_url: str, gitea_url: str) -> str:
    url = (project_url or commit_url or "").strip()
    if not url:
        return ""

    host = urlparse(url).netloc.lower()
    if "github.com" in host:
        return "github"

    if gitlab_url:
        if host == urlparse(gitlab_url).netloc.lower():
            return "gitlab"

    if gitea_url:
        if host == urlparse(gitea_url).netloc.lower():
            return "gitea"

    if "gitlab" in host:
        return "gitlab"

    return ""


def build_base_url(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}"


def get_gitlab_display_name(username: str, base_url: str, token: str) -> str:
    if not username or not base_url or not token:
        return ""
    url = f"{base_url.rstrip('/')}/api/v4/users?username={quote(username)}"
    response = requests.get(url, headers={"Private-Token": token}, timeout=10, verify=False)
    if response.status_code != 200:
        return ""
    data = response.json()
    if not data:
        return ""
    return data[0].get("name") or data[0].get("username") or ""


def get_github_display_name(username: str, token: str) -> str:
    if not username:
        return ""
    headers = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"token {token}"
    response = requests.get(f"https://api.github.com/users/{quote(username)}", headers=headers, timeout=10)
    if response.status_code != 200:
        return ""
    data = response.json()
    return data.get("name") or data.get("login") or ""


def get_gitea_display_name(username: str, base_url: str, token: str) -> str:
    if not username or not base_url:
        return ""
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"token {token}"
    url = f"{base_url.rstrip('/')}/api/v1/users/{quote(username)}"
    response = requests.get(url, headers=headers, timeout=10, verify=False)
    if response.status_code != 200:
        return ""
    data = response.json()
    return data.get("full_name") or data.get("name") or data.get("login") or ""


def fetch_display_name(platform: str, username: str, project_url: str, commit_url: str,
                       gitlab_url: str, gitlab_token: str, github_token: str, gitea_url: str,
                       gitea_token: str) -> str:
    if platform == "gitlab":
        base_url = gitlab_url or build_base_url(project_url) or build_base_url(commit_url)
        return get_gitlab_display_name(username, base_url, gitlab_token)
    if platform == "github":
        return get_github_display_name(username, github_token)
    if platform == "gitea":
        base_url = gitea_url or build_base_url(project_url) or build_base_url(commit_url)
        return get_gitea_display_name(username, base_url, gitea_token)
    return ""


def backfill_display_names():
    load_dotenv("conf/.env")
    gitlab_url = os.getenv("GITLAB_URL", "").strip()
    gitlab_token = os.getenv("GITLAB_ACCESS_TOKEN", "").strip()
    github_token = os.getenv("GITHUB_ACCESS_TOKEN", "").strip()
    gitea_url = os.getenv("GITEA_URL", "").strip()
    gitea_token = os.getenv("GITEA_ACCESS_TOKEN", "").strip()

    total_updated = 0

    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        for table in TABLES:
            cursor.execute(f"SELECT id, author, author_display_name, project_url, commit_url FROM {table}")
            rows = cursor.fetchall()
            for row in rows:
                record_id, author, display_name, project_url, commit_url = row
                if display_name and str(display_name).strip():
                    continue
                author = (author or "").strip()
                if not author:
                    continue

                platform = detect_platform(project_url or "", commit_url or "", gitlab_url, gitea_url)
                if not platform:
                    continue

                resolved_name = fetch_display_name(
                    platform,
                    author,
                    project_url or "",
                    commit_url or "",
                    gitlab_url,
                    gitlab_token,
                    github_token,
                    gitea_url,
                    gitea_token,
                )

                if resolved_name and resolved_name.strip():
                    cursor.execute(
                        f"UPDATE {table} SET author_display_name = ? WHERE id = ?",
                        (resolved_name.strip(), record_id),
                    )
                    total_updated += 1

        conn.commit()

    print(f"Backfill complete. Updated {total_updated} records.")


if __name__ == "__main__":
    backfill_display_names()
