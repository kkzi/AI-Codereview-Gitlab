import os
import time
from typing import Any

import requests

from biz.utils.log import logger


def _get_timeout() -> float:
    try:
        return float(os.getenv("HTTP_TIMEOUT", "15"))
    except Exception:
        return 15.0


def _get_retries() -> int:
    try:
        return int(os.getenv("HTTP_RETRY_COUNT", "2"))
    except Exception:
        return 2


def _get_backoff() -> float:
    try:
        return float(os.getenv("HTTP_RETRY_BACKOFF", "1"))
    except Exception:
        return 1.0


def request_with_retry(
    method: str,
    url: str,
    *,
    timeout: float | None = None,
    retries: int | None = None,
    backoff: float | None = None,
    **kwargs: Any,
) -> requests.Response:
    timeout = _get_timeout() if timeout is None else timeout
    retries = _get_retries() if retries is None else retries
    backoff = _get_backoff() if backoff is None else backoff

    last_error: Exception | None = None
    for attempt in range(max(retries, 1)):
        try:
            return requests.request(method, url, timeout=timeout, **kwargs)
        except requests.exceptions.RequestException as e:
            last_error = e
            logger.warning(
                "HTTP request failed (attempt %s/%s) %s %s: %s",
                attempt + 1,
                retries,
                method,
                url,
                e,
            )
            if attempt < retries - 1:
                sleep_time = backoff * (2**attempt) if backoff else 0
                if sleep_time > 0:
                    time.sleep(sleep_time)
            else:
                break

    if last_error:
        raise last_error
    raise RuntimeError("HTTP request failed without exception")
