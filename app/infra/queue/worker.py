from __future__ import annotations

import threading
import time
from typing import Callable, Dict, Optional

from app.core.logging import get_logger
from app.core.performance import get_monitor
from app.infra.queue.db_queue import DbQueue


logger = get_logger(__name__)


def _performance_summary_thread(interval: int = 300) -> None:
    """定期输出性能监控摘要的后台线程

    Args:
        interval: 输出间隔（秒），默认 300 秒（5 分钟）
    """
    monitor = get_monitor()
    while True:
        time.sleep(interval)
        try:
            monitor.log_summary()
        except Exception as exc:
            logger.exception("Failed to log performance summary: %s", exc)


def run_worker(
    queue: DbQueue,
    handler: Callable[[Dict[str, object]], None],
    *,
    poll_interval: float = 1.0,
    enable_performance_summary: bool = True,
) -> None:
    # 启动性能监控摘要线程
    if enable_performance_summary:
        summary_thread = threading.Thread(
            target=_performance_summary_thread,
            args=(300,),  # 每 5 分钟输出一次
            daemon=True,
        )
        summary_thread.start()
        logger.info("Performance monitoring enabled (summary every 5 minutes)")

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
