"""Tests for the enum-locked RiskResult contract — the gate for everything downstream."""

import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from schemas import RiskAssessment, RiskFactor, RiskFactorType, RiskLevel, RiskResult


def make_factor(**overrides) -> dict:
    base = {
        "factor_type": "BUDGET_DEVIATION",
        "score": 72.5,
        "weight": 1.0,
        "rationale_th": "งบประมาณสูงกว่าค่ากลางของโครงการประเภทเดียวกันอย่างมีนัยสำคัญ",
    }
    return {**base, **overrides}


def make_assessment(**overrides) -> dict:
    base = {
        "risk_level": "HIGH",
        "overall_score": 72.5,
        "factors": [make_factor()],
        "summary_th": "พบความเบี่ยงเบนของงบประมาณที่ควรได้รับการตรวจสอบโดยผู้ตรวจสอบ",
    }
    return {**base, **overrides}


class TestRiskLevelEnum:
    def test_exactly_four_closed_values(self):
        assert {m.value for m in RiskLevel} == {
            "LOW",
            "MEDIUM",
            "HIGH",
            "REQUIRES_INVESTIGATION",
        }

    def test_thai_labels(self):
        assert RiskLevel.LOW.label_th == "ต่ำ"
        assert RiskLevel.MEDIUM.label_th == "ปานกลาง"
        assert RiskLevel.HIGH.label_th == "สูง"
        assert RiskLevel.REQUIRES_INVESTIGATION.label_th == "ควรตรวจสอบเพิ่มเติม"

    @pytest.mark.parametrize("banned", ["fraud", "corruption", "ทุจริต", "โกง", "ฉ้อโกง"])
    def test_accusatory_verdicts_are_impossible(self, banned):
        with pytest.raises(ValidationError):
            RiskAssessment.model_validate(make_assessment(risk_level=banned))

    def test_guided_json_schema_locks_the_enum(self):
        """The schema handed to vLLM guided_json must constrain risk_level to the enum."""
        schema = RiskAssessment.model_json_schema()
        level_schema = schema["$defs"]["RiskLevel"]
        assert set(level_schema["enum"]) == {
            "LOW",
            "MEDIUM",
            "HIGH",
            "REQUIRES_INVESTIGATION",
        }
        # extra="forbid" → the model cannot smuggle a free-text verdict field
        assert schema["additionalProperties"] is False


class TestScoreAndWeightRanges:
    @pytest.mark.parametrize("bad_score", [-1, 100.1, 500])
    def test_overall_score_bounded_0_100(self, bad_score):
        with pytest.raises(ValidationError):
            RiskAssessment.model_validate(make_assessment(overall_score=bad_score))

    @pytest.mark.parametrize("bad_score", [-0.1, 101])
    def test_factor_score_bounded_0_100(self, bad_score):
        with pytest.raises(ValidationError):
            RiskAssessment.model_validate(
                make_assessment(factors=[make_factor(score=bad_score)])
            )

    def test_weights_must_sum_to_one(self):
        factors = [
            make_factor(factor_type="BUDGET_DEVIATION", weight=0.5),
            make_factor(factor_type="VENDOR_CONCENTRATION", weight=0.3),
            make_factor(factor_type="THRESHOLD_SPLITTING", weight=0.2),
        ]
        assessment = RiskAssessment.model_validate(make_assessment(factors=factors))
        assert len(assessment.factors) == 3

    def test_bad_weight_sum_rejected(self):
        factors = [
            make_factor(factor_type="BUDGET_DEVIATION", weight=0.5),
            make_factor(factor_type="VENDOR_CONCENTRATION", weight=0.6),
        ]
        with pytest.raises(ValidationError, match="sum to 1.0"):
            RiskAssessment.model_validate(make_assessment(factors=factors))

    def test_at_least_one_factor_required(self):
        with pytest.raises(ValidationError):
            RiskAssessment.model_validate(make_assessment(factors=[]))


class TestFactorTypes:
    def test_closed_factor_taxonomy(self):
        assert {m.value for m in RiskFactorType} == {
            "BUDGET_DEVIATION",
            "VENDOR_CONCENTRATION",
            "TIMELINE_ANOMALY",
            "THRESHOLD_SPLITTING",
            "DOCUMENT_COMPLETENESS",
        }

    def test_unknown_factor_type_rejected(self):
        with pytest.raises(ValidationError):
            RiskFactor.model_validate(make_factor(factor_type="VIBES"))


class TestRiskResult:
    def test_extra_fields_forbidden(self):
        with pytest.raises(ValidationError):
            RiskAssessment.model_validate(make_assessment(verdict_text="anything"))

    def test_full_result_roundtrip_utf8(self):
        result = RiskResult.model_validate(
            make_assessment(
                project_id=str(uuid4()),
                model_id="scb10x/typhoon2.5-qwen3-30b-a3b",
                prompt_version="risk_scoring/v1",
                generated_at=datetime.now(UTC).isoformat(),
            )
        )
        dumped = result.model_dump_json()
        restored = RiskResult.model_validate_json(dumped)
        assert restored == result
        # Thai text survives serialization intact
        assert "ผู้ตรวจสอบ" in json.loads(dumped)["summary_th"]

    def test_provenance_required(self):
        with pytest.raises(ValidationError):
            RiskResult.model_validate(make_assessment())  # no project/model/prompt/time
