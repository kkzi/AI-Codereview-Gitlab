from typing import Dict, List, Optional

import httpx
from anthropic import Anthropic

from biz.llm.client.base import BaseClient
from biz.llm.config import get_llm_value
from biz.llm.types import NotGiven, NOT_GIVEN


class AnthropicClient(BaseClient):
    def __init__(self, api_key: Optional[str] = None):
        resolved_key = api_key or (get_llm_value("ANTHROPIC_API_KEY") or "")
        self.base_url = get_llm_value("ANTHROPIC_API_BASE_URL") or None
        if not resolved_key:
            raise ValueError(
                "API key is required. Please provide it or set ANTHROPIC_API_KEY in the environment variables."
            )

        # Create a custom httpx client to avoid proxy-related issues
        # This prevents the 'proxies' parameter error when environment proxy variables are set
        http_client = httpx.Client()

        self.api_key = resolved_key
        # Initialize Anthropic client with custom http_client
        if self.base_url:
            self.client = Anthropic(
                api_key=self.api_key, base_url=self.base_url, http_client=http_client
            )
        else:
            self.client = Anthropic(api_key=self.api_key, http_client=http_client)

        self.default_model = str(
            get_llm_value("ANTHROPIC_API_MODEL", "claude-sonnet-4-5-20250929")
        )

    def completions(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] | NotGiven = NOT_GIVEN,
    ) -> str:
        model = model or self.default_model

        # Convert messages to Anthropic format
        # Anthropic requires separating system messages from user/assistant messages
        system_message = None
        anthropic_messages = []

        for msg in messages:
            role = msg.get("role")
            content = msg.get("content")

            if role == "system":
                # Anthropic uses a separate system parameter
                system_message = content
            else:
                # Keep user and assistant messages
                anthropic_messages.append({"role": role, "content": content})

        # Create completion with Anthropic API
        response = self.client.messages.create(
            model=model,
            system=system_message,
            messages=anthropic_messages,
            max_tokens=int(get_llm_value("ANTHROPIC_MAX_TOKENS", "4096")),
        )

        # Extract text from response
        return response.content[0].text
