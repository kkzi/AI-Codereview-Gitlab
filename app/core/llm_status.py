from __future__ import annotations

import threading
import time
from typing import Dict, Optional


_lock = threading.Lock()
_status: Dict[str, Optional[int]] = {"available": None, "checked_at": None}


def set_llm_status(available: bool, checked_at: Optional[int] = None) -> None:
    timestamp = checked_at if checked_at is not None else int(time.time())
    with _lock:
        _status["available"] = bool(available)
        _status["checked_at"] = timestamp


def get_llm_status() -> Dict[str, Optional[int]]:
    with _lock:
        return {
            "available": _status.get("available"),
            "checked_at": _status.get("checked_at"),
        }
