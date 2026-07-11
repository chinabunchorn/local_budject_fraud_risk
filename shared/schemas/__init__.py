"""Mission 3 data contracts — the single source of truth.

Backend, pipelines, and guardrails all import from here.
Never duplicate a schema definition elsewhere.
"""

from schemas.chunk import EMBEDDING_DIM, Chunk, Citation
from schemas.feedback import Feedback, FeedbackSentiment
from schemas.risk import (
    ReasoningStep,
    ReasoningStepType,
    RegulationReference,
    RiskAssessment,
    RiskFactor,
    RiskFactorType,
    RiskLevel,
    RiskResult,
)

__all__ = [
    "EMBEDDING_DIM",
    "Chunk",
    "Citation",
    "Feedback",
    "FeedbackSentiment",
    "ReasoningStep",
    "ReasoningStepType",
    "RegulationReference",
    "RiskAssessment",
    "RiskFactor",
    "RiskFactorType",
    "RiskLevel",
    "RiskResult",
]
