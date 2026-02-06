from dotenv import load_dotenv

load_dotenv("conf/.env")

from app.core.config import load_config
from app.core.logging import configure_logging
from app.infra.db.sqlite import SQLiteRepository
from app.infra.queue.db_queue import DbQueue
from app.infra.queue.worker import run_worker
from app.usecases.reconcile import requeue_unreviewed_events
from app.usecases.review import ReviewUseCase


if __name__ == "__main__":
    configure_logging()
    config = load_config()

    repo = SQLiteRepository(config.db_file)
    repo.init_db()

    queue = DbQueue(config.db_file)
    queue.init_db()

    usecase = ReviewUseCase(repo=repo, queue=queue, config=config)
    requeue_unreviewed_events(repo, queue, days=7)
    run_worker(queue, usecase.process_job)
