"""Deterministic aggregation of per-factor assessments (no LLM, no DB)."""

from schemas import (
    FactorAssessment,
    ReasoningStep,
    ReasoningStepType,
    RegulationReference,
    RiskFactorType,
    RiskLevel,
    find_banned_terms,
)

from common.aggregation import build_assessment, overall_score, risk_level


def _fa(score: float, regs: list[RegulationReference] | None = None) -> FactorAssessment:
    return FactorAssessment(
        score=score,
        rationale_th="เหตุผลประกอบการพิจารณา",
        reasoning_steps=[
            ReasoningStep(step_type=ReasoningStepType.EVIDENCE, text_th="หลักฐานที่ตรวจสอบ")
        ],
        regulation_references=regs or [],
    )


def _all(score: float) -> dict:
    return {ft: _fa(score) for ft in RiskFactorType}


class TestBanding:
    def test_bands(self):
        assert risk_level(10, has_high_severity_precheck=False) == RiskLevel.LOW
        assert risk_level(40, has_high_severity_precheck=False) == RiskLevel.MEDIUM
        assert risk_level(60, has_high_severity_precheck=False) == RiskLevel.HIGH
        assert risk_level(80, has_high_severity_precheck=False) == RiskLevel.REQUIRES_INVESTIGATION

    def test_high_severity_precheck_overrides_low_score(self):
        assert (
            risk_level(5, has_high_severity_precheck=True) == RiskLevel.REQUIRES_INVESTIGATION
        )


class TestOverallScore:
    def test_weighted_mean_of_equal_weights(self):
        assessment = build_assessment(_all(70), has_high_severity_precheck=False)
        assert assessment.overall_score == 70.0
        assert abs(sum(f.weight for f in assessment.factors) - 1.0) < 1e-6

    def test_mixed_scores(self):
        scored = dict(zip(RiskFactorType, [_fa(s) for s in (100, 0, 50, 50, 50)], strict=True))
        assessment = build_assessment(scored, has_high_severity_precheck=False)
        assert overall_score(assessment.factors) == 50.0


class TestWeightRenormalization:
    def test_missing_factors_still_sum_to_one(self):
        # only 3 of 5 factors scored (two dropped after re-asks)
        scored = {
            RiskFactorType.BUDGET_DEVIATION: _fa(60),
            RiskFactorType.THRESHOLD_SPLITTING: _fa(60),
            RiskFactorType.DOCUMENT_COMPLETENESS: _fa(60),
        }
        assessment = build_assessment(scored, has_high_severity_precheck=False)
        assert len(assessment.factors) == 3
        assert abs(sum(f.weight for f in assessment.factors) - 1.0) < 1e-6
        assert assessment.overall_score == 60.0


class TestAssemblyDetails:
    def test_regulations_collected_and_deduped(self):
        ref = RegulationReference(
            regulation_id="fiscal-discipline-act-2561/s.37",
            act_name_th="พ.ร.บ. วินัยการเงินการคลัง",
            section_no="37",
            relevance_th="ความคุ้มค่า",
        )
        scored = {ft: _fa(50, regs=[ref]) for ft in RiskFactorType}
        assessment = build_assessment(scored, has_high_severity_precheck=False)
        assert len(assessment.regulation_references) == 1  # deduped across factors

    def test_summary_is_non_accusatory_and_has_disclaimer(self):
        assessment = build_assessment(_all(80), has_high_severity_precheck=False)
        assert "ผู้ตรวจสอบ" in assessment.summary_th
        assert find_banned_terms(assessment.summary_th) == []
