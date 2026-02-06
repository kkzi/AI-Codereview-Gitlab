from __future__ import annotations

import threading
import time
from typing import Callable, Dict, Optional

from app.core.logging import get_logger
from app.infra.queue.db_queue import DbQueue


logger = get_logger(__name__)


def run_worker(
    queue: DbQueue,
    handler: Callable[[Dict[str, object]], None],
    *,
    poll_interval: float = 1.0,
) -> None:
    while True:
        job = queue.claim_next_job()
        if not job:
            time.sleep(poll_interval)
            continue

        job_id = int(job["id"])
        try:
            handler(job)
            queue.mark_done(job_id)
        except Exception as exc:
            logger.exception("Job failed: %s", exc)
            queue.mark_failed(
                job_id,
                attempts=int(job.get("attempts", 0)),
                max_attempts=int(job.get("max_attempts", 3)),
                error=str(exc),
            )


def start_worker_thread(
    queue: DbQueue,
    handler: Callable[[Dict[str, object]], None],
    *,
    poll_interval: float = 1.0,
) -> threading.Thread:
    thread = threading.Thread(
        target=run_worker,
        args=(queue, handler),
        kwargs={"poll_interval": poll_interval},
        daemon=True,
    )
    thread.start()
    return thread
