"""Tests for the auditor Feedback contract."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from schemas import Feedback, FeedbackSentiment


def make_feedback(**overrides) -> dict:
    base = {
        "id": str(uuid4()),
        "project_id": str(uuid4()),
        "text_th": "ควรขอเอกสารสัญญาเพิ่มเติมก่อนสรุปผลการตรวจสอบ",
        "created_at": datetime.now(UTC).isoformat(),
    }
    return {**base, **overrides}


class TestFeedback:
    def test_sentiment_closed_enum(self):
        assert {m.value for m in FeedbackSentiment} == {"POSITIVE", "NEUTRAL", "NEGATIVE"}

    def test_sentiment_optional_until_batch_analysis(self):
        fb = Feedback.model_validate(make_feedback())
        assert fb.sentiment is None
        assert fb.concern_tags == []

    def test_analyzed_feedback(self):
        fb = Feedback.model_validate(
            make_feedback(sentiment="NEGATIVE", concern_tags=["เอกสารไม่ครบ"])
        )
        assert fb.sentiment is FeedbackSentiment.NEGATIVE

    def test_unknown_sentiment_rejected(self):
        with pytest.raises(ValidationError):
            Feedback.model_validate(make_feedback(sentiment="ANGRY"))

    def test_empty_text_rejected(self):
        with pytest.raises(ValidationError):
            Feedback.model_validate(make_feedback(text_th=""))
