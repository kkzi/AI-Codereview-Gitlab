from typing import Dict, List, Optional

from openai import OpenAI

from biz.llm.client.base import BaseClient
from biz.llm.config import get_llm_value
from biz.llm.types import NotGiven, NOT_GIVEN


class QwenClient(BaseClient):
    def __init__(self, api_key: Optional[str] = None):
        resolved_key = api_key or (get_llm_value("QWEN_API_KEY") or "")
        self.base_url = str(
            get_llm_value(
                "QWEN_API_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
            )
        )
        try:
            self.timeout = float(get_llm_value("LLM_TIMEOUT", "60"))
        except Exception:
            self.timeout = 60.0
        if not resolved_key:
            raise ValueError(
                "API key is required. Please provide it or set it in the environment variables."
            )

        self.api_key = resolved_key
        try:
            self.client = OpenAI(
                api_key=self.api_key, base_url=self.base_url, timeout=self.timeout
            )
        except TypeError:
            self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        self.default_model = str(get_llm_value("QWEN_API_MODEL", "qwen-coder-plus"))
        self.extra_body = {"enable_thinking": False}

    def completions(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] | NotGiven = NOT_GIVEN,
    ) -> str:
        model = model or self.default_model
        completion = self.client.chat.completions.create(
            model=model,
            messages=messages,
            extra_body=self.extra_body,
        )
        return completion.choices[0].message.content
