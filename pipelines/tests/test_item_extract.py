"""Unit tests for tracked-item extraction + item-level findings (MVP case:
the Tambon Hua Khao 2,000L water tanks — 5 ใบ FY67 ฿22,500 → FY68 ฿34,000,
same vendor, standard ฿7,000/unit)."""

from decimal import Decimal

from common.item_extract import (
    CandidateProject,
    ItemLine,
    extract_item_lines,
    match_line_to_project,
    match_tracked_item,
    report_fiscal_year,
)
from common.item_prechecks import (
    ItemFact,
    StandardPrice,
    compute_item_findings,
)

# real shapes as stored in chunks (pipe tables, Arabic digits after normalize)
FY67_CHUNK = (
    "| 13 | การช่วยเหลือผู้ประสบวาตภัย หมู่ที่ 6 , 7 ตำบลหัวเขา | 10,385 | พ.ค. - ก.ค. 67 |\n"
    "| 14 | จัดซื้อถังน้ำพลาสติก ขนาด 2,000 ลิตร จำนวน 5 ใบ | 22,500 | 23 ก.ย. 67 |\n"
    "| 15 | จัดซื้อถังน้ำพลาสติก ขนาด 3,000 ลิตร จำนวน 1 ใบ | 6,700 | 23 ก.ย. 67 |\n"
)
FY68_CHUNK = "| 19 | จัดซื้อถังน้ำพลาสติก ขนาด 2,000 ลิตร จำนวน 5 ใบ |           34,000 | 8 ก.ย. 68 |"
# Thai digits, as the raw OCR markdown carries them
THAI_DIGIT_CHUNK = "| ๑๔ | จัดซื้อถังน้ำพลาสติก ขนาด ๒,๐๐๐ ลิตร จำนวน ๕ ใบ | ๒๒,๕๐๐ | ๒๓ ก.ย. ๖๗ |"


def test_extracts_only_the_tracked_2000l_item():
    lines = extract_item_lines(FY67_CHUNK, page=12)
    assert len(lines) == 1  # the 3,000L tank is NOT in the tracked catalog
    line = lines[0]
    assert line.item_key == "water-tank-plastic-2000l"
    assert line.quantity == Decimal("5")
    assert line.unit_th == "ใบ"
    assert line.total_amount == Decimal("22500")
    assert line.page == 12
    assert "ถังน้ำพลาสติก" in line.quote_th


def test_extracts_whitespace_padded_amount_cell():
    lines = extract_item_lines(FY68_CHUNK, page=10)
    assert len(lines) == 1
    assert lines[0].total_amount == Decimal("34000")


def test_extracts_thai_digit_ocr_rows():
    lines = extract_item_lines(THAI_DIGIT_CHUNK, page=12)
    assert len(lines) == 1
    assert lines[0].quantity == Decimal("5")
    assert lines[0].total_amount == Decimal("22500")


def test_matches_tank_name_variants():
    assert match_tracked_item("ซื้อถังน้ำพลาสติก ขนาดความจุ ๒,๐๐๐ ลิตร") is not None
    assert match_tracked_item("ซื้อถังน้ำแบบพลาสติก ขนาดความจุ ๒,๐๐๐ ลิตร") is not None
    assert match_tracked_item("จัดซื้อถังน้ำพลาสติก ขนาด 3,000 ลิตร") is None
    assert match_tracked_item("โครงการก่อสร้างถนน คสล") is None


def test_report_fiscal_year():
    assert report_fiscal_year("รายงานงบ 67.pdf") == 2567
    assert report_fiscal_year("รายงานงบ68.pdf") == 2568
    assert report_fiscal_year("รายงานอื่น.pdf") is None


def _line(total: str) -> ItemLine:
    return ItemLine(
        item_key="water-tank-plastic-2000l",
        description_th="จัดซื้อถังน้ำพลาสติก ขนาด 2,000 ลิตร จำนวน 5 ใบ",
        quantity=Decimal("5"),
        unit_th="ใบ",
        total_amount=Decimal(total),
        page=12,
        quote_th="…",
    )


def _candidate(pid: str, name: str, price: str | None) -> CandidateProject:
    return CandidateProject(
        project_id=pid,
        sub_district_id="sd1",
        fiscal_year=2567,
        name_th=name,
        contract_price=Decimal(price) if price else None,
    )


def test_match_requires_amount_and_name_pattern():
    tank = _candidate("p1", "ซื้อถังน้ำพลาสติก ขนาดความจุ ๒,๐๐๐ ลิตร", "22500")
    road = _candidate("p2", "โครงการก่อสร้างถนน", "22500")  # same amount, wrong item
    assert match_line_to_project(_line("22500"), [tank, road]) is tank
    assert match_line_to_project(_line("22500"), [road]) is None
    assert match_line_to_project(_line("99999"), [tank]) is None


def test_match_refuses_ambiguity():
    a = _candidate("p1", "ซื้อถังน้ำพลาสติก ๒,๐๐๐ ลิตร ชุดแรก", "22500")
    b = _candidate("p2", "ซื้อถังน้ำพลาสติก ๒,๐๐๐ ลิตร ชุดสอง", "22500")
    assert match_line_to_project(_line("22500"), [a, b]) is None


# ---- findings -----------------------------------------------------------------


def _fact(pid: str, fy: int, unit_price: str, winner: str | None) -> ItemFact:
    return ItemFact(
        project_id=pid,
        sub_district_id="sd1",
        fiscal_year=fy,
        project_name_th=f"ซื้อถังน้ำ FY{fy}",
        item_key="water-tank-plastic-2000l",
        label_th="ถังน้ำพลาสติก ขนาด 2,000 ลิตร",
        quantity=Decimal("5"),
        unit_th="ใบ",
        unit_price=Decimal(unit_price),
        total_amount=Decimal(unit_price) * 5,
        winner_name=winner,
        bid_count=1,
        procurement_method="SPECIFIC",
    )


STANDARDS = {
    "water-tank-plastic-2000l": StandardPrice(
        item_key="water-tank-plastic-2000l",
        description_th="ถังน้ำ แบบพลาสติก 2,000 ลิตร",
        unit_price=Decimal("7000"),
    )
}


def test_mvp_case_spike_vendor_lock_and_standard():
    facts = [
        _fact("p67", 2567, "4500", "ร้านวีระพร พลาสติก"),
        _fact("p68", 2568, "6800", "ร้านวีระพร พลาสติก"),
    ]
    findings = compute_item_findings(facts, STANDARDS)

    spike = next(f for f in findings["p68"] if f["name"] == "unit_price_yoy_spike")
    assert spike["status"] == "FLAG"
    assert spike["values"]["growth_pct"] == "51.1"
    # same vendor both years → escalated with Thai justification
    assert spike["values"]["severity"] == "HIGH"
    assert "ร้านวีระพร" in spike["values"]["justification"]
    # attached to both member projects
    assert any(f["name"] == "unit_price_yoy_spike" for f in findings["p67"])

    lock = next(f for f in findings["p68"] if f["name"] == "item_vendor_lock")
    assert lock["status"] == "FLAG"
    assert lock["values"]["fiscal_years"] == [2567, 2568]
    assert lock["values"]["single_bid_years"] == [2567, 2568]
    assert lock["values"]["cumulative_amount"] == "56500"

    std67 = next(f for f in findings["p67"] if f["name"] == "unit_price_vs_standard")
    std68 = next(f for f in findings["p68"] if f["name"] == "unit_price_vs_standard")
    assert std67["status"] == "OK" and std67["values"]["ratio_pct"] == "64.3"
    assert std68["status"] == "OK" and std68["values"]["ratio_pct"] == "97.1"


def test_duplicate_facts_from_overlapping_chunks_deduped():
    """The same budget-report line can appear in two overlapping chunks —
    the group must treat one project as one fact (regression: cumulative
    ฿90,500 from a double-counted FY68 line)."""
    facts = [
        _fact("p67", 2567, "4500", "ร้านวีระพร พลาสติก"),
        _fact("p68", 2568, "6800", "ร้านวีระพร พลาสติก"),
        _fact("p68", 2568, "6800", "ร้านวีระพร พลาสติก"),  # duplicate
    ]
    findings = compute_item_findings(facts, STANDARDS)
    lock = next(f for f in findings["p68"] if f["name"] == "item_vendor_lock")
    assert lock["values"]["fiscal_years"] == [2567, 2568]
    assert lock["values"]["cumulative_amount"] == "56500"
    spikes = [f for f in findings["p68"] if f["name"] == "unit_price_yoy_spike"]
    assert len(spikes) == 1


def test_no_spike_below_threshold_and_different_vendor_no_lock():
    facts = [
        _fact("a", 2567, "4500", "ร้าน ก"),
        _fact("b", 2568, "5000", "ร้าน ข"),  # +11% — under threshold
    ]
    findings = compute_item_findings(facts, STANDARDS)
    assert not any(f["name"] == "unit_price_yoy_spike" for f in findings["b"])
    assert not any(f["name"] == "item_vendor_lock" for f in findings["b"])


def test_over_standard_flags():
    facts = [_fact("p", 2568, "7500", "ร้าน ก")]
    findings = compute_item_findings(facts, STANDARDS)
    std = next(f for f in findings["p"] if f["name"] == "unit_price_vs_standard")
    assert std["status"] == "FLAG"
    assert "สูงกว่าราคามาตรฐาน" in std["detail"]


def test_no_standard_row_is_na():
    facts = [_fact("p", 2568, "6800", "ร้าน ก")]
    findings = compute_item_findings(facts, {})
    std = next(f for f in findings["p"] if f["name"] == "unit_price_vs_standard")
    assert std["status"] == "NA"


def test_banned_lexicon_absent_from_all_finding_text():
    from schemas import BANNED_TERMS

    facts = [
        _fact("p67", 2567, "4500", "ร้านวีระพร พลาสติก"),
        _fact("p68", 2568, "7800", "ร้านวีระพร พลาสติก"),
    ]
    findings = compute_item_findings(facts, STANDARDS)
    import json

    blob = json.dumps(findings, ensure_ascii=False, default=str)
    for term in BANNED_TERMS:
        assert term not in blob
