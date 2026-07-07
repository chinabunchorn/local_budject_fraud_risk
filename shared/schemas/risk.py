"""Enum-locked risk-result contract ("flag, never accuse").

`RiskAssessment` is exactly what the LLM must emit — its JSON schema is bound
to vLLM `guided_json` at decode time, so the verdict slot is grammatically
incapable of holding an accusation. `RiskResult` adds pipeline provenance and
is the shape stored in the `risk_results` JSONB column. The guardrails
validation stage is the ONLY write path into that table.

Free-text fields (`summary_th`, `rationale_th`) are re-checked post-hoc by the
guardrails non-accusation lexicon; this module enforces structure and ranges.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from schemas.chunk import Citation


class RiskLevel(StrEnum):
    """Closed verdict enum. There is no free-text verdict anywhere."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    REQUIRES_INVESTIGATION = "REQUIRES_INVESTIGATION"

    @property
    def label_th(self) -> str:
        return _RISK_LEVEL_TH[self]


_RISK_LEVEL_TH: dict[RiskLevel, str] = {
    RiskLevel.LOW: "ต่ำ",
    RiskLevel.MEDIUM: "ปานกลาง",
    RiskLevel.HIGH: "สูง",
    RiskLevel.REQUIRES_INVESTIGATION: "ควรตรวจสอบเพิ่มเติม",
}


class RiskFactorType(StrEnum):
    """The analyzable risk dimensions (one prompt template per factor)."""

    BUDGET_DEVIATION = "BUDGET_DEVIATION"
    VENDOR_CONCENTRATION = "VENDOR_CONCENTRATION"
    TIMELINE_ANOMALY = "TIMELINE_ANOMALY"
    THRESHOLD_SPLITTING = "THRESHOLD_SPLITTING"
    DOCUMENT_COMPLETENESS = "DOCUMENT_COMPLETENESS"


Score = Annotated[float, Field(ge=0, le=100)]
Weight = Annotated[float, Field(ge=0, le=1)]


class RegulationReference(BaseModel):
    """Link to a section of a known act. `regulation_id` must resolve to a row
    in the regulations index — guardrails re-checks existence before DB write."""

    model_config = ConfigDict(extra="forbid")

    regulation_id: str = Field(min_length=1)
    act_name_th: str = Field(min_length=1)
    section_no: str = Field(min_length=1)
    relevance_th: str = Field(min_length=1)


class RiskFactor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    factor_type: RiskFactorType
    score: Score
    weight: Weight
    rationale_th: str = Field(min_length=1)
    citations: list[Citation] = Field(default_factory=list)


class RiskAssessment(BaseModel):
    """Exactly what the model emits under `guided_json` at temperature 0."""

    model_config = ConfigDict(extra="forbid")

    risk_level: RiskLevel
    overall_score: Score
    factors: list[RiskFactor] = Field(min_length=1)
    regulation_references: list[RegulationReference] = Field(default_factory=list)
    summary_th: str = Field(min_length=1)

    @model_validator(mode="after")
    def _weights_sum_to_one(self) -> RiskAssessment:
        total = sum(f.weight for f in self.factors)
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"factor weights must sum to 1.0, got {total}")
        return self


class RiskResult(RiskAssessment):
    """Assessment + provenance — the validated row stored in `risk_results`."""

    project_id: UUID
    model_id: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)
    generated_at: datetime
