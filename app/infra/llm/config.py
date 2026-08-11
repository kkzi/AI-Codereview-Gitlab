from __future__ import annotations

import os
import threading
import time
from typing import Any, Dict, List

import yaml

from app.core.logging import get_logger


_lock = threading.Lock()
_cache: Dict[str, Any] = {"config": {}, "mtime": 0}
_logger = get_logger(__name__)


def _default_config_path() -> str:
    return os.getenv("LLM_CONFIG_PATH", "conf/llm.yml")


def _load_llm_config(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as file:
            data = yaml.safe_load(file) or {}
            return {str(k): v for k, v in data.items()}
    except Exception:
        _logger.exception("加载 LLM 配置失败: %s", path)
        return {}


def get_llm_config() -> Dict[str, Any]:
    path = _default_config_path()
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

    _logger.info("LLM 配置已加载: %s", path)
    return _cache["config"]


def get_llm_config_mtime() -> float:
    path = _default_config_path()
    try:
        return float(os.path.getmtime(path))
    except OSError:
        return 0.0


def get_llm_value(key: str, default: Any | None = None) -> Any:
    env_value = os.getenv(key)
    if env_value is not None and str(env_value).strip() != "":
        return env_value
    config = get_llm_config()
    if key in config:
        return config[key]
    return default


def get_llm_profiles() -> List[Dict[str, Any]]:
    config = get_llm_config()
    raw_profiles = config.get("llm_profiles") or config.get("LLM_PROFILES") or []
    if not isinstance(raw_profiles, list):
        return []

    profiles: List[Dict[str, Any]] = []
    for idx, raw in enumerate(raw_profiles):
        if not isinstance(raw, dict):
            continue
        profile = {str(k): v for k, v in raw.items()}
        name = str(profile.get("name") or profile.get("profile") or f"profile_{idx + 1}")
        provider = str(profile.get("type") or profile.get("provider") or "").strip().lower()
        base_url = profile.get("baseurl") or profile.get("base_url") or profile.get("baseURL")
        api_key = profile.get("key") or profile.get("api_key")
        model = profile.get("model")
        options = profile.get("options") if isinstance(profile.get("options"), dict) else {}
        profiles.append(
            {
                "name": name,
                "type": provider,
                "base_url": base_url,
                "key": api_key,
                "model": model,
                "options": options,
            }
        )

    return profiles
