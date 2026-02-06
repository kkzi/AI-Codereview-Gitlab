from __future__ import annotations

from flask import Flask

from app.api.routes.health import health_bp
from app.api.routes.webhook import webhook_bp
from app.api.routes.dashboard import dashboard_bp


def register_routes(app: Flask) -> None:
    app.register_blueprint(health_bp)
    app.register_blueprint(webhook_bp)
    app.register_blueprint(dashboard_bp)
