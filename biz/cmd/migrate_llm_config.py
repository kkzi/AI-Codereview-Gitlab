import os
from typing import Dict

import yaml
from dotenv import dotenv_values


LLM_KEYS = [
    "LLM_PROVIDER",
    "LLM_RETRY_COUNT",
    "DEEPSEEK_API_KEY",
    "DEEPSEEK_API_BASE_URL",
    "DEEPSEEK_API_MODEL",
    "OPENAI_API_KEY",
    "OPENAI_API_BASE_URL",
    "OPENAI_API_MODEL",
    "ZHIPUAI_API_KEY",
    "ZHIPUAI_API_MODEL",
    "QWEN_API_KEY",
    "QWEN_API_BASE_URL",
    "QWEN_API_MODEL",
    "OLLAMA_API_BASE_URL",
    "OLLAMA_API_MODEL",
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_API_BASE_URL",
    "ANTHROPIC_API_MODEL",
    "ANTHROPIC_MAX_TOKENS",
]


def _load_yaml(path: str) -> Dict[str, str]:
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}
        return {str(k): v for k, v in data.items()}


def _write_yaml(path: str, data: Dict[str, str]) -> None:
    with open(path, "w", encoding="utf-8") as file:
        yaml.safe_dump(data, file, default_flow_style=False, sort_keys=False)


def migrate_llm_env_to_yaml(
    env_path: str = "conf/.env",
    yaml_path: str = "conf/llm.yml",
) -> int:
    env_data = dotenv_values(env_path)
    if not env_data:
        print(f"No env data found in {env_path}")
        return 0

    config = _load_yaml(yaml_path)
    updated_keys = []

    for key in LLM_KEYS:
        value = env_data.get(key)
        if value is None or value == "":
            continue
        config[key] = value
        updated_keys.append(key)

    if updated_keys:
        _write_yaml(yaml_path, config)

    print(f"Migrated {len(updated_keys)} keys to {yaml_path}")
    return len(updated_keys)


if __name__ == "__main__":
    migrate_llm_env_to_yaml()
