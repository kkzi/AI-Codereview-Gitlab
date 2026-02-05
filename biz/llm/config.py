import os
import threading
import time
from typing import Any, Dict

import yaml

from biz.utils.log import logger


_lock = threading.Lock()
_cache: Dict[str, Any] = {"config": {}, "mtime": 0}


def _default_config_path() -> str:
    return os.getenv("LLM_CONFIG_PATH", "conf/llm.yml")


def _load_llm_config(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}
        return {str(k): v for k, v in data.items()}


def get_llm_config() -> Dict[str, Any]:
    path = _default_config_path()
    mtime = 0
    try:
        mtime = int(os.path.getmtime(path))
    except OSError:
        mtime = 0

    with _lock:
        if _cache["config"] and _cache["mtime"] == mtime:
            return _cache["config"]

        config = _load_llm_config(path)
        _cache["config"] = config
        _cache["mtime"] = mtime

    logger.info("LLM config loaded from %s at %s", path, int(time.time()))
    return _cache["config"]


def get_llm_value(key: str, default: Any = None) -> Any:
    config = get_llm_config()
    if key in config:
        return config[key]
    return os.getenv(key, default)
