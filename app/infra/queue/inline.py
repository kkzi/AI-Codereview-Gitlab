from __future__ import annotations

from threading import Thread
from typing import Any, Callable


class InlineQueue:
    def enqueue(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        thread = Thread(target=func, args=args, kwargs=kwargs, daemon=True)
        thread.start()
