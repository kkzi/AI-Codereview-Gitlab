from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from app.core.performance import get_monitor
from app.infra.llm.base import ChatClient
from app.infra.llm.anthropic_client import AnthropicClient
from app.infra.llm.ollama_client import OllamaClient
from app.infra.llm.openai_client import OpenAIClient
from app.infra.llm.deepseek_client import DeepSeekClient
from app.infra.llm.qwen_client import QwenClient
from app.infra.llm.zhipuai_client import ZhipuAIClient
from app.infra.llm.config import (
    get_llm_config_mtime,
    get_llm_profiles,
    get_llm_value,
)


class LLMRetryExhaustedError(Exception):
    pass


class RetryClientWrapper(ChatClient):
    def __init__(self, client: ChatClient, provider: str) -> None:
        self.client = client
        self.provider = provider
        self.monitor = get_monitor()

    def ping(self) -> bool:
        return self.client.ping()

    def completions(self, messages, model: Optional[str] = None) -> str:
        retry_count = int(get_llm_value("LLM_RETRY_COUNT", "5"))
        last_error: Exception | None = None

        with self.monitor.measure("llm_api_call", {"provider": self.provider}):
            for attempt in range(retry_count):
                try:
                    result = self.client.completions(messages=messages, model=model)

                    # 记录成功的 API 调用
                    if attempt > 0:
                        self.monitor.increment_counter(f"llm_retry_success_{self.provider}")

                    return result
                except Exception as exc:
                    last_error = exc
                    self.monitor.increment_counter(f"llm_api_error_{self.provider}")

                    if attempt < retry_count - 1:
                        wait_time = min(2**attempt, 16)
                        time.sleep(wait_time)

            # 所有重试都失败
            self.monitor.increment_counter(f"llm_retry_exhausted_{self.provider}")
            raise LLMRetryExhaustedError(
                f"LLM call failed after {retry_count} attempts: {last_error}"
            )


@dataclass(frozen=True)
class LLMProfile:
    name: str
    provider: str
    api_key: Optional[str]
    base_url: Optional[str]
    model: Optional[str]
    options: Dict[str, Any]


_last_success_profile: Optional[LLMProfile] = None


def _set_last_success_profile(profile: LLMProfile) -> None:
    global _last_success_profile
    _last_success_profile = profile


def _get_last_success_profile() -> Optional[LLMProfile]:
    return _last_success_profile


def _build_profiles() -> List[LLMProfile]:
    profiles: List[LLMProfile] = []
    for raw in get_llm_profiles():
        provider = str(raw.get("type") or "").strip().lower()
        if not provider:
            continue
        profiles.append(
            LLMProfile(
                name=str(raw.get("name") or provider),
                provider=provider,
                api_key=raw.get("key"),
                base_url=raw.get("base_url"),
                model=raw.get("model"),
                options=raw.get("options") or {},
            )
        )
    return profiles


_cache_lock = threading.Lock()
_profiles_cache: Tuple[Optional[float], Optional[List[LLMProfile]]] = (None, None)
_clients_cache: Dict[Tuple[float, Tuple[str, ...]], ChatClient] = {}


def _get_profiles_cached() -> Tuple[List[LLMProfile], float]:
    """Build LLM profiles once and reuse until the config file changes."""
    global _profiles_cache
    mtime = get_llm_config_mtime()
    with _cache_lock:
        cached_mtime, cached_profiles = _profiles_cache
        if cached_profiles is not None and cached_mtime == mtime:
            return cached_profiles, mtime
    profiles = _build_profiles()
    with _cache_lock:
        _profiles_cache = (mtime, profiles)
    return profiles, mtime


def _get_cached_client(
    mtime: float, selected: List[LLMProfile]
) -> ChatClient:
    """Return a cached MultiProfileClient for the given profile selection."""
    global _clients_cache
    key = (mtime, tuple(profile.name for profile in selected))
    with _cache_lock:
        client = _clients_cache.get(key)
    if client is not None:
        return client
    client = MultiProfileClient(selected)
    with _cache_lock:
        _clients_cache[key] = client
    return client


def _build_client_from_profile(profile: LLMProfile) -> ChatClient:
    provider = profile.provider
    options = profile.options or {}
    timeout = options.get("timeout")
    extra_body = options.get("extra_body")
    response_options = options.get("response_options")
    if response_options is not None and not isinstance(response_options, dict):
        response_options = None
    if extra_body is None and "enable_thinking" in options:
        extra_body = {"enable_thinking": bool(options.get("enable_thinking"))}

    if provider in {"chat", "responses"}:
        return OpenAIClient(
            api_key=profile.api_key,
            base_url=profile.base_url,
            model=profile.model,
            timeout=timeout,
            extra_body=extra_body,
            api_type=provider,
            response_options=response_options,
        )
    if provider == "anthropic":
        return AnthropicClient(
            api_key=profile.api_key,
            base_url=profile.base_url,
            model=profile.model,
            timeout=timeout,
            max_tokens=options.get("max_tokens"),
        )
    if provider == "ollama":
        return OllamaClient(
            base_url=profile.base_url,
            model=profile.model,
            timeout=timeout,
        )
    if provider == "deepseek":
        return DeepSeekClient(
            api_key=profile.api_key,
            base_url=profile.base_url,
            model=profile.model,
            timeout=timeout,
            extra_body=extra_body,
        )
    if provider == "qwen":
        return QwenClient(
            api_key=profile.api_key,
            base_url=profile.base_url,
            model=profile.model,
            timeout=timeout,
            extra_body=extra_body,
        )
    if provider == "zhipuai":
        return ZhipuAIClient(
            api_key=profile.api_key,
            model=profile.model,
            timeout=timeout,
        )
    raise ValueError(f"Unknown LLM provider: {provider}")


class MultiProfileClient(ChatClient):
    def __init__(self, profiles: List[LLMProfile]) -> None:
        self.profiles = profiles
        self.monitor = get_monitor()
        self.retry_count = int(get_llm_value("LLM_RETRY_COUNT", "5"))
        self._clients: Dict[str, ChatClient] = {}

    def _get_client(self, profile: LLMProfile) -> ChatClient:
        if profile.name in self._clients:
            return self._clients[profile.name]
        client = _build_client_from_profile(profile)
        self._clients[profile.name] = client
        return client

    def ping(self) -> bool:
        try:
            result = self.completions(messages=[{"role": "user", "content": "请仅返回 ok"}])
            return result.strip() == "ok"
        except Exception:
            return False

    def completions(self, messages, model: Optional[str] = None) -> str:
        if not self.profiles:
            raise ValueError("No LLM profiles configured.")

        last_error: Exception | None = None
        last_profile: Optional[LLMProfile] = None
        total_attempts = max(int(self.retry_count), 1)

        for attempt in range(total_attempts):
            profile = self.profiles[attempt % len(self.profiles)]
            last_profile = profile
            try:
                client = self._get_client(profile)
                with self.monitor.measure("llm_api_call", {"provider": profile.provider}):
                    result = client.completions(messages=messages, model=model)
                if attempt > 0:
                    self.monitor.increment_counter(f"llm_retry_success_{profile.provider}")
                _set_last_success_profile(profile)
                return result
            except Exception as exc:
                last_error = exc
                self.monitor.increment_counter(f"llm_api_error_{profile.provider}")
                if attempt < total_attempts - 1:
                    wait_time = min(2**attempt, 16)
                    time.sleep(wait_time)

        if last_profile:
            self.monitor.increment_counter(f"llm_retry_exhausted_{last_profile.provider}")
        raise LLMRetryExhaustedError(
            f"LLM call failed after {total_attempts} attempts: {last_error}"
        )


def get_client(provider: Optional[str] = None) -> ChatClient:
    profiles, mtime = _get_profiles_cached()
    if not profiles:
        raise ValueError("No LLM profiles configured. Please set llm_profiles in conf/llm.yml.")

    if provider:
        match = [
            profile
            for profile in profiles
            if profile.provider == provider or profile.name == provider
        ]
        if not match:
            raise ValueError(f"No LLM profile matches provider/name: {provider}")
        return _get_cached_client(mtime, match)

    return _get_cached_client(mtime, profiles)


def get_model_name(provider: Optional[str] = None) -> str:
    profiles, _ = _get_profiles_cached()
    if profiles:
        if provider:
            profile = next(
                (
                    item
                    for item in profiles
                    if item.provider == provider or item.name == provider
                ),
                None,
            )
            if profile and profile.model:
                return str(profile.model)
            if profile:
                return _friendly_provider_name(profile.provider)

        active = _get_last_success_profile()
        profile = active or profiles[0]
        if profile.model:
            return str(profile.model)
        return _friendly_provider_name(profile.provider)

    return "unknown"


def _get_model_name_for_provider(provider: str) -> str:
    api_model_env_map = {
        "chat": "OPENAI_API_MODEL",
        "responses": "OPENAI_API_MODEL",
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

    return _friendly_provider_name(provider)


def _friendly_provider_name(provider: str) -> str:
    friendly = {
        "chat": "OpenAI Chat",
        "responses": "OpenAI Responses",
        "anthropic": "Claude",
        "ollama": "Ollama",
        "deepseek": "DeepSeek",
        "qwen": "通义千问",
        "zhipuai": "智谱AI",
    }
    return friendly.get(provider, provider.upper())


def get_active_profile_info() -> Optional[Dict[str, str]]:
    profiles, _ = _get_profiles_cached()
    if not profiles:
        return None
    active = _get_last_success_profile() or profiles[0]
    return {
        "name": active.name,
        "type": active.provider,
        "model": str(active.model) if active.model else "",
    }
