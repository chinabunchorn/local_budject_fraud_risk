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
            has_items = conn.execute(text("SELECT to_regclass('project_items')")).scalar()
    except Exception:
        pytest.skip("PostgreSQL not reachable — start the compose stack and source .env")
    if has_users is None or has_items is None:
        pytest.skip("schema out of date — run alembic upgrade head (needs migration 0006)")
    yield eng
    eng.dispose()


@pytest.fixture()
def seeded_items(engine, seeded):
    """Tracked-item rows + a curated standard price on the throwaway projects
    (unit prices 4,500 → 6,800 vs standard 7,000 — mirrors the MVP case)."""
    with engine.begin() as conn:
        for pid, qty, total in [
            (seeded["project_2566"], 5, 22500),
            (seeded["project_2567"], 5, 34000),
        ]:
            conn.execute(
                text(
                    "INSERT INTO project_items (project_id, item_key, description_th, "
                    "quantity, unit_th, total_amount, source_document_id, source_page, "
                    "source_quote_th) VALUES (:p, 'test-tank-2000l', "
                    "'จัดซื้อถังน้ำทดสอบ ขนาด 2,000 ลิตร จำนวน 5 ใบ', :q, 'ใบ', :t, :doc, 12, "
                    "'จัดซื้อถังน้ำทดสอบ | 22,500') "
                    "ON CONFLICT (project_id, item_key) DO UPDATE SET quantity = EXCLUDED.quantity"
                ),
                {"p": pid, "q": qty, "t": total, "doc": seeded["document"]},
            )
        conn.execute(
            text(
                "INSERT INTO standard_prices (item_key, description_th, "
                "standard_unit_price, fiscal_year, source_document_id, source_page) "
                "VALUES ('test-tank-2000l', 'ถังน้ำทดสอบ 2,000 ลิตร', 7000, 2568, :doc, 1) "
                "ON CONFLICT (item_key) DO UPDATE SET "
                "standard_unit_price = EXCLUDED.standard_unit_price"
            ),
            {"doc": seeded["document"]},
        )

    yield seeded

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM standard_prices WHERE item_key = 'test-tank-2000l'"))
        # project_items cascade away with the seeded sub-district


@pytest.fixture()
def seeded_budget_reports(engine, seeded):
    """Two years of budget_report_summaries on the throwaway sub-district
    (1.0M -> 1.5M, +50% YoY; 10 -> 12 projects)."""
    with engine.begin() as conn:
        for fy, total, count in [(2566, 1_000_000, 10), (2567, 1_500_000, 12)]:
            conn.execute(
                text(
                    "INSERT INTO budget_report_summaries (sub_district_id, fiscal_year, "
                    "document_id, total_budget, project_count) "
                    "VALUES (:sd, :fy, :doc, :total, :count) "
                    "ON CONFLICT (sub_district_id, fiscal_year) DO UPDATE SET "
                    "total_budget = EXCLUDED.total_budget"
                ),
                {"sd": seeded["sub_district"], "fy": fy, "doc": seeded["document"],
                 "total": total, "count": count},
            )
    yield seeded
    # rows cascade away with the seeded sub-district


@pytest.fixture()
def document_with_file(engine):
    """A throwaway document row whose minio_key points at a real tiny PDF
    uploaded to the corpus bucket — exercises the actual MinIO round trip the
    /documents/{id}/file endpoint depends on, not just the DB row. Skips
    cleanly when MinIO is unreachable, same convention as `engine`."""
    from io import BytesIO

    from app.services.storage import get_minio_client

    settings = get_settings()
    client = get_minio_client()
    try:
        client.bucket_exists(settings.minio_bucket_corpus)
    except Exception:
        pytest.skip("MinIO not reachable — start the compose stack and source .env")

    # Minimal syntactically-valid single-page PDF — enough for the endpoint's
    # content-type/streaming behavior, not a real document.
    pdf_bytes = (
        b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]>>endobj\n"
        b"trailer<</Root 1 0 R>>\n%%EOF"
    )
    key = f"{TEST_PREFIX}/sample-{uuid.uuid4()}.pdf"
    client.put_object(settings.minio_bucket_corpus, key, BytesIO(pdf_bytes), length=len(pdf_bytes))

    with engine.begin() as conn:
        sd_id = conn.execute(
            text(
                "INSERT INTO sub_districts (name_th, district_th, province_th) VALUES "
                "('ตำบลทดสอบไฟล์', 'อำเภอทดสอบ', 'จังหวัดทดสอบ') RETURNING id"
            )
        ).scalar_one()
        pid = conn.execute(
            text(
                "INSERT INTO projects (sub_district_id, name_th, fiscal_year, budget_total) "
                "VALUES (:sd, 'โครงการทดสอบไฟล์', 2569, 500000) RETURNING id"
            ),
            {"sd": sd_id},
        ).scalar_one()
        # Thai filename on purpose — regression for the RFC 5987
        # Content-Disposition encoding (headers are latin-1; Thai must not 500)
        doc_id = conn.execute(
            text(
                "INSERT INTO documents (project_id, minio_key, filename, doc_type, source, "
                "parse_status, scope) VALUES (:p, :k, 'ราคามาตรฐานทดสอบ.pdf', "
                "'contract_summary', 'BORN_DIGITAL', 'COMPLETED', 'PROJECT') RETURNING id"
            ),
            {"p": pid, "k": key},
        ).scalar_one()

    yield doc_id

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM sub_districts WHERE id = :id"), {"id": sd_id})
    client.remove_object(settings.minio_bucket_corpus, key)


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
