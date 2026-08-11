from __future__ import annotations

from typing import Any, Dict, List, Optional

from openai import OpenAI

from app.infra.llm.base import ChatClient
from app.infra.llm.config import get_llm_value


class OpenAIClient(ChatClient):
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[float] = None,
        extra_body: Optional[Dict[str, object]] = None,
        api_type: str = "chat",
        response_options: Optional[Dict[str, object]] = None,
    ) -> None:
        resolved_key = api_key or (get_llm_value("OPENAI_API_KEY") or "")
        if not resolved_key:
            raise ValueError("OPENAI_API_KEY is required.")

        self.base_url = str(
            base_url or get_llm_value("OPENAI_API_BASE_URL", "https://api.openai.com/v1")
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

        self.default_model = str(model or get_llm_value("OPENAI_API_MODEL", "gpt-4o-mini"))
        self.extra_body = extra_body or None
        self.api_type = api_type
        self.response_options = response_options or {}

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
        kwargs: Dict[str, object] = {}
        if self.extra_body:
            kwargs["extra_body"] = self.extra_body

        if self.api_type == "responses":
            response = self.client.responses.create(
                model=model or self.default_model,
                input=messages,
                **self.response_options,
                **kwargs,
            )
            return self._extract_response_text(response)

        completion = self.client.chat.completions.create(
            model=model or self.default_model,
            messages=messages,
            **kwargs,
        )
        return completion.choices[0].message.content

    @staticmethod
    def _extract_response_text(response: Any) -> str:
        output_text = getattr(response, "output_text", None)
        if output_text:
            return str(output_text)

        if isinstance(response, dict):
            output = response.get("output") or []
        else:
            output = getattr(response, "output", None) or []

        parts: List[str] = []
        for item in output:
            content = item.get("content") if isinstance(item, dict) else getattr(item, "content", [])
            for block in content or []:
                if isinstance(block, dict):
                    text = block.get("text")
                else:
                    text = getattr(block, "text", None)
                if text:
                    parts.append(str(text))

        if parts:
            return "".join(parts)
        raise ValueError("OpenAI Responses API returned no text output.")
