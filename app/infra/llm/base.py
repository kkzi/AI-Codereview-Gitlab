from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol


class ChatClient(Protocol):
    def ping(self) -> bool:
        ...

    def completions(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
    ) -> str:
        ...
