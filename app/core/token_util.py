from __future__ import annotations

import tiktoken


def count_tokens(text: str, encoding_name: str = "cl100k_base") -> int:
    encoding = tiktoken.get_encoding(encoding_name)
    return len(encoding.encode(text))


def truncate_text_by_tokens(
    text: str,
    max_tokens: int,
    encoding_name: str = "cl100k_base",
) -> str:
    encoding = tiktoken.get_encoding(encoding_name)
    tokens = encoding.encode(text)
    if len(tokens) <= max_tokens:
        return text
    return encoding.decode(tokens[:max_tokens])
