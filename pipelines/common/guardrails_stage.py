"""Guardrails validation stage — THE ONLY write path into `risk_results`.

Validation order (all violations collected, not fail-fast, so a rejected
result reports everything wrong with it at once — that report is what gets
traced to Langfuse and used for the re-ask):

1. Schema / ranges / enum / weight-sum — `schemas.RiskResult` (pydantic).
2. Regulation references resolve: every `regulation_id` must exist in the
   `regulations` table (built by the ingest_regulations flow).
3. Non-accusation lexicon over every free-text field — with the resolved
   references' own act names and section titles as the ONLY allowed
   quotations (e.g. the Procurement Act chapter title containing "การทุจริต").
4. Citation existence: every cited chunk_id must exist in `chunks`.

Only a result passing all four is upserted (idempotent on
project_id + prompt_version + model_id, per the table's unique key).
"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError
from schemas import RiskResult, lexicon_violations
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError


class GuardrailsRejection(Exception):
    """The result must not reach the database. `violations` says why."""

    def __init__(self, violations: list[str]) -> None:
        self.violations = violations
        super().__init__("; ".join(violations))


_UPSERT = text(
    """
    INSERT INTO risk_results
        (project_id, result, risk_level, overall_score, model_id, prompt_version, generated_at)
    VALUES
        (:project_id, CAST(:result AS jsonb), :risk_level, :overall_score,
         :model_id, :prompt_version, :generated_at)
    ON CONFLICT (project_id, prompt_version, model_id) DO UPDATE SET
        result = EXCLUDED.result,
        risk_level = EXCLUDED.risk_level,
        overall_score = EXCLUDED.overall_score,
        generated_at = EXCLUDED.generated_at,
        validated_at = now()
    """
)


def validate_and_write(engine: Engine, payload: dict[str, Any] | RiskResult) -> RiskResult:
    """Validate a raw model output (+ provenance) and upsert it. Raises
    GuardrailsRejection with the full violation list on any failure."""
    try:
        result = (
            payload
            if isinstance(payload, RiskResult)
            else RiskResult.model_validate(payload)
        )
    except ValidationError as exc:
        raise GuardrailsRejection(
            [f"schema: {err['loc']} — {err['msg']}" for err in exc.errors()]
        ) from exc

    violations: list[str] = []
    with engine.connect() as conn:
        # regulation references must resolve
        codes = sorted({ref.regulation_id for ref in result.regulation_references})
        allowed_phrases: tuple[str, ...] = ()
        if codes:
            rows = conn.execute(
                text(
                    "SELECT regulation_code, act_name_th, section_title_th "
                    "FROM regulations WHERE regulation_code = ANY(CAST(:codes AS text[]))"
                ),
                {"codes": codes},
            ).fetchall()
            found = {row.regulation_code for row in rows}
            violations.extend(
                f"regulation: {code!r} does not resolve to a known regulation"
                for code in codes
                if code not in found
            )
            allowed_phrases = tuple(
                {row.act_name_th for row in rows}
                | {row.section_title_th for row in rows if row.section_title_th}
            )

        # lexicon over all free text (quoting resolved regulation titles is allowed)
        violations.extend(
            f"lexicon: banned term {v.term!r} in {v.location}"
            for v in lexicon_violations(result, allowed_phrases)
        )

        # cited chunks must exist
        chunk_ids = sorted(
            {
                str(citation.chunk_id)
                for factor in result.factors
                for citation in (
                    *factor.citations,
                    *(c for step in factor.reasoning_steps for c in step.citations),
                )
            }
        )
        if chunk_ids:
            existing = {
                str(row.id)
                for row in conn.execute(
                    text("SELECT id FROM chunks WHERE id = ANY(CAST(:ids AS uuid[]))"),
                    {"ids": chunk_ids},
                )
            }
            violations.extend(
                f"citation: chunk {cid} does not exist"
                for cid in chunk_ids
                if cid not in existing
            )

    if violations:
        raise GuardrailsRejection(violations)

    try:
        with engine.begin() as conn:
            conn.execute(
                _UPSERT,
                {
                    "project_id": str(result.project_id),
                    "result": result.model_dump_json(),
                    "risk_level": result.risk_level.value,
                    "overall_score": result.overall_score,
                    "model_id": result.model_id,
                    "prompt_version": result.prompt_version,
                    "generated_at": result.generated_at,
                },
            )
    except IntegrityError as exc:  # e.g. project_id not in projects
        raise GuardrailsRejection([f"integrity: {exc.orig}"]) from exc
    return result
