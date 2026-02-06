from __future__ import annotations

from typing import Callable, Dict

from app.infra.llm.base import ChatClient


class ClientRegistry:
    def __init__(self) -> None:
        self._factories: Dict[str, Callable[[], ChatClient]] = {}

    def register(self, name: str, factory: Callable[[], ChatClient]) -> None:
        self._factories[name] = factory

    def get(self, name: str) -> ChatClient:
        if name not in self._factories:
            raise ValueError(f"Unknown LLM provider: {name}")
        return self._factories[name]()
