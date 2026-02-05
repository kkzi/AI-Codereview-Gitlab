"""Dashboard blueprint compatibility shim.

The dashboard was originally implemented in this module. It has been moved to
`biz.dashboard.routes` to keep concerns separated.

Keep this file so `biz.api.routes.register_routes()` continues to work without
changing import paths.
"""

from biz.dashboard.routes import dashboard_bp
