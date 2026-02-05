from multiprocessing import Process
from threading import Thread

from biz.utils.log import logger


def handle_queue(function: callable, data: any, token: str, url: str, url_slug: str, **kwargs):
    try:
        process = Process(target=function, args=(data, token, url, url_slug), kwargs=kwargs)
        process.start()
        return
    except Exception:
        # Some deployment environments disallow forking child processes from workers.
        # Fall back to a background thread to keep webhooks/retry endpoints responsive.
        logger.exception("Failed to start background process; falling back to thread")
        t = Thread(target=function, args=(data, token, url, url_slug), kwargs=kwargs, daemon=True)
        t.start()
