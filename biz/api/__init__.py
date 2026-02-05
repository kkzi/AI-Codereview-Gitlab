"""
API 应用初始化模块
"""

import os
from flask import Flask

push_review_enabled = os.environ.get("PUSH_REVIEW_ENABLED", "0") == "1"

# Compute absolute paths for templates and static directories
_current_dir = os.path.dirname(os.path.abspath(__file__))  # biz/api/
_project_root = os.path.dirname(os.path.dirname(_current_dir))  # project root
_templates_folder = os.path.join(_project_root, "templates")
_static_folder = os.path.join(_project_root, "static")

# Keep templates/static under repo root so the app can be packaged as a single container.
api_app = Flask(
    __name__,
    template_folder=_templates_folder,
    static_folder=_static_folder,
    static_url_path="/static",
)
api_app.config["SECRET_KEY"] = os.environ.get(
    "DASHBOARD_SECRET_KEY",
    "fac8cf149bdd616c07c1a675c4571ccacc40d7f7fe16914cfe0f9f9d966bb773",
)
api_app.config["TEMPLATES_AUTO_RELOAD"] = True

# Session cookie hardening for the admin dashboard.
api_app.config["SESSION_COOKIE_HTTPONLY"] = True
api_app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

# Only set this to True when serving over HTTPS, otherwise browsers may drop the cookie.
api_app.config["SESSION_COOKIE_SECURE"] = os.environ.get("DASHBOARD_COOKIE_SECURE", "0") == "1"


def init_app(app):
    """
    初始化应用，注册所有路由
    """
    from biz.api.routes import register_routes

    register_routes(app)
