from __future__ import annotations

from typing import Dict, List, Optional

from zhipuai import ZhipuAI

from app.infra.llm.base import ChatClient
from app.infra.llm.config import get_llm_value


class ZhipuAIClient(ChatClient):
    def __init__(self, api_key: Optional[str] = None) -> None:
        resolved_key = api_key or (get_llm_value("ZHIPUAI_API_KEY") or "")
        if not resolved_key:
            raise ValueError("ZHIPUAI_API_KEY is required.")

        try:
            self.timeout = float(get_llm_value("LLM_TIMEOUT", "60"))
        except Exception:
            self.timeout = 60.0

        try:
            self.client = ZhipuAI(api_key=resolved_key, timeout=self.timeout)
        except TypeError:
            self.client = ZhipuAI(api_key=resolved_key)

        self.default_model = str(get_llm_value("ZHIPUAI_API_MODEL", "GLM-4-Flash"))

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
