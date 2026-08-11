from __future__ import annotations

import re
from typing import Dict, List, Optional

from ollama import Client

from app.infra.llm.base import ChatClient
from app.infra.llm.config import get_llm_value


class OllamaClient(ChatClient):
    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> None:
        self.default_model = str(model or get_llm_value("OLLAMA_API_MODEL", "deepseek-r1-8k:14b"))
        self.base_url = str(base_url or get_llm_value("OLLAMA_API_BASE_URL", "http://127.0.0.1:11434"))
        if timeout is None:
            try:
                timeout = float(get_llm_value("LLM_TIMEOUT", "60"))
            except Exception:
                timeout = 60.0
        self.timeout = float(timeout)

        try:
            self.client = Client(host=self.base_url, timeout=self.timeout)
        except TypeError:
            self.client = Client(host=self.base_url)

    def ping(self) -> bool:
        try:
            result = self.completions(messages=[{"role": "user", "content": "请仅返回 ok"}])
            return result.strip() == "ok"
        except Exception:
            return False

    def _extract_content(self, content: str) -> str:
        if "<think>" in content and "</think>" not in content:
            return "COT ABORT!"
        if "<think>" not in content and "</think>" in content:
            return content.split("</think>", 1)[1].strip()
        if re.search(r"<think>.*?</think>", content, re.DOTALL):
            return re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
        return content

    def completions(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
    ) -> str:
        response = self.client.chat(model or self.default_model, messages)
        content = response["message"]["content"]
        return self._extract_content(content)
