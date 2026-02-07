from dotenv import load_dotenv

load_dotenv("conf/.env")

from app.core.config import load_config
from app.core.config_checker import check_config
from app.core.logging import configure_logging, get_logger
from app.infra.db.sqlite import SQLiteRepository
from app.infra.queue.db_queue import DbQueue
from app.infra.queue.worker import run_worker
from app.usecases.reconcile import requeue_unreviewed_events
from app.usecases.review import ReviewUseCase


if __name__ == "__main__":
    configure_logging()
    logger = get_logger(__name__)
    config = load_config()

    # 验证配置（严格模式：配置无效时退出）
    check_config(strict=True)

    repo = SQLiteRepository(config.db_file)
    repo.init_db()

    queue = DbQueue(config.db_file)
    queue.init_db()
    reclaimed = queue.reclaim_stale_jobs()
    if reclaimed:
        logger.warning("Reclaimed %s stale jobs on startup", reclaimed)

    usecase = ReviewUseCase(repo=repo, queue=queue, config=config)
    requeue_unreviewed_events(repo, queue, days=7)
    run_worker(queue, usecase.process_job)
