from __future__ import annotations

import os
from flask import Flask

from app.api.routes import register_routes
from app.core.config import load_config
from app.core.logging import configure_logging, get_logger
from app.infra.db.sqlite import SQLiteRepository
from app.infra.queue.db_queue import DbQueue
from app.infra.queue.worker import start_worker_thread
from app.usecases.reconcile import requeue_unreviewed_events
from app.usecases.review import ReviewUseCase


def create_app() -> Flask:
    config = load_config()
    configure_logging()
    logger = get_logger(__name__)
    app = Flask(
        __name__,
        template_folder=config.templates_dir,
        static_folder=config.static_dir,
        static_url_path="/static",
    )
    app.config["SECRET_KEY"] = config.dashboard_secret_key
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = config.dashboard_cookie_secure

    register_routes(app)

    if os.getenv("QUEUE_RUN_IN_APP", "0") == "1":
        repo = SQLiteRepository(config.db_file)
        repo.init_db()
        queue = DbQueue(config.db_file)
        queue.init_db()
        reclaimed = queue.reclaim_stale_jobs()
        if reclaimed:
            logger.warning("Reclaimed %s stale jobs on startup", reclaimed)
        usecase = ReviewUseCase(repo=repo, queue=queue, config=config)
        requeue_unreviewed_events(repo, queue, days=7)
        start_worker_thread(queue, usecase.process_job)
    return app
