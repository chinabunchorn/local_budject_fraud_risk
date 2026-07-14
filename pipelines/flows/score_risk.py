"""Risk-scoring flow (Phase G) — per-factor LLM scoring, offline-precomputed.

The 8192-token serving window cannot hold all five factors' reasoning in one
call, so each project is scored one factor at a time (prompts risk_scoring/v2):

  per factor: assemble evidence (Phase-F facts + precheck findings + real
  chunk_ids + cited regulations) → vLLM `guided_json` bound to
  `FactorAssessment` (temp 0, tunnel, Langfuse-traced) → filter the model's
  citations/regulation refs down to what was actually offered (so a
  hallucinated reference can't fail guardrails) → keep the factor.

Then DETERMINISTIC aggregation (common/aggregation.py) combines the factors:
weighted overall_score, banded risk_level (a HIGH-severity pre-check forces
REQUIRES_INVESTIGATION), templated summary — no LLM in the verdict. The
assembled RiskResult goes through the guardrails stage, the sole write path
into risk_results.

Runs during an attended LANTA serving window. `assess` is injectable so the
flow is verifiable against a stub without a live model.

Run (tunnel up):  cd pipelines && python -m flows.score_risk
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime

import httpx
from prefect import flow, get_run_logger
from pydantic import ValidationError
from schemas import FactorAssessment, RiskFactorType
from sqlalchemy import Engine, create_engine, text

from common.aggregation import build_assessment
from common.guardrails_stage import GuardrailsRejection, validate_and_write
from common.observability import langfuse_tracer
from common.prompts import PromptBundle, build_factor_messages, load_risk_scoring
from common.scoring_evidence import ProjectEvidence, assemble_evidence
from common.settings import database_url, vllm_base_url, vllm_model_id, vllm_served_model
from common.vllm import VLLMClient

logger = logging.getLogger(__name__)

# messages -> guided_json content string (bound to FactorAssessment by the client)
Assess = Callable[[list[dict[str, str]]], str]

_FACTOR_SCHEMA = FactorAssessment.model_json_schema()
# one factor completes in ~1k tokens; cap bounds the whitespace-loop degeneration
_MAX_FACTOR_TOKENS = 2048
# total attempts per factor (a fresh generation clears the intermittent loop)
_FACTOR_ATTEMPTS = 3


def _default_assess() -> Assess:
    # request uses the served alias; provenance (model_id) records the real model
    client = VLLMClient(vllm_base_url(), vllm_served_model(), tracer=langfuse_tracer())

    def assess(messages: list[dict[str, str]]) -> str:
        return client.generate_json(
            messages, _FACTOR_SCHEMA, name="risk_scoring", max_tokens=_MAX_FACTOR_TOKENS
        )

    return assess


def _filter_references(factor: FactorAssessment, ev: ProjectEvidence) -> FactorAssessment:
    """Drop any citation / regulation ref the evidence did not actually offer —
    keeps the guardrails citation-existence and regulation-resolution checks
    from failing on a hallucinated reference (the reasoning step survives, just
    without an unsupported pointer)."""
    chunks = set(ev.excerpt_chunk_ids)
    regs = set(ev.regulation_ids)

    def kept(citations):
        return [c for c in citations if str(c.chunk_id) in chunks]

    steps = [
        step.model_copy(update={"citations": kept(step.citations)})
        for step in factor.reasoning_steps
    ]
    return factor.model_copy(
        update={
            "citations": kept(factor.citations),
            "reasoning_steps": steps,
            "regulation_references": [
                r for r in factor.regulation_references if r.regulation_id in regs
            ],
        }
    )


def _score_factor(
    assess: Assess,
    bundle: PromptBundle,
    ev: ProjectEvidence,
    factor_type: RiskFactorType,
    attempts: int,
) -> FactorAssessment | None:
    messages = build_factor_messages(
        bundle,
        factor_type,
        sub_district=ev.sub_district,
        project_name=ev.project_name,
        fiscal_year=ev.fiscal_year,
        budget_total=ev.budget_total,
        budget_lines=ev.budget_lines,
        document_excerpts=ev.document_excerpts,
        regulation_context=ev.regulation_context,
    )
    # A fresh generation, not a feedback re-ask: the dominant failure is an
    # intermittent whitespace-loop that truncates the JSON (invalid), and
    # appending that truncated garbage would only bloat the next prompt. Temp 0
    # is non-deterministic under TP2 batching, so a plain retry clears it.
    for _ in range(attempts):
        content = assess(messages)
        try:
            return _filter_references(FactorAssessment.model_validate_json(content), ev)
        except ValidationError:
            continue
    return None


def score_project(
    engine: Engine,
    assess: Assess,
    bundle: PromptBundle,
    ev: ProjectEvidence,
    model_id: str,
    *,
    generated_at: datetime | None = None,
    attempts: int = _FACTOR_ATTEMPTS,
) -> str:
    """Score every factor for one project, aggregate deterministically, and
    write through the guardrails stage. Returns 'scored' or 'rejected'."""
    generated_at = generated_at or datetime.now(UTC)

    scored: dict[RiskFactorType, FactorAssessment] = {}
    for factor_type in RiskFactorType:
        factor = _score_factor(assess, bundle, ev, factor_type, attempts)
        if factor is not None:
            scored[factor_type] = factor
        else:
            logger.warning("%s: factor %s failed to parse — dropped", ev.project_name, factor_type)
    if not scored:
        return "rejected"

    assessment = build_assessment(
        scored, has_high_severity_precheck=ev.has_high_severity_precheck
    )
    payload = assessment.model_dump(mode="json") | {
        "project_id": ev.project_id,
        "model_id": model_id,
        "prompt_version": bundle.version,
        "generated_at": generated_at.isoformat(),
    }
    try:
        validate_and_write(engine, payload)
        return "scored"
    except GuardrailsRejection as rejection:
        logger.warning("%s: guardrails rejected — %s", ev.project_name, rejection.violations)
        return "rejected"


@flow(name="score-risk")
def score_risk(
    prompt_version: str = "v2", limit: int | None = None, rescore: bool = False
) -> dict[str, int]:
    """Score every project with a precheck row. Idempotent and RESUMABLE: a
    project already in risk_results for this (prompt_version, model_id) is
    skipped unless `rescore=True`, so a run interrupted by a tunnel drop just
    continues where it left off on re-run."""
    flow_logger = get_run_logger()
    bundle = load_risk_scoring(prompt_version)
    model_id = vllm_model_id()
    assess = _default_assess()
    engine = create_engine(database_url())
    tally = {"scored": 0, "rejected": 0, "skipped": 0}
    try:
        with engine.connect() as conn:
            project_ids = [
                str(r.project_id)
                for r in conn.execute(
                    text("SELECT project_id FROM precheck_results ORDER BY project_id")
                )
            ]
            done = {
                str(r.project_id)
                for r in conn.execute(
                    text(
                        "SELECT project_id FROM risk_results "
                        "WHERE prompt_version = :pv AND model_id = :m"
                    ),
                    {"pv": bundle.version, "m": model_id},
                )
            }
        if limit is not None:
            project_ids = project_ids[:limit]
        for project_id in project_ids:
            if project_id in done and not rescore:
                tally["skipped"] += 1
                continue
            ev = assemble_evidence(engine, project_id, bundle)
            if ev is None:
                tally["skipped"] += 1
                continue
            try:
                outcome = score_project(engine, assess, bundle, ev, model_id)
            except httpx.HTTPError as exc:
                flow_logger.error(
                    "LLM endpoint error (tunnel down?) after %d scored — re-run to resume: %s",
                    tally["scored"], exc,
                )
                break
            tally[outcome] += 1
            flow_logger.info("%s: %s", ev.project_name, outcome)
    finally:
        engine.dispose()
    flow_logger.info("score-risk summary: %s", tally)
    return tally


if __name__ == "__main__":
    score_risk()
