"""Deterministic aggregation of per-factor assessments (Phase G, v2).

The model scores each factor independently (`FactorAssessment`); this module
combines them into the `RiskAssessment` with NO LLM in the path:

- `overall_score` = weighted sum of factor scores (fixed weights — equal by
  default, since there is no labelled calibration set yet; tune `FACTOR_WEIGHTS`
  when there is);
- `risk_level` = deterministic banding of the overall score, with a HARD rule
  that a HIGH-severity deterministic pre-check (e.g. the YoY contractor-
  concentration flag) forces REQUIRES_INVESTIGATION regardless of score — the
  human-look verdict is settled by code, keeping the enum out of the model's
  free choice entirely;
- `summary_th` = a factual, non-accusatory template ending in the mandatory
  "the auditor decides" disclaimer.
"""

from __future__ import annotations

from schemas import (
    FactorAssessment,
    RegulationReference,
    RiskAssessment,
    RiskFactor,
    RiskFactorType,
    RiskLevel,
)

# Equal weights (sum 1.0) — honest default with no calibration data. Tune here.
FACTOR_WEIGHTS: dict[RiskFactorType, float] = {
    RiskFactorType.BUDGET_DEVIATION: 0.20,
    RiskFactorType.VENDOR_CONCENTRATION: 0.20,
    RiskFactorType.TIMELINE_ANOMALY: 0.20,
    RiskFactorType.THRESHOLD_SPLITTING: 0.20,
    RiskFactorType.DOCUMENT_COMPLETENESS: 0.20,
}

# overall_score → risk_level bands (REQUIRES_INVESTIGATION is also forced by a
# HIGH-severity pre-check; see risk_level()).
_HIGH_BAND = 55.0
_MEDIUM_BAND = 30.0
_INVESTIGATE_BAND = 75.0

_FACTOR_TH: dict[RiskFactorType, str] = {
    RiskFactorType.BUDGET_DEVIATION: "ความเบี่ยงเบนของงบประมาณ",
    RiskFactorType.VENDOR_CONCENTRATION: "การกระจุกตัวของผู้รับจ้าง",
    RiskFactorType.TIMELINE_ANOMALY: "ความผิดปกติด้านระยะเวลา",
    RiskFactorType.THRESHOLD_SPLITTING: "การแบ่งซื้อแบ่งจ้าง",
    RiskFactorType.DOCUMENT_COMPLETENESS: "ความครบถ้วนของเอกสาร",
}


def _to_risk_factor(
    factor_type: RiskFactorType, assessment: FactorAssessment, weight: float
) -> RiskFactor:
    return RiskFactor(
        factor_type=factor_type,
        score=assessment.score,
        weight=weight,
        rationale_th=assessment.rationale_th,
        reasoning_steps=assessment.reasoning_steps,
        citations=assessment.citations,
    )


def overall_score(factors: list[RiskFactor]) -> float:
    return round(sum(f.score * f.weight for f in factors), 2)


def risk_level(score: float, *, has_high_severity_precheck: bool) -> RiskLevel:
    if has_high_severity_precheck or score >= _INVESTIGATE_BAND:
        return RiskLevel.REQUIRES_INVESTIGATION
    if score >= _HIGH_BAND:
        return RiskLevel.HIGH
    if score >= _MEDIUM_BAND:
        return RiskLevel.MEDIUM
    return RiskLevel.LOW


def _dedupe_regulations(
    references: list[RegulationReference],
) -> list[RegulationReference]:
    seen: set[str] = set()
    out: list[RegulationReference] = []
    for ref in references:
        if ref.regulation_id not in seen:
            seen.add(ref.regulation_id)
            out.append(ref)
    return out


def summary_th(score: float, level: RiskLevel, factors: list[RiskFactor]) -> str:
    top = sorted(factors, key=lambda f: f.score, reverse=True)[:2]
    top_names = " และ ".join(_FACTOR_TH[f.factor_type] for f in top)
    return (
        f"การประเมินความเสี่ยงรวมได้ {score:.0f} คะแนน จัดอยู่ในระดับ{level.label_th} "
        f"ปัจจัยที่ควรให้ความสำคัญในการตรวจสอบ ได้แก่ {top_names} "
        f"ผลนี้เป็นการชี้จุดที่ควรตรวจสอบเพิ่มเติมเท่านั้น "
        f"การวินิจฉัยขั้นสุดท้ายเป็นของผู้ตรวจสอบ"
    )


def build_assessment(
    scored: dict[RiskFactorType, FactorAssessment],
    *,
    has_high_severity_precheck: bool,
) -> RiskAssessment:
    """Assemble the per-factor assessments into a RiskAssessment. Weights are
    renormalized over the factors actually present, so a factor dropped after
    exhausting its re-asks never breaks the weights-sum-to-1.0 contract."""
    present = [ft for ft in RiskFactorType if ft in scored]
    if not present:
        raise ValueError("no factors scored — cannot build an assessment")
    weight_total = sum(FACTOR_WEIGHTS[ft] for ft in present)
    factors = [
        _to_risk_factor(ft, scored[ft], FACTOR_WEIGHTS[ft] / weight_total) for ft in present
    ]
    score = overall_score(factors)
    level = risk_level(score, has_high_severity_precheck=has_high_severity_precheck)
    references = _dedupe_regulations(
        [ref for fa in scored.values() for ref in fa.regulation_references]
    )
    return RiskAssessment(
        risk_level=level,
        overall_score=score,
        factors=factors,
        regulation_references=references,
        summary_th=summary_th(score, level, factors),
    )
