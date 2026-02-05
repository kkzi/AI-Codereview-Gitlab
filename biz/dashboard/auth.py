import os
import time
from functools import wraps
from typing import Dict, Tuple

from flask import jsonify, redirect, request, session


DASHBOARD_USER = os.getenv("DASHBOARD_USER", "admin")
DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD", "admin")


# Simple in-memory rate limit for login attempts.
# Good enough for single-process deployments. If you run multiple workers,
# consider moving this to Redis.
_FAILED_LOGINS: Dict[str, Tuple[int, float]] = {}


def _client_key() -> str:
    # Keep it simple: rate limit per remote IP.
    # NOTE: behind a reverse proxy, you may want to use X-Forwarded-For.
    return request.remote_addr or "unknown"


def is_rate_limited(max_attempts: int = 10, window_seconds: int = 300) -> bool:
    max_attempts = int(os.environ.get("DASHBOARD_LOGIN_MAX_ATTEMPTS", str(max_attempts)))
    window_seconds = int(
        os.environ.get("DASHBOARD_LOGIN_WINDOW_SECONDS", str(window_seconds))
    )
    key = _client_key()
    now = time.time()
    attempts, first_ts = _FAILED_LOGINS.get(key, (0, now))
    if now - first_ts > window_seconds:
        _FAILED_LOGINS.pop(key, None)
        return False
    return attempts >= max_attempts


def register_failed_login(max_attempts: int = 10, window_seconds: int = 300) -> int:
    """Register a failed login attempt and return remaining attempts in window."""
    max_attempts = int(os.environ.get("DASHBOARD_LOGIN_MAX_ATTEMPTS", str(max_attempts)))
    window_seconds = int(
        os.environ.get("DASHBOARD_LOGIN_WINDOW_SECONDS", str(window_seconds))
    )
    key = _client_key()
    now = time.time()
    attempts, first_ts = _FAILED_LOGINS.get(key, (0, now))
    if now - first_ts > window_seconds:
        attempts, first_ts = 0, now
    attempts += 1
    _FAILED_LOGINS[key] = (attempts, first_ts)
    remaining = max(0, max_attempts - attempts)
    return remaining


def clear_failed_logins():
    # Useful for tests.
    _FAILED_LOGINS.clear()


def login_required(view_func):
    """Protect a view with the simple session-based login used by the dashboard."""

    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if not session.get("logged_in"):
            if request.is_json or request.path.startswith("/dashboard/api/"):
                return jsonify({"error": "Unauthorized"}), 401
            return redirect("/dashboard/login")
        return view_func(*args, **kwargs)

    return wrapper


def authenticate(username: str, password: str) -> bool:
    return username == DASHBOARD_USER and password == DASHBOARD_PASSWORD
