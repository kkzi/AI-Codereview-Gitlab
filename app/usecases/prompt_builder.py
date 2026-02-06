from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml
from jinja2 import Template


EXTENSION_TO_PROMPT = {
    ".py": "python_prompt",
    ".java": "java_prompt",
    ".js": "javascript_prompt",
    ".ts": "javascript_prompt",
    ".jsx": "javascript_prompt",
    ".tsx": "javascript_prompt",
    ".vue": "javascript_prompt",
    ".go": "golang_prompt",
    ".cpp": "cpp_prompt",
    ".cc": "cpp_prompt",
    ".cxx": "cpp_prompt",
    ".hpp": "cpp_prompt",
    ".h": "cpp_prompt",
    ".php": "php_prompt",
    ".sql": "sql_prompt",
    ".rb": "ruby_prompt",
}

PROMPT_TO_LANGUAGE_NAME = {
    "python_prompt": "Python",
    "java_prompt": "Java",
    "javascript_prompt": "JavaScript",
    "golang_prompt": "Go",
    "cpp_prompt": "C++",
    "php_prompt": "PHP",
    "sql_prompt": "SQL",
    "ruby_prompt": "Ruby",
}


class PromptBuilder:
    def __init__(self, style: str, model_name: str) -> None:
        self.style = style
        self.model_name = model_name or "LLM"

    @staticmethod
    def detect_primary_language_name(
        changes: Optional[List[Dict[str, Any]]],
    ) -> str:
        language_file = PromptBuilder._detect_language_from_changes(changes)
        if not language_file:
            return ""
        return PROMPT_TO_LANGUAGE_NAME.get(language_file, "")

    @staticmethod
    def _detect_language_from_changes(
        changes: Optional[List[Dict[str, Any]]],
    ) -> Optional[str]:
        if not changes:
            return None

        language_counts: Dict[str, int] = {}
        for change in changes:
            new_path = change.get("new_path", "")
            if not new_path:
                continue
            _, ext = os.path.splitext(new_path.lower())
            if ext in EXTENSION_TO_PROMPT:
                language_file = EXTENSION_TO_PROMPT[ext]
                language_counts[language_file] = language_counts.get(language_file, 0) + 1

        if not language_counts:
            return None

        primary_language = max(language_counts.items(), key=lambda item: item[1])[0]
        primary_count = language_counts[primary_language]
        if primary_count / len(changes) >= 0.5:
            return primary_language
        return None

    def build_messages(
        self,
        diffs_text: str,
        commits_text: str,
        changes: Optional[List[Dict[str, Any]]] = None,
    ) -> Tuple[List[Dict[str, str]], str]:
        language_file = self._detect_language_from_changes(changes)
        prompts = self._load_prompts_by_language("code_review_prompt", language_file)

        user_content = prompts["user_message"]["content"].format(
            diffs_text=diffs_text,
            commits_text=commits_text,
        )
        messages = [
            prompts["system_message"],
            {"role": "user", "content": user_content},
        ]
        language_name = PROMPT_TO_LANGUAGE_NAME.get(language_file, "") if language_file else ""
        return messages, language_name

    def _load_base_prompts(self) -> Dict[str, str]:
        repo_root = Path(__file__).resolve().parents[2]
        base_prompt_path = repo_root / "conf" / "base_prompt.yml"
        try:
            with open(base_prompt_path, "r", encoding="utf-8") as file:
                base_config = yaml.safe_load(file).get("code_review_prompt", {})
                return {
                    "scoring_rules": base_config.get("scoring_rules", ""),
                    "output_format": base_config.get("output_format", ""),
                    "style_template": base_config.get("style_template", ""),
                    "user_prompt_template": base_config.get("user_prompt_template", ""),
                }
        except Exception:
            return {}

    def _load_prompts_by_language(
        self, prompt_key: str, language_file: Optional[str]
    ) -> Dict[str, Any]:
        base_prompts = self._load_base_prompts()
        if not base_prompts:
            return self._default_prompts()

        language_specific_checks = ""
        user_prompt = base_prompts.get("user_prompt_template", "")

        if language_file:
            repo_root = Path(__file__).resolve().parents[2]
            language_prompt_path = repo_root / "conf" / f"{language_file}.yml"
            if language_prompt_path.exists():
                try:
                    with open(language_prompt_path, "r", encoding="utf-8") as file:
                        prompts = yaml.safe_load(file).get(prompt_key, {})
                    language_specific_checks = prompts.get(
                        "language_specific_checks", ""
                    )
                    if "user_prompt" in prompts:
                        user_prompt = prompts["user_prompt"]
                except Exception:
                    pass

        def render_template(template_str: str) -> str:
            return Template(template_str).render(style=self.style, model_name=self.model_name)

        scoring_rules = render_template(base_prompts.get("scoring_rules", ""))
        output_format = render_template(base_prompts.get("output_format", ""))
        style_template = render_template(base_prompts.get("style_template", ""))

        system_parts: List[str] = []
        if language_specific_checks:
            system_parts.append(render_template(language_specific_checks))
        system_parts.extend([scoring_rules, output_format, style_template])
        system_prompt = "\n\n".join([part for part in system_parts if part])

        user_prompt_rendered = render_template(user_prompt)

        return {
            "system_message": {"role": "system", "content": system_prompt},
            "user_message": {"role": "user", "content": user_prompt_rendered},
        }

    def _default_prompts(self) -> Dict[str, Any]:
        system_prompt = "请审查以下代码变更，指出问题并给出建议。"
        user_prompt = "代码变更内容：\n{diffs_text}\n\n提交历史：\n{commits_text}"
        return {
            "system_message": {"role": "system", "content": system_prompt},
            "user_message": {"role": "user", "content": user_prompt},
        }


def parse_review_score(review_text: str) -> int:
    if not review_text:
        return 0
    match = re.search(r"总分[:：]\s*(\d+)分?", review_text)
    if not match:
        return 0
    try:
        return int(match.group(1))
    except Exception:
        return 0
