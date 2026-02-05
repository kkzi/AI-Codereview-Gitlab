from typing import Dict, List, Optional

from zhipuai import ZhipuAI

from biz.llm.client.base import BaseClient
from biz.llm.config import get_llm_value
from biz.llm.types import NotGiven, NOT_GIVEN


class ZhipuAIClient(BaseClient):
    def __init__(self, api_key: Optional[str] = None):
        resolved_key = api_key or (get_llm_value("ZHIPUAI_API_KEY") or "")
        if not resolved_key:
            raise ValueError(
                "API key is required. Please provide it or set it in the environment variables."
            )

        self.api_key = resolved_key
        self.client = ZhipuAI(api_key=self.api_key)
        self.default_model = str(get_llm_value("ZHIPUAI_API_MODEL", "GLM-4-Flash"))

    def completions(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] | NotGiven = NOT_GIVEN,
    ) -> str:
        model = model or self.default_model
        completion = self.client.chat.completions.create(
            model=model,
            messages=messages,
        )
        return completion.choices[0].message.content
