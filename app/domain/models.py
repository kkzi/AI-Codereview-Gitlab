from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class WebhookEvent:
    review_type: str
    source: str
    event_type: str
    project_name: str
    project_url: str
    created_at: int
    payload: Dict[str, Any]
    event_id: Optional[int] = None


@dataclass(frozen=True)
class ReviewResult:
    score: int
    review_text: str
    model_name: str
    language: str
    additions: int
    deletions: int
