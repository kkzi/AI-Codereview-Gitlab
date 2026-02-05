import time
from typing import Optional

from biz.llm.client.base import BaseClient
from biz.llm.client.anthropic import AnthropicClient
from biz.llm.client.deepseek import DeepSeekClient
from biz.llm.client.ollama_client import OllamaClient
from biz.llm.client.openai import OpenAIClient
from biz.llm.client.qwen import QwenClient
from biz.llm.client.zhipuai import ZhipuAIClient
from biz.llm.config import get_llm_value
from biz.utils.log import logger


class LLMRetryExhaustedError(Exception):
    """LLM 重试次数用尽异常"""

    pass


class RetryClientWrapper(BaseClient):
    """客户端包装器，为 completions 方法添加重试逻辑"""

    def __init__(self, client: BaseClient):
        self.client = client

    def ping(self) -> bool:
        """Ping the model to check connectivity."""
        return self.client.ping()

    def completions(self, messages, model=None):
        """Chat with the model with retry logic."""
        retry_count = int(get_llm_value("LLM_RETRY_COUNT", "5"))
        last_error = None

        for attempt in range(retry_count):
            try:
                return self.client.completions(messages=messages, model=model)
            except Exception as e:
                last_error = e
                logger.warning(
                    f"AI 模型调用失败 (尝试 {attempt + 1}/{retry_count}): {e}"
                )

                if attempt < retry_count - 1:
                    # 指数退避策略: 1s, 2s, 4s, 8s, 16s
                    wait_time = min(2**attempt, 16)
                    logger.info(f"等待 {wait_time} 秒后重试...")
                    time.sleep(wait_time)

        # 所有重试都失败，抛出异常而不是返回错误字符串
        error_msg = f"AI 模型调用失败，已重试 {retry_count} 次: {last_error}"
        logger.error(error_msg)
        raise LLMRetryExhaustedError(error_msg)


class Factory:
    @staticmethod
    def getClient(provider: Optional[str] = None) -> BaseClient:
        provider = provider or (
            get_llm_value("LLM_PROVIDER", "anthropic") or "anthropic"
        )
        chat_model_providers = {
            "anthropic": lambda: AnthropicClient(),
            "zhipuai": lambda: ZhipuAIClient(),
            "openai": lambda: OpenAIClient(),
            "deepseek": lambda: DeepSeekClient(),
            "qwen": lambda: QwenClient(),
            "ollama": lambda: OllamaClient(),
        }

        provider_func = chat_model_providers.get(provider)
        if provider_func:
            client = provider_func()
            # 用重试装饰器包装客户端
            return RetryClientWrapper(client)
        else:
            raise Exception(f"Unknown chat model provider: {provider}")
