"""Risk-scoring flow (Phase G) — the LLM path, offline-precomputed.

Per project: assemble deterministic evidence (Phase-F facts + real chunk_ids +
regulation context) → v1 Thai prompt → vLLM `guided_json` (bound to
`schemas.RiskAssessment`, temperature 0, through the SSH tunnel, Langfuse-
traced) → the guardrails stage, THE only write path into `risk_results`. A
rejected result is fed back once with its violation list (bounded re-ask)
before it is dropped — nothing unvalidated ever reaches the table.

Runs during an attended LANTA serving window (2FA blocks unattended tunnel
bring-up). The `assess` callable is injectable so the flow is verifiable
against a stub without a live model.

Run (tunnel up):  cd pipelines && python -m flows.score_risk
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime

from prefect import flow, get_run_logger
from schemas import RiskAssessment
from sqlalchemy import Engine, create_engine, text

from common.guardrails_stage import GuardrailsRejection, validate_and_write
from common.observability import langfuse_tracer
from common.prompts import PromptBundle, build_messages, load_risk_scoring
from common.scoring_evidence import ProjectEvidence, assemble_evidence
from common.settings import database_url, vllm_base_url, vllm_model
from common.vllm import VLLMClient

# messages -> guided_json content string (bound to RiskAssessment by the client)
Assess = Callable[[list[dict[str, str]]], str]

_SCHEMA = RiskAssessment.model_json_schema()


def _default_assess() -> Assess:
    client = VLLMClient(vllm_base_url(), vllm_model(), tracer=langfuse_tracer())

    def assess(messages: list[dict[str, str]]) -> str:
        return client.generate_json(messages, _SCHEMA, name="risk_scoring")

    return assess


def _messages_for(bundle: PromptBundle, ev: ProjectEvidence) -> list[dict[str, str]]:
    return build_messages(
        bundle,
        sub_district=ev.sub_district,
        project_name=ev.project_name,
        fiscal_year=ev.fiscal_year,
        budget_total=ev.budget_total,
        budget_lines=ev.budget_lines,
        document_excerpts=ev.document_excerpts,
        regulation_context=ev.regulation_context,
    )


def _reask(violations: list[str]) -> str:
    return (
        "ผลลัพธ์ก่อนหน้าไม่ผ่านการตรวจสอบด้วยเหตุผลต่อไปนี้:\n"
        + "\n".join(f"- {v}" for v in violations)
        + "\nโปรดแก้ไขให้ถูกต้องและตอบเป็น JSON ตาม schema เดิมอีกครั้ง"
    )


def score_project(
    engine: Engine,
    assess: Assess,
    bundle: PromptBundle,
    ev: ProjectEvidence,
    model_id: str,
    *,
    generated_at: datetime | None = None,
    max_reasks: int = 1,
) -> str:
    """Score one project and write it through the guardrails stage. Returns
    'scored' or 'rejected' (after exhausting the bounded re-ask)."""
    messages = _messages_for(bundle, ev)
    generated_at = generated_at or datetime.now(UTC)
    violations: list[str] = []
    for attempt in range(max_reasks + 1):
        content = assess(messages)
        try:
            payload = json.loads(content)
        except json.JSONDecodeError as exc:
            violations = [f"invalid JSON: {exc}"]
        else:
            payload |= {
                "project_id": ev.project_id,
                "model_id": model_id,
                "prompt_version": bundle.version,
                "generated_at": generated_at.isoformat(),
            }
            try:
                validate_and_write(engine, payload)
                return "scored"
            except GuardrailsRejection as rejection:
                violations = rejection.violations
        if attempt < max_reasks:
            messages = [
                *messages,
                {"role": "assistant", "content": content},
                {"role": "user", "content": _reask(violations)},
            ]
    return "rejected"


@flow(name="score-risk")
def score_risk(prompt_version: str = "v1", limit: int | None = None) -> dict[str, int]:
    logger = get_run_logger()
    bundle = load_risk_scoring(prompt_version)
    model_id = vllm_model()
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
        if limit is not None:
            project_ids = project_ids[:limit]
        for project_id in project_ids:
            ev = assemble_evidence(engine, project_id, bundle)
            if ev is None:
                tally["skipped"] += 1
                continue
            outcome = score_project(engine, assess, bundle, ev, model_id)
            tally[outcome] += 1
            logger.info("%s: %s", ev.project_name, outcome)
    finally:
        engine.dispose()
    logger.info("score-risk summary: %s", tally)
    return tally


if __name__ == "__main__":
    score_risk()
