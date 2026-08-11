from __future__ import annotations

from typing import Any, Dict

import tiktoken


_encoding_cache: Dict[str, Any] = {}


def _get_encoding(encoding_name: str = "cl100k_base") -> Any:
    encoding = _encoding_cache.get(encoding_name)
    if encoding is None:
        encoding = tiktoken.get_encoding(encoding_name)
        _encoding_cache[encoding_name] = encoding
    return encoding


def count_tokens(text: str, encoding_name: str = "cl100k_base") -> int:
    encoding = _get_encoding(encoding_name)
    return len(encoding.encode(text))


def truncate_text_by_tokens(
    text: str,
    max_tokens: int,
    encoding_name: str = "cl100k_base",
) -> str:
    encoding = _get_encoding(encoding_name)
    tokens = encoding.encode(text)
    if len(tokens) <= max_tokens:
        return text
    return encoding.decode(tokens[:max_tokens])
