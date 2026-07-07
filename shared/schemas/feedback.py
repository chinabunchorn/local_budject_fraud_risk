"""Auditor feedback contract (human-in-the-loop).

Auditors disposition every flag; their feedback is stored raw, then the batch
pipeline fills in sentiment and concern tags (guided-JSON, temperature 0).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class FeedbackSentiment(StrEnum):
    POSITIVE = "POSITIVE"
    NEUTRAL = "NEUTRAL"
    NEGATIVE = "NEGATIVE"


class Feedback(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    project_id: UUID
    risk_result_id: UUID | None = None
    text_th: str = Field(min_length=1)
    # Filled by the batch sentiment flow; None until analyzed
    sentiment: FeedbackSentiment | None = None
    concern_tags: list[str] = Field(default_factory=list)
    created_at: datetime
