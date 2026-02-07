from __future__ import annotations

import sys

from app.core.config_validator import validate_config
from app.core.llm_status import set_llm_status
from app.core.logging import get_logger
from app.infra.llm.config import get_llm_value
from app.infra.llm.factory import get_client


_logger = get_logger(__name__)

LLM_PROVIDERS = {"anthropic", "zhipuai", "openai", "deepseek", "ollama", "qwen"}

LLM_REQUIRED_KEYS = {
    "anthropic": ["ANTHROPIC_API_KEY", "ANTHROPIC_API_BASE_URL", "ANTHROPIC_API_MODEL"],
    "zhipuai": ["ZHIPUAI_API_KEY", "ZHIPUAI_API_MODEL"],
    "openai": ["OPENAI_API_KEY", "OPENAI_API_MODEL"],
    "deepseek": ["DEEPSEEK_API_KEY", "DEEPSEEK_API_MODEL"],
    "ollama": ["OLLAMA_API_BASE_URL", "OLLAMA_API_MODEL"],
    "qwen": ["QWEN_API_KEY", "QWEN_API_MODEL"],
}


def check_llm_provider() -> None:
    llm_provider = get_llm_value("LLM_PROVIDER")
    if not llm_provider:
        _logger.warning("LLM_PROVIDER 未设置")
        return
    if llm_provider not in LLM_PROVIDERS:
        _logger.warning("LLM_PROVIDER=%s 不在支持范围内", llm_provider)
        return

    required_keys = LLM_REQUIRED_KEYS.get(llm_provider, [])
    missing_keys = [key for key in required_keys if not get_llm_value(key)]
    if missing_keys:
        _logger.warning(
            "LLM 配置缺少关键字段: %s", ", ".join(missing_keys)
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
