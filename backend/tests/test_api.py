"""API integration tests against the live compose PostgreSQL (throwaway rows;
skip when the stack is down — see conftest)."""

from tests.conftest import REG_CODE, TEST_PREFIX

# ---- auth ---------------------------------------------------------------------


async def test_health(client):
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["database"] == "up"


async def test_login_wrong_password(client):
    resp = await client.post(
        "/api/auth/login",
        json={"username": f"{TEST_PREFIX}-auditor", "password": "nope"},
    )
    assert resp.status_code == 401


async def test_login_inactive_user_rejected(client):
    resp = await client.post(
        "/api/auth/login",
        json={"username": f"{TEST_PREFIX}-inactive", "password": "test-password-123"},
    )
    assert resp.status_code == 401


async def test_me(client, auth_headers):
    resp = await client.get("/api/auth/me", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["username"] == f"{TEST_PREFIX}-auditor"
    assert body["role"] == "AUDITOR"


async def test_endpoints_require_auth(client):
    for path in ["/api/dashboard/overview", "/api/projects", f"/api/regulations/{REG_CODE}"]:
        resp = await client.get(path)
        assert resp.status_code == 401, path


# ---- projects -----------------------------------------------------------------


async def test_project_list_filters_and_sorting(client, auth_headers, seeded):
    resp = await client.get(
        "/api/projects",
        params={"sub_district_id": str(seeded["sub_district"])},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    # Scored REQUIRES_INVESTIGATION project sorts above the unscored one
    first, second = body["items"]
    assert first["id"] == str(seeded["project_2567"])
    assert first["risk_level"] == "REQUIRES_INVESTIGATION"
    assert first["precheck_flag_count"] == 1
    assert second["risk_level"] is None
    assert "ผู้ตรวจสอบ" in body["disclaimer_th"]

    resp = await client.get(
        "/api/projects",
        params={"sub_district_id": str(seeded["sub_district"]), "fiscal_year": 2566},
        headers=auth_headers,
    )
    assert [i["fiscal_year"] for i in resp.json()["items"]] == [2566]

    resp = await client.get(
        "/api/projects",
        params={"sub_district_id": str(seeded["sub_district"]), "risk_level": "LOW"},
        headers=auth_headers,
    )
    assert resp.json()["total"] == 0


async def test_project_detail_serves_validated_contract(client, auth_headers, seeded):
    resp = await client.get(f"/api/projects/{seeded['project_2567']}", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()

    assert body["procurement_method"] == "E_BIDDING"
    assert len(body["bids"]) == 2
    assert body["bids"][0]["is_winner"] is True

    names = {c["name"] for c in body["prechecks"]}
    assert {"yoy_budget_anomaly", "boq_vs_bk01"} <= names
    yoy = next(c for c in body["prechecks"] if c["name"] == "yoy_budget_anomaly")
    assert yoy["status"] == "FLAG" and yoy["severity"] == "HIGH"

    risk = body["risk"]["result"]
    assert risk["risk_level"] == "REQUIRES_INVESTIGATION"
    factor = risk["factors"][0]
    assert factor["factor_type"] == "BUDGET_DEVIATION"
    assert factor["reasoning_steps"][0]["step_type"] == "EVIDENCE"
    assert factor["reasoning_steps"][0]["citations"][0]["chunk_id"] == str(seeded["chunk"])
    assert risk["regulation_references"][0]["regulation_id"] == REG_CODE


async def test_project_detail_404(client, auth_headers):
    resp = await client.get(
        "/api/projects/00000000-0000-0000-0000-000000000000", headers=auth_headers
    )
    assert resp.status_code == 404


# ---- citations / regulations ---------------------------------------------------


async def test_citation_resolves_to_source_passage(client, auth_headers, seeded):
    resp = await client.get(f"/api/chunks/{seeded['chunk']}", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "สรุปสัญญาจ้าง" in body["text"]
    assert body["document"]["filename"] == "contract_summary_test.pdf"


async def test_regulation_code_with_slash(client, auth_headers):
    resp = await client.get(f"/api/regulations/{REG_CODE}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["section_no"] == "มาตรา ๙๙"


# ---- dashboard -----------------------------------------------------------------


async def test_overview(client, auth_headers, seeded, clear_dashboard_cache):
    await clear_dashboard_cache()
    resp = await client.get("/api/dashboard/overview", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()

    assert body["totals"]["project_count"] >= 2
    assert body["risk_distribution"].get("REQUIRES_INVESTIGATION", 0) >= 1

    ours = [
        c for c in body["heatmap"] if c["sub_district_id"] == str(seeded["sub_district"])
    ]
    assert {c["fiscal_year"] for c in ours} == {2566, 2567}
    cell_2567 = next(c for c in ours if c["fiscal_year"] == 2567)
    assert cell_2567["worst_risk_level"] == "REQUIRES_INVESTIGATION"
    await clear_dashboard_cache()


async def test_trends_yoy_and_contractor_concentration(
    client, auth_headers, seeded, clear_dashboard_cache
):
    await clear_dashboard_cache()
    resp = await client.get("/api/dashboard/trends", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()

    ours = [
        p
        for p in body["budget_by_year"]
        if p["sub_district_id"] == str(seeded["sub_district"])
    ]
    point_2567 = next(p for p in ours if p["fiscal_year"] == 2567)
    assert point_2567["yoy_pct"] == 100.0  # 1,000,000 -> 2,000,000

    winner = next(
        c
        for c in body["contractor_concentration"]
        if c["bidder_name_th"] == "หจก. ทดสอบก่อสร้าง"
    )
    assert winner["bids_submitted"] == 2
    assert winner["contracts_won"] == 2
    assert winner["total_awarded"] == 2935000.0
    assert sorted(winner["fiscal_years"]) == [2566, 2567]
    await clear_dashboard_cache()


# ---- feedback ------------------------------------------------------------------


async def test_feedback_capture_and_list(client, auth_headers, seeded):
    resp = await client.post(
        f"/api/projects/{seeded['project_2566']}/feedback",
        json={"text_th": "ตรวจสอบเอกสารประกอบแล้ว ขอข้อมูลราคากลางเพิ่มเติม"},
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["auditor_username"] == f"{TEST_PREFIX}-auditor"
    assert body["sentiment"] is None  # filled later by the batch sentiment flow

    resp = await client.get(
        f"/api/projects/{seeded['project_2566']}/feedback", headers=auth_headers
    )
    assert resp.status_code == 200
    assert any("ราคากลาง" in f["text_th"] for f in resp.json())


# ---- citation viewer: real source PDF -------------------------------------------


async def test_document_file_serves_real_pdf(client, auth_headers, document_with_file):
    resp = await client.get(f"/api/documents/{document_with_file}/file", headers=auth_headers)
    assert resp.status_code == 200
    # Forced explicitly by the endpoint — the object is stored as
    # application/octet-stream (verified against the real bucket).
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content.startswith(b"%PDF-")
    # Thai filename must survive header encoding (RFC 5987), never 500
    disposition = resp.headers["content-disposition"]
    assert "filename*=UTF-8''" in disposition
    assert disposition.isascii()


async def test_document_file_404_for_unknown_document(client, auth_headers):
    resp = await client.get(
        "/api/documents/00000000-0000-0000-0000-000000000000/file", headers=auth_headers
    )
    assert resp.status_code == 404


async def test_document_file_requires_auth(client, document_with_file):
    resp = await client.get(f"/api/documents/{document_with_file}/file")
    assert resp.status_code == 401


# ---- budget items (tracked-item anomaly page) -----------------------------------


async def test_budget_items_unit_price_series(
    client, auth_headers, seeded_items, clear_dashboard_cache
):
    from app.services.cache import get_redis

    try:
        await get_redis().delete("dashboard:budget-items")
    except Exception:
        pass
    resp = await client.get("/api/dashboard/budget-items", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    group = next(
        g for g in body["items"] if g["item_key"] == "test-tank-2000l"
    )
    assert group["standard"]["standard_unit_price"] == 7000.0
    assert group["standard"]["provenance"] == "CURATED"
    assert group["standard"]["document_id"] is not None  # citation resolves

    years = group["years"]
    assert [y["fiscal_year"] for y in years] == [2566, 2567]
    assert years[0]["unit_price"] == 4500.0
    assert years[0]["unit_price_yoy_pct"] is None  # first recorded year
    assert years[1]["unit_price"] == 6800.0
    assert years[1]["unit_price_yoy_pct"] == 51.1  # SQL window, not Python
    assert years[0]["pct_of_standard"] == 64.3
    assert years[1]["pct_of_standard"] == 97.1
    # quantity source citation opens in the PDF viewer
    assert years[0]["source"]["document_id"] is not None
    assert years[0]["source"]["page"] == 12
    assert "ผู้ตรวจสอบ" in body["disclaimer_th"]
    try:
        await get_redis().delete("dashboard:budget-items")
    except Exception:
        pass


# ---- budget-report trends (ภาพรวม budget-by-year) -------------------------------


async def test_budget_report_trends(client, auth_headers, seeded_budget_reports, seeded):
    from app.services.cache import get_redis

    try:
        await get_redis().delete("dashboard:budget-report-trends")
    except Exception:
        pass
    resp = await client.get("/api/dashboard/budget-report-trends", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    group = next(
        g for g in body["items"] if g["sub_district_id"] == str(seeded["sub_district"])
    )
    years = group["years"]
    assert [y["fiscal_year"] for y in years] == [2566, 2567]
    assert years[0]["total_budget"] == 1_000_000.0
    assert years[0]["project_count"] == 10
    assert years[0]["budget_yoy_pct"] is None  # first year
    assert years[1]["total_budget"] == 1_500_000.0
    assert years[1]["budget_yoy_pct"] == 50.0  # SQL window, not Python
    assert years[1]["document_id"] is not None  # cites the source report
    # top-3 highest-budget items, ranked descending
    tops = years[0]["top_items"]
    assert len(tops) == 3
    assert tops[0]["description_th"] == "โครงการเบี้ยยังชีพผู้สูงอายุ"
    assert tops[0]["amount"] == 500000.0
    assert [t["amount"] for t in tops] == sorted((t["amount"] for t in tops), reverse=True)
    assert "ผู้ตรวจสอบ" in body["disclaimer_th"]
    try:
        await get_redis().delete("dashboard:budget-report-trends")
    except Exception:
        pass
