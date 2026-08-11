from __future__ import annotations

from typing import Dict, List, Optional

from openai import OpenAI

from app.infra.llm.base import ChatClient
from app.infra.llm.config import get_llm_value


class QwenClient(ChatClient):
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[float] = None,
        extra_body: Optional[Dict[str, object]] = None,
    ) -> None:
        resolved_key = api_key or (get_llm_value("QWEN_API_KEY") or "")
        if not resolved_key:
            raise ValueError("QWEN_API_KEY is required.")

        self.base_url = str(
            base_url
            or get_llm_value(
                "QWEN_API_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
            )
        )
        if timeout is None:
            try:
                timeout = float(get_llm_value("LLM_TIMEOUT", "60"))
            except Exception:
                timeout = 60.0
        self.timeout = float(timeout)

        try:
            self.client = OpenAI(api_key=resolved_key, base_url=self.base_url, timeout=self.timeout)
        except TypeError:
            self.client = OpenAI(api_key=resolved_key, base_url=self.base_url)

        self.default_model = str(model or get_llm_value("QWEN_API_MODEL", "qwen-coder-plus"))
        self.extra_body = extra_body or {"enable_thinking": False}

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
            extra_body=self.extra_body,
        )
        return completion.choices[0].message.content
