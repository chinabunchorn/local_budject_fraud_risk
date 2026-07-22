"""score_project end-to-end against a stub model (no LANTA), per-factor (v2).

Exercises the real write path: per-factor guided-JSON → citation/regulation
filtering → deterministic aggregation → guardrails stage → risk_results, plus
the per-factor re-ask. DB-backed; skips if the stack is down or the regulation
index is not ingested. Rows cascade away with the project_id fixture.
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


def _factor(chunk_id: str, score: float = 50.0, extra_citations: list | None = None) -> dict:
    return {
        "score": score,
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
        "citations": [{"chunk_id": chunk_id}, *(extra_citations or [])],
        "regulation_references": [
            {
                "regulation_id": S37,
                "act_name_th": "พระราชบัญญัติวินัยการเงินการคลังของรัฐ พ.ศ. ๒๕๖๑",
                "section_no": "37",
                "relevance_th": "การใช้จ่ายต้องคุ้มค่าและโปร่งใส",
            }
        ],
    }


def _evidence(project_id: str, chunk_id: str, *, high_severity: bool = False) -> ProjectEvidence:
    return ProjectEvidence(
        project_id=project_id,
        sub_district="ตำบลทดสอบ",
        project_name="โครงการทดสอบการให้คะแนน",
        fiscal_year=2568,
        budget_total="1,000,000.00",
        budget_lines="- ราคากลาง: 900,000.00 บาท",
        document_excerpts=f"[chunk_id: {chunk_id}] (เอกสาร: contract_summary)\nข้อความ",
        regulation_context=f"[regulation_id: {S37}] พ.ร.บ. วินัยการเงินการคลัง มาตรา 37",
        excerpt_chunk_ids=[chunk_id],
        regulation_ids=[S37],
        has_high_severity_precheck=high_severity,
    )


def test_five_factors_aggregate_and_write(engine, project_id, citable_chunk):
    bundle = load_risk_scoring("v2")
    ev = _evidence(project_id, citable_chunk)
    calls = {"n": 0}

    def assess(_messages):
        calls["n"] += 1
        return json.dumps(_factor(citable_chunk, score=50.0))

    assert score_project(engine, assess, bundle, ev, "mock/test") == "scored"
    assert calls["n"] == 5  # one call per factor
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT risk_level, overall_score, jsonb_array_length(result->'factors') n "
                "FROM risk_results WHERE project_id = :p"
            ),
            {"p": project_id},
        ).one()
    assert row.n == 5
    assert float(row.overall_score) == 50.0  # weighted mean of equal-weight 50s
    assert row.risk_level == "MEDIUM"  # 30 <= 50 < 55


def test_high_severity_precheck_forces_requires_investigation(engine, project_id, citable_chunk):
    bundle = load_risk_scoring("v2")
    ev = _evidence(project_id, citable_chunk, high_severity=True)
    # low factor scores, but a HIGH-severity pre-check overrides the band
    assert score_project(engine, assess=lambda _m: json.dumps(_factor(citable_chunk, 10.0)),
                         bundle=bundle, ev=ev, model_id="mock/test") == "scored"
    with engine.connect() as conn:
        level = conn.execute(
            text("SELECT risk_level FROM risk_results WHERE project_id = :p"), {"p": project_id}
        ).scalar()
    assert level == "REQUIRES_INVESTIGATION"


def test_per_factor_reask_recovers(engine, project_id, citable_chunk):
    bundle = load_risk_scoring("v2")
    ev = _evidence(project_id, citable_chunk)
    calls = {"n": 0}

    def assess(_messages):
        calls["n"] += 1
        if calls["n"] == 1:  # first factor's first attempt is unparseable
            return "{ not valid json"
        return json.dumps(_factor(citable_chunk))

    assert score_project(engine, assess, bundle, ev, "mock/test") == "scored"
    assert calls["n"] == 6  # 5 factors + 1 re-ask


def test_hallucinated_citation_is_filtered_not_rejected(engine, project_id, citable_chunk):
    bundle = load_risk_scoring("v2")
    ev = _evidence(project_id, citable_chunk)
    fake = "00000000-0000-0000-0000-000000000000"

    def assess(_messages):
        return json.dumps(_factor(citable_chunk, extra_citations=[{"chunk_id": fake}]))

    # the fake citation is dropped before guardrails, so the write still succeeds
    assert score_project(engine, assess, bundle, ev, "mock/test") == "scored"
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT result::text FROM risk_results WHERE project_id = :p"), {"p": project_id}
        ).scalar()
    assert fake not in result
    assert citable_chunk in result


def test_all_factors_unparseable_is_rejected(engine, project_id, citable_chunk):
    bundle = load_risk_scoring("v2")
    ev = _evidence(project_id, citable_chunk)

    assert score_project(engine, lambda _m: "not json", bundle, ev, "mock/test") == "rejected"
    with engine.connect() as conn:
        count = conn.execute(
            text("SELECT count(*) FROM risk_results WHERE project_id = :p"), {"p": project_id}
        ).scalar()
    assert count == 0
