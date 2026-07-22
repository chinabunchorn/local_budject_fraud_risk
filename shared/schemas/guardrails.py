"""Contract-level "flag, never accuse" lexicon — shared by every validator.

The closed RiskLevel enum makes an accusatory *verdict* grammatically
impossible at decode time; this module covers the free-text fields
(`summary_th`, `rationale_th`, `ReasoningStep.text_th`,
`RegulationReference.relevance_th`), which the schema cannot constrain.

Banned terms are rejected wherever they appear as the model's own words.
The single exemption: quoting the title of a cited regulation (e.g. the
Procurement Act's หมวด ๒ "...ในการป้องกันการทุจริต") — callers pass those
titles as `allowed_phrases`, and only text OUTSIDE them is scanned.

Both the batch guardrails stage (pipelines) and the chat output guardrails
(backend) import from here — one lexicon, one behavior.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from schemas.risk import RiskAssessment

# Verdict-language ban per CLAUDE.md constraint 3. Thai terms are matched as
# substrings (Thai has no word boundaries); English case-insensitively.
BANNED_TERMS: tuple[str, ...] = ("ทุจริต", "ฉ้อโกง", "โกง", "fraud", "corruption")


class LexiconViolation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    location: str  # e.g. "factors[1].reasoning_steps[2].text_th"
    term: str


def find_banned_terms(text: str, allowed_phrases: tuple[str, ...] = ()) -> list[str]:
    scrubbed = text
    for phrase in allowed_phrases:
        if phrase:
            scrubbed = scrubbed.replace(phrase, " ")
    lowered = scrubbed.lower()
    return [term for term in BANNED_TERMS if term in scrubbed or term in lowered]


def lexicon_violations(
    assessment: RiskAssessment, allowed_phrases: tuple[str, ...] = ()
) -> list[LexiconViolation]:
    """Scan every free-text field of an assessment (incl. the reasoning chain
    shown in the frontend). Empty list = clean."""
    texts: list[tuple[str, str]] = [("summary_th", assessment.summary_th)]
    for i, factor in enumerate(assessment.factors):
        texts.append((f"factors[{i}].rationale_th", factor.rationale_th))
        texts.extend(
            (f"factors[{i}].reasoning_steps[{j}].text_th", step.text_th)
            for j, step in enumerate(factor.reasoning_steps)
        )
    texts.extend(
        (f"regulation_references[{i}].relevance_th", ref.relevance_th)
        for i, ref in enumerate(assessment.regulation_references)
    )
    return [
        LexiconViolation(location=location, term=term)
        for location, text in texts
        for term in find_banned_terms(text, allowed_phrases)
    ]
