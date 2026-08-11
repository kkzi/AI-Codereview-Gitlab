from __future__ import annotations

import sys

from app.core.config_validator import validate_config
from app.core.llm_status import set_llm_status
from app.core.logging import get_logger
from app.infra.llm.config import get_llm_profiles
from app.infra.llm.factory import get_client


_logger = get_logger(__name__)

def check_llm_provider() -> None:
    profiles = get_llm_profiles()
    if not profiles:
        _logger.warning("llm_profiles 未设置")
        return
    _check_llm_profiles(profiles)


def _check_llm_profiles(profiles) -> None:
    supported = {"anthropic", "zhipuai", "chat", "responses", "deepseek", "ollama", "qwen"}
    required_fields = {
        "anthropic": ["key", "model"],
        "zhipuai": ["key", "model"],
        "chat": ["key", "model"],
        "responses": ["key", "model"],
        "deepseek": ["key", "model"],
        "ollama": ["base_url", "model"],
        "qwen": ["key", "model"],
    }
    for idx, profile in enumerate(profiles):
        name = profile.get("name") or f"profile_{idx + 1}"
        provider = str(profile.get("type") or "").strip().lower()
        if provider not in supported:
            _logger.warning("LLM Profile %s 提供商不支持: %s", name, provider)
            continue
        missing = [field for field in required_fields[provider] if not profile.get(field)]
        if missing:
            _logger.warning(
                "LLM Profile %s 缺少关键字段: %s", name, ", ".join(missing)
            )


def check_llm_connectivity() -> None:
    try:
        available = bool(get_client().ping())
    except Exception:
        _logger.exception("LLM 可用性检测失败")
        available = False
    set_llm_status(available)


def check_config(strict: bool = False) -> None:
    """检查配置

    Args:
        strict: 如果为 True，配置验证失败时将退出程序
    """
    # 运行全面的配置验证
    _logger.info("开始配置验证...")
    is_valid = validate_config()

    if not is_valid:
        if strict:
            _logger.error("配置验证失败，程序退出")
            sys.exit(1)
        else:
            _logger.warning("配置验证失败，但继续运行（非严格模式）")

    # 运行 LLM 连接性检查
    check_llm_connectivity()
