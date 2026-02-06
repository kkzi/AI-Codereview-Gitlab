from __future__ import annotations

from typing import Dict, List, Optional

import httpx
from anthropic import Anthropic

from app.infra.llm.base import ChatClient
from app.infra.llm.config import get_llm_value


class AnthropicClient(ChatClient):
    def __init__(self, api_key: Optional[str] = None) -> None:
        resolved_key = api_key or (get_llm_value("ANTHROPIC_API_KEY") or "")
        if not resolved_key:
            raise ValueError("ANTHROPIC_API_KEY is required.")

        self.base_url = get_llm_value("ANTHROPIC_API_BASE_URL") or None
        try:
            self.timeout = float(get_llm_value("LLM_TIMEOUT", "60"))
        except Exception:
            self.timeout = 60.0

        http_client = httpx.Client(timeout=self.timeout)
        if self.base_url:
            self.client = Anthropic(api_key=resolved_key, base_url=self.base_url, http_client=http_client)
        else:
            self.client = Anthropic(api_key=resolved_key, http_client=http_client)

        self.default_model = str(
            get_llm_value("ANTHROPIC_API_MODEL", "claude-sonnet-4-5-20250929")
        )

    def ping(self) -> bool:
        try:
            result = self.completions(messages=[{"role": "user", "content": "请仅返回 ok"}])
            return result.strip() == "ok"
        except Exception:
            return False

    def completions(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
    ) -> str:
        system_message = None
        anthropic_messages = []
        for msg in messages:
            role = msg.get("role")
            content = msg.get("content")
            if role == "system":
                system_message = content
            else:
                anthropic_messages.append({"role": role, "content": content})

        response = self.client.messages.create(
            model=model or self.default_model,
            system=system_message,
            messages=anthropic_messages,
            max_tokens=int(get_llm_value("ANTHROPIC_MAX_TOKENS", "4096")),
        )
        return response.content[0].text
