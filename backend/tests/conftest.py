"""Shared fixtures — house convention (see pipelines/tests): DB-backed tests
run against the live compose PostgreSQL with throwaway rows and skip cleanly
when the stack is down. Requires migrations 0001–0005 applied."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from schemas.chunk import Citation
from schemas.risk import (
    ReasoningStep,
    ReasoningStepType,
    RegulationReference,
    RiskFactor,
    RiskFactorType,
    RiskLevel,
    RiskResult,
)
from sqlalchemy import create_engine, text

from app.core.settings import get_settings

TEST_PREFIX = "gordrail-api-test"
REG_CODE = f"{TEST_PREFIX}-act-2561/s.99"


@pytest.fixture(scope="session")
def engine():
    eng = create_engine(get_settings().database_url)
    try:
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
            has_users = conn.execute(text("SELECT to_regclass('users')")).scalar()
    except Exception:
        pytest.skip("PostgreSQL not reachable — start the compose stack and source .env")
    if has_users is None:
        pytest.skip("users table missing — run alembic upgrade head (migration 0005)")
    yield eng
    eng.dispose()


@pytest.fixture(scope="session")
def seeded(engine):
    """Two fiscal years of one throwaway sub-district: projects, bids,
    prechecks, a validated RiskResult, a document+chunk, a regulation, users."""
    from app.core.security import hash_password

    ids: dict[str, uuid.UUID | str] = {}
    password_hash = hash_password("test-password-123")

    with engine.begin() as conn:
        sd = conn.execute(
            text(
                "INSERT INTO sub_districts (name_th, district_th, province_th) VALUES "
                "('ตำบลทดสอบเอพีไอ', 'อำเภอทดสอบ', 'จังหวัดทดสอบ') RETURNING id"
            )
        ).scalar_one()
        ids["sub_district"] = sd

        p_2566 = conn.execute(
            text(
                "INSERT INTO projects (sub_district_id, name_th, fiscal_year, budget_total, "
                "contract_price, reference_price, procurement_method) VALUES "
                "(:sd, 'โครงการถนนทดสอบเอพีไอ หมู่ ๙', 2566, 1000000, 985000, 990000, 'SPECIFIC') "
                "RETURNING id"
            ),
            {"sd": sd},
        ).scalar_one()
        p_2567 = conn.execute(
            text(
                "INSERT INTO projects (sub_district_id, name_th, fiscal_year, budget_total, "
                "contract_price, reference_price, procurement_method) VALUES "
                "(:sd, 'โครงการถนนทดสอบเอพีไอ หมู่ ๙ ระยะสอง', 2567, 2000000, 1950000, 1980000, "
                "'E_BIDDING') RETURNING id"
            ),
            {"sd": sd},
        ).scalar_one()
        ids["project_2566"], ids["project_2567"] = p_2566, p_2567

        for pid, bidder, amount, winner in [
            (p_2566, "หจก. ทดสอบก่อสร้าง", 985000, True),
            (p_2567, "หจก. ทดสอบก่อสร้าง", 1950000, True),
            (p_2567, "บจก. คู่เทียบทดสอบ", 1990000, False),
        ]:
            conn.execute(
                text(
                    "INSERT INTO bids (project_id, bidder_name_th, bid_amount, is_winner) "
                    "VALUES (:p, :b, :a, :w)"
                ),
                {"p": pid, "b": bidder, "a": amount, "w": winner},
            )

        conn.execute(
            text(
                "INSERT INTO precheck_results (project_id, checks) "
                "VALUES (:p, CAST(:c AS jsonb))"
            ),
            {
                "p": p_2567,
                "c": '[{"name": "yoy_budget_anomaly", "status": "FLAG", '
                '"detail": "งบประมาณโครงการต่อเนื่องเพิ่มขึ้น 100% จากปีก่อน", '
                '"values": {"growth_pct": 100.0}, "severity": "HIGH"}, '
                '{"name": "boq_vs_bk01", "status": "NA", "detail": "ไม่มียอดรวมตัวเลข", '
                '"values": {}}]',
            },
        )

        doc = conn.execute(
            text(
                "INSERT INTO documents (project_id, minio_key, filename, doc_type, source, "
                "parse_status, scope) VALUES (:p, :k, 'contract_summary_test.pdf', "
                "'contract_summary', 'BORN_DIGITAL', 'COMPLETED', 'PROJECT') RETURNING id"
            ),
            {"p": p_2567, "k": f"{TEST_PREFIX}/{uuid.uuid4()}.pdf"},
        ).scalar_one()
        chunk = conn.execute(
            text(
                "INSERT INTO chunks (document_id, chunk_index, text, page) VALUES "
                "(:d, 0, 'สรุปสัญญาจ้าง วงเงิน 1,950,000 บาท ผู้รับจ้าง หจก. ทดสอบก่อสร้าง', 1) "
                "RETURNING id"
            ),
            {"d": doc},
        ).scalar_one()
        ids["document"], ids["chunk"] = doc, chunk

        conn.execute(
            text(
                "INSERT INTO regulations (regulation_code, act_name_th, section_no, text) VALUES "
                "(:c, 'พระราชบัญญัติทดสอบ พ.ศ. ๒๕๖๑', 'มาตรา ๙๙', "
                "'การจัดซื้อจัดจ้างต้องดำเนินการอย่างเปิดเผยและตรวจสอบได้')"
            ),
            {"c": REG_CODE},
        )

        risk = RiskResult(
            project_id=p_2567,
            model_id="scb10x/typhoon2.5-qwen3-30b-a3b",
            prompt_version=f"{TEST_PREFIX}/v1",
            generated_at=datetime.now(UTC),
            risk_level=RiskLevel.REQUIRES_INVESTIGATION,
            overall_score=72.5,
            summary_th="พบการเพิ่มขึ้นของงบประมาณอย่างมีนัยสำคัญ ควรตรวจสอบเพิ่มเติมโดยผู้ตรวจสอบ",
            factors=[
                RiskFactor(
                    factor_type=RiskFactorType.BUDGET_DEVIATION,
                    score=72.5,
                    weight=1.0,
                    rationale_th="งบประมาณเพิ่มขึ้นเท่าตัวจากปีก่อนหน้า",
                    reasoning_steps=[
                        ReasoningStep(
                            step_type=ReasoningStepType.EVIDENCE,
                            text_th="งบประมาณปี ๒๕๖๗ เท่ากับ ๒ ล้านบาท เทียบกับ ๑ ล้านบาทในปี ๒๕๖๖",
                            citations=[Citation(chunk_id=chunk, document_id=doc, page=1)],
                        )
                    ],
                    citations=[Citation(chunk_id=chunk, document_id=doc, page=1)],
                )
            ],
            regulation_references=[
                RegulationReference(
                    regulation_id=REG_CODE,
                    act_name_th="พระราชบัญญัติทดสอบ พ.ศ. ๒๕๖๑",
                    section_no="มาตรา ๙๙",
                    relevance_th="เกี่ยวข้องกับความโปร่งใสในการจัดซื้อจัดจ้าง",
                )
            ],
        )
        conn.execute(
            text(
                "INSERT INTO risk_results (project_id, result, risk_level, overall_score, "
                "model_id, prompt_version, generated_at) VALUES "
                "(:p, CAST(:r AS jsonb), :level, :score, :model, :pv, :gen)"
            ),
            {
                "p": p_2567,
                "r": risk.model_dump_json(),
                "level": risk.risk_level.value,
                "score": float(risk.overall_score),
                "model": risk.model_id,
                "pv": risk.prompt_version,
                "gen": risk.generated_at,
            },
        )

        for username, role, active in [
            (f"{TEST_PREFIX}-auditor", "AUDITOR", True),
            (f"{TEST_PREFIX}-admin", "ADMIN", True),
            (f"{TEST_PREFIX}-inactive", "AUDITOR", False),
        ]:
            conn.execute(
                text(
                    "INSERT INTO users (username, password_hash, display_name_th, role, "
                    "is_active) VALUES (:u, :h, :d, :r, :a) "
                    "ON CONFLICT (username) DO UPDATE SET password_hash = EXCLUDED.password_hash, "
                    "role = EXCLUDED.role, is_active = EXCLUDED.is_active"
                ),
                {"u": username, "h": password_hash, "d": f"ผู้ทดสอบ {role}", "r": role, "a": active},
            )

    yield ids

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM sub_districts WHERE id = :id"), {"id": ids["sub_district"]})
        conn.execute(
            text("DELETE FROM users WHERE username LIKE :p"), {"p": f"{TEST_PREFIX}-%"}
        )
        conn.execute(text("DELETE FROM regulations WHERE regulation_code = :c"), {"c": REG_CODE})


@pytest.fixture()
def clear_dashboard_cache():
    """Dashboard responses are Redis-cached; drop the keys so assertions see
    the seeded rows. Best-effort — the cache itself is best-effort."""

    async def _clear() -> None:
        from app.services.cache import get_redis

        try:
            await get_redis().delete("dashboard:overview", "dashboard:trends")
        except Exception:
            pass

    return _clear


@pytest.fixture()
async def client(seeded):
    from httpx import ASGITransport, AsyncClient

    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture()
async def auth_headers(client):
    resp = await client.post(
        "/api/auth/login",
        json={"username": f"{TEST_PREFIX}-auditor", "password": "test-password-123"},
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}
