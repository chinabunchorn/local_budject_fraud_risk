"""Mission 3 data contracts — the single source of truth.

Backend, pipelines, and guardrails all import from here.
Never duplicate a schema definition elsewhere.
"""

from schemas.chunk import EMBEDDING_DIM, Chunk, Citation
from schemas.feedback import Feedback, FeedbackSentiment
from schemas.guardrails import (
    BANNED_TERMS,
    LexiconViolation,
    find_banned_terms,
    lexicon_violations,
)
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
    "BANNED_TERMS",
    "EMBEDDING_DIM",
    "Chunk",
    "Citation",
    "Feedback",
    "FeedbackSentiment",
    "LexiconViolation",
    "find_banned_terms",
    "lexicon_violations",
    "ReasoningStep",
    "ReasoningStepType",
    "RegulationReference",
    "RiskAssessment",
    "RiskFactor",
    "RiskFactorType",
    "RiskLevel",
    "RiskResult",
]
