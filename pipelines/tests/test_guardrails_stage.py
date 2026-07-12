"""Integration tests for the guardrails stage against the live stack.

Uses the REAL ingested regulation index (fiscal-discipline-act-2561 +
procurement-act-2560 must be present — Track A). Skips if the DB is down.
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import text

from common.guardrails_stage import GuardrailsRejection, validate_and_write

S37 = "fiscal-discipline-act-2561/s.37"
# Procurement Act หมวด ๒ sections carry a title containing "การทุจริต"
PROCUREMENT_CH2 = "procurement-act-2560/s.16"


@pytest.fixture(autouse=True)
def _needs_regulations(engine):
    with engine.connect() as conn:
        n = conn.execute(
            text("SELECT count(*) FROM regulations WHERE regulation_code IN (:a, :b)"),
            {"a": S37, "b": PROCUREMENT_CH2},
        ).scalar()
    if n != 2:
        pytest.skip("regulation index not ingested — run flows.ingest_regulations first")


def make_payload(project_id: str, **overrides) -> dict:
    base = {
        "risk_level": "HIGH",
        "overall_score": 78.0,
        "summary_th": "พบความผิดปกติด้านงบประมาณที่ควรตรวจสอบเพิ่มเติม ผู้ตรวจสอบเป็นผู้วินิจฉัยขั้นสุดท้าย",
        "factors": [
            {
                "factor_type": "BUDGET_DEVIATION",
                "score": 78.0,
                "weight": 1.0,
                "rationale_th": "งบประมาณสูงกว่าโครงการเทียบเคียงอย่างมีนัยสำคัญ",
                "reasoning_steps": [
                    {
                        "step_type": "EVIDENCE",
                        "text_th": "ตรวจสอบรายการงบประมาณ 12 รายการของโครงการ",
                    },
                    {
                        "step_type": "OBSERVATION",
                        "text_th": "ราคาต่อหน่วยสูงกว่าค่ากลาง 3 เท่า",
                    },
                    {
                        "step_type": "INTERPRETATION",
                        "text_th": "อาจเป็นความเบี่ยงเบนที่ควรตรวจสอบเพิ่มเติมตามมาตรา ๓๗",
                    },
                ],
            }
        ],
        "regulation_references": [
            {
                "regulation_id": S37,
                "act_name_th": "พระราชบัญญัติวินัยการเงินการคลังของรัฐ พ.ศ. ๒๕๖๑",
                "section_no": "37",
                "relevance_th": "การก่อหนี้ผูกพันต้องโปร่งใสและคุ้มค่า",
            }
        ],
        "project_id": project_id,
        "model_id": "scb10x/typhoon2.5-qwen3-30b-a3b",
        "prompt_version": "risk_scoring/v1",
        "generated_at": datetime.now(UTC).isoformat(),
    }
    return {**base, **overrides}


class TestHappyPath:
    def test_valid_result_written_and_denormalized(self, engine, project_id):
        result = validate_and_write(engine, make_payload(project_id))
        assert result.risk_level.value == "HIGH"
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT risk_level, overall_score, result->>'summary_th' AS summary "
                    "FROM risk_results WHERE project_id = :p"
                ),
                {"p": project_id},
            ).one()
        assert row.risk_level == "HIGH"
        assert float(row.overall_score) == 78.0
        assert "ผู้ตรวจสอบ" in row.summary

    def test_rerun_upserts_single_row(self, engine, project_id):
        validate_and_write(engine, make_payload(project_id))
        validate_and_write(
            engine, make_payload(project_id, overall_score=55.0, risk_level="MEDIUM")
        )
        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT overall_score FROM risk_results WHERE project_id = :p"),
                {"p": project_id},
            ).fetchall()
        assert len(rows) == 1
        assert float(rows[0].overall_score) == 55.0


class TestRejections:
    def test_unknown_regulation_reference_rejected(self, engine, project_id):
        payload = make_payload(project_id)
        payload["regulation_references"][0]["regulation_id"] = "no-such-act/s.999"
        with pytest.raises(GuardrailsRejection, match="does not resolve"):
            validate_and_write(engine, payload)

    def test_banned_lexicon_rejected_with_location(self, engine, project_id):
        payload = make_payload(project_id)
        payload["factors"][0]["reasoning_steps"][2]["text_th"] = "รูปแบบนี้ชี้ว่าเป็นการทุจริต"
        with pytest.raises(GuardrailsRejection) as exc:
            validate_and_write(engine, payload)
        assert any("reasoning_steps[2]" in v for v in exc.value.violations)

    def test_quoting_cited_regulation_title_is_allowed(self, engine, project_id):
        """หมวด ๒'s real title contains 'การทุจริต' — quoting a CITED regulation
        is the one sanctioned use of those strings."""
        payload = make_payload(project_id)
        payload["regulation_references"].append(
            {
                "regulation_id": PROCUREMENT_CH2,
                "act_name_th": "พระราชบัญญัติการจัดซื้อจัดจ้างและการบริหารพัสดุภาครัฐ พ.ศ. ๒๕๖๐",
                "section_no": "16",
                "relevance_th": "แนวทางการมีส่วนร่วมของภาคประชาชน",
            }
        )
        payload["summary_th"] = (
            "ควรพิจารณาแนวทางตามหมวด ๒ การมีส่วนร่วมของภาคประชาชนและผู้ประกอบการ"
            "ในการป้องกันการทุจริต ทั้งนี้ผู้ตรวจสอบเป็นผู้วินิจฉัยขั้นสุดท้าย"
        )
        result = validate_and_write(engine, payload)
        assert result.overall_score == 78.0

    def test_nonexistent_citation_rejected(self, engine, project_id):
        payload = make_payload(project_id)
        payload["factors"][0]["reasoning_steps"][0]["citations"] = [
            {"chunk_id": str(uuid4())}
        ]
        with pytest.raises(GuardrailsRejection, match="chunk .* does not exist"):
            validate_and_write(engine, payload)

    def test_schema_violation_rejected(self, engine, project_id):
        with pytest.raises(GuardrailsRejection, match="schema"):
            validate_and_write(engine, make_payload(project_id, risk_level="ทุจริต"))

    def test_bad_weight_sum_rejected(self, engine, project_id):
        payload = make_payload(project_id)
        payload["factors"][0]["weight"] = 0.4
        with pytest.raises(GuardrailsRejection, match="schema"):
            validate_and_write(engine, payload)

    def test_unknown_project_rejected(self, engine, project_id):
        with pytest.raises(GuardrailsRejection, match="integrity"):
            validate_and_write(engine, make_payload(str(uuid4())))
