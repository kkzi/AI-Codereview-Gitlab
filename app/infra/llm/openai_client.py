from __future__ import annotations

from typing import Dict, List, Optional

from openai import OpenAI

from app.infra.llm.base import ChatClient
from app.infra.llm.config import get_llm_value


class OpenAIClient(ChatClient):
    def __init__(self, api_key: Optional[str] = None) -> None:
        resolved_key = api_key or (get_llm_value("OPENAI_API_KEY") or "")
        if not resolved_key:
            raise ValueError("OPENAI_API_KEY is required.")

        self.base_url = str(get_llm_value("OPENAI_API_BASE_URL", "https://api.openai.com"))
        try:
            self.timeout = float(get_llm_value("LLM_TIMEOUT", "60"))
        except Exception:
            self.timeout = 60.0

        try:
            self.client = OpenAI(api_key=resolved_key, base_url=self.base_url, timeout=self.timeout)
        except TypeError:
            self.client = OpenAI(api_key=resolved_key, base_url=self.base_url)

        self.default_model = str(get_llm_value("OPENAI_API_MODEL", "gpt-4o-mini"))

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
        completion = self.client.chat.completions.create(
            model=model or self.default_model,
            messages=messages,
        )
        return completion.choices[0].message.content
