from __future__ import annotations

import time
from typing import Optional

from app.infra.llm.base import ChatClient
from app.infra.llm.anthropic_client import AnthropicClient
from app.infra.llm.ollama_client import OllamaClient
from app.infra.llm.openai_client import OpenAIClient
from app.infra.llm.deepseek_client import DeepSeekClient
from app.infra.llm.qwen_client import QwenClient
from app.infra.llm.zhipuai_client import ZhipuAIClient
from app.infra.llm.config import get_llm_value


class LLMRetryExhaustedError(Exception):
    pass


class RetryClientWrapper(ChatClient):
    def __init__(self, client: ChatClient) -> None:
        self.client = client

    def ping(self) -> bool:
        return self.client.ping()

    def completions(self, messages, model: Optional[str] = None) -> str:
        retry_count = int(get_llm_value("LLM_RETRY_COUNT", "5"))
        last_error: Exception | None = None

        for attempt in range(retry_count):
            try:
                return self.client.completions(messages=messages, model=model)
            except Exception as exc:
                last_error = exc
                if attempt < retry_count - 1:
                    wait_time = min(2**attempt, 16)
                    time.sleep(wait_time)

        raise LLMRetryExhaustedError(
            f"LLM call failed after {retry_count} attempts: {last_error}"
        )


def get_client(provider: Optional[str] = None) -> ChatClient:
    provider = provider or (get_llm_value("LLM_PROVIDER", "openai") or "openai")
    factories = {
        "openai": OpenAIClient,
        "anthropic": AnthropicClient,
        "ollama": OllamaClient,
        "deepseek": DeepSeekClient,
        "qwen": QwenClient,
        "zhipuai": ZhipuAIClient,
    }
    if provider not in factories:
        raise ValueError(f"Unknown LLM provider: {provider}")
    return RetryClientWrapper(factories[provider]())


def get_model_name(provider: Optional[str] = None) -> str:
    provider = provider or (get_llm_value("LLM_PROVIDER", "openai") or "openai")
    api_model_env_map = {
        "openai": "OPENAI_API_MODEL",
        "anthropic": "ANTHROPIC_API_MODEL",
        "ollama": "OLLAMA_API_MODEL",
        "deepseek": "DEEPSEEK_API_MODEL",
        "qwen": "QWEN_API_MODEL",
        "zhipuai": "ZHIPUAI_API_MODEL",
    }
    env_key = api_model_env_map.get(provider)
    if env_key:
        model_name = get_llm_value(env_key)
        if model_name:
            return str(model_name)

    friendly = {
        "openai": "GPT",
        "anthropic": "Claude",
        "ollama": "Ollama",
        "deepseek": "DeepSeek",
        "qwen": "通义千问",
        "zhipuai": "智谱AI",
    }
    return friendly.get(provider, provider.upper())
