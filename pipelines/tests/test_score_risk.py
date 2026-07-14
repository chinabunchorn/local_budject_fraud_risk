"""score_project end-to-end against a stub model (no LANTA).

Exercises the real write path: stub guided-JSON → guardrails stage →
risk_results, plus the bounded re-ask. DB-backed; skips if the stack is down or
the regulation index is not ingested. Rows cascade away with the project_id
fixture.
"""

import json

import pytest
from sqlalchemy import text

from common.prompts import load_risk_scoring
from common.scoring_evidence import ProjectEvidence
from flows.score_risk import score_project

S37 = "fiscal-discipline-act-2561/s.37"


@pytest.fixture(autouse=True)
def _needs_regulation(engine):
    with engine.connect() as conn:
        present = conn.execute(
            text("SELECT count(*) FROM regulations WHERE regulation_code = :c"), {"c": S37}
        ).scalar()
    if not present:
        pytest.skip("regulation index not ingested — run flows.ingest_regulations first")


@pytest.fixture()
def citable_chunk(engine, project_id):
    """A real chunk under the throwaway project, so citations resolve."""
    with engine.begin() as conn:
        doc_id = conn.execute(
            text(
                """
                INSERT INTO documents
                    (project_id, scope, minio_key, filename, doc_type, parse_status)
                VALUES (:pid, 'PROJECT', :key, 'contract_summary.pdf',
                        'contract_summary', 'COMPLETED')
                RETURNING id
                """
            ),
            {"pid": project_id, "key": f"test/{project_id}/contract_summary.pdf"},
        ).scalar_one()
        chunk_id = conn.execute(
            text(
                "INSERT INTO chunks (document_id, chunk_index, text, page) "
                "VALUES (:d, 0, 'ข้อความสัญญาสำหรับการทดสอบ', 1) RETURNING id"
            ),
            {"d": doc_id},
        ).scalar_one()
    return str(chunk_id)


def _assessment(chunk_id: str, *, weight: float = 1.0) -> dict:
    return {
        "risk_level": "MEDIUM",
        "overall_score": 45.0,
        "summary_th": "พบข้อสังเกตที่ควรตรวจสอบเพิ่มเติม ผู้ตรวจสอบเป็นผู้วินิจฉัยขั้นสุดท้าย",
        "factors": [
            {
                "factor_type": "BUDGET_DEVIATION",
                "score": 45.0,
                "weight": weight,
                "rationale_th": "งบประมาณอยู่ในเกณฑ์ที่ควรตรวจสอบเพิ่มเติมตามหลักฐาน",
                "reasoning_steps": [
                    {
                        "step_type": "EVIDENCE",
                        "text_th": "ตรวจสอบข้อความในสัญญา",
                        "citations": [{"chunk_id": chunk_id}],
                    },
                    {"step_type": "OBSERVATION", "text_th": "พบราคาที่ควรพิจารณาเทียบเคียง"},
                    {"step_type": "INTERPRETATION", "text_th": "อาจต้องตรวจสอบความเหมาะสมเพิ่มเติม"},
                ],
                "citations": [{"chunk_id": chunk_id}],
            }
        ],
        "regulation_references": [
            {
                "regulation_id": S37,
                "act_name_th": "พระราชบัญญัติวินัยการเงินการคลังของรัฐ พ.ศ. ๒๕๖๑",
                "section_no": "37",
                "relevance_th": "การใช้จ่ายต้องคุ้มค่าและโปร่งใส",
            }
        ],
    }


def _evidence(project_id: str, chunk_id: str) -> ProjectEvidence:
    return ProjectEvidence(
        project_id=project_id,
        sub_district="ตำบลทดสอบ",
        project_name="โครงการทดสอบการให้คะแนน",
        fiscal_year=2568,
        budget_total="1,000,000.00",
        budget_lines="- ราคากลาง: 900,000.00 บาท",
        document_excerpts=f"[chunk_id: {chunk_id}] (เอกสาร: contract_summary)\nข้อความ",
        regulation_context=f"[regulation_id: {S37}] พ.ร.บ. วินัยการเงินการคลัง มาตรา 37",
    )


def test_valid_assessment_written_through_guardrails(engine, project_id, citable_chunk):
    bundle = load_risk_scoring("v1")
    ev = _evidence(project_id, citable_chunk)
    assessment = _assessment(citable_chunk)

    result = score_project(engine, lambda _m: json.dumps(assessment), bundle, ev, "mock/test")

    assert result == "scored"
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT risk_level, overall_score, model_id, prompt_version "
                "FROM risk_results WHERE project_id = :p"
            ),
            {"p": project_id},
        ).one()
    assert row.risk_level == "MEDIUM"
    assert float(row.overall_score) == 45.0
    assert row.model_id == "mock/test"
    assert row.prompt_version == "risk_scoring/v1"


def test_bounded_reask_recovers_from_a_rejected_first_answer(engine, project_id, citable_chunk):
    bundle = load_risk_scoring("v1")
    ev = _evidence(project_id, citable_chunk)
    # first answer violates the weight-sum rule (schema); second is valid
    answers = [
        json.dumps(_assessment(citable_chunk, weight=0.4)),
        json.dumps(_assessment(citable_chunk)),
    ]
    calls: list[list[dict]] = []

    def assess(messages):
        calls.append(messages)
        return answers.pop(0)

    result = score_project(engine, assess, bundle, ev, "mock/test")

    assert result == "scored"
    assert len(calls) == 2  # one re-ask
    # the re-ask carried the violation feedback forward
    assert any("ไม่ผ่านการตรวจสอบ" in m["content"] for m in calls[1])


def test_unrecoverable_answer_is_rejected_not_written(engine, project_id, citable_chunk):
    bundle = load_risk_scoring("v1")
    ev = _evidence(project_id, citable_chunk)
    bad = json.dumps(_assessment(citable_chunk, weight=0.4))  # always invalid

    result = score_project(engine, lambda _m: bad, bundle, ev, "mock/test")

    assert result == "rejected"
    with engine.connect() as conn:
        count = conn.execute(
            text("SELECT count(*) FROM risk_results WHERE project_id = :p"), {"p": project_id}
        ).scalar()
    assert count == 0
