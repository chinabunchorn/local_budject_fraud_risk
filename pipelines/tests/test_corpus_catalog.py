"""Catalog tests — every real-world naming defect observed in the delivery."""

from pathlib import Path

from common.corpus_catalog import (
    BK01,
    BK06,
    BOQ,
    CONTRACT_SUMMARY,
    PRICE_APPROVAL_MEMO,
    TECH_SPEC,
    TOR,
    WINNER_ANNOUNCEMENT,
    clean_component,
    infer_doc_type,
    normalize_year,
    walk_corpus,
)

PDF = b"%PDF-1.4 fake"


def make_tree(tmp_path: Path) -> Path:
    root = tmp_path / "real_data"
    files = [
        "เอกสารกลาง/กรมบัญชีกลาง/บัญชีค่าแรงงาน.pdf",
        "ตำบลหัวเขา/รายงานงบประมาณ/รายงานงบ66.pdf",
        # trailing space in year dir; extensionless bk file with Thai digits
        "ตำบลหัวเขา/โครงการ/ปี 67 /โครงการถนน คสล หมู่ ๔/บก.๐๖",
        "ตำบลหัวเขา/โครงการ/ปี 67 /โครงการถนน คสล หมู่ ๔/BOQ.pdf",
        # spaced bk01 variant + trailing-space project dir
        "ตำบลหัวเขา/โครงการ/ปี 66/โครงการถนนดิน /บก. 01",
        # leading combining mark in filename; numeric year dir
        "ตำบลท่าช้าง/โครงการ/2565/จ้างซ่อมรถ/้ข้อมูลสาระสำคัญในสัญญา.pdf",
        "ตำบลท่าช้าง/โครงการ/2565/จ้างซ่อมรถ/README.md",
    ]
    for rel in files:
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"# guide" if rel.endswith(".md") else PDF)
    return root


class TestNormalizers:
    def test_year_forms(self):
        assert normalize_year("ปี 68") == 2568
        assert normalize_year("ปี 67 ") == 2567
        assert normalize_year("2565") == 2565
        assert normalize_year("๒๕๖๖") == 2566
        assert normalize_year("โครงการ") is None

    def test_clean_component_strips_leading_combining_mark(self):
        assert clean_component("้ข้อมูลสาระสำคัญในสัญญา.pdf") == "ข้อมูลสาระสำคัญในสัญญา.pdf"

    def test_doc_type_variants(self):
        assert infer_doc_type("บก.01") == BK01
        assert infer_doc_type("บก.1") == BK01
        assert infer_doc_type("บก. 01") == BK01
        assert infer_doc_type("บก.๐๖") == BK06
        assert infer_doc_type(" บก.๐๖") == BK06
        assert infer_doc_type("BOQ.pdf") == BOQ
        assert infer_doc_type("ปร.5.pdf") == BOQ
        assert infer_doc_type("TOR.pdf") == TOR
        assert infer_doc_type("ขอบเขตของงาน.pdf") == TOR
        assert infer_doc_type("ข้อกำหนดเทคนิค.pdf") == TECH_SPEC
        assert infer_doc_type("ข้อมูลเทคนิค.pdf") == TECH_SPEC
        assert infer_doc_type("ข้อมูลสาระสำคัญในสัญญา.pdf") == CONTRACT_SUMMARY
        assert infer_doc_type("้ข้อมูลสาระสำคัญในสัญญา.pdf") == CONTRACT_SUMMARY
        assert infer_doc_type("ประกาศผู้ชนะการเสนอราคา.pdf") == WINNER_ANNOUNCEMENT
        assert infer_doc_type("บันทึกอนุมัติราคากลาง.pdf") == PRICE_APPROVAL_MEMO
        assert infer_doc_type("อะไรก็ไม่รู้.pdf") is None


class TestWalkCorpus:
    def test_scopes_and_counts(self, tmp_path):
        entries = walk_corpus(make_tree(tmp_path))
        assert len(entries) == 6  # README.md excluded
        scopes = {e.scope for e in entries}
        assert scopes == {"PROJECT", "SUB_DISTRICT", "REFERENCE"}

    def test_extensionless_bk_normalized(self, tmp_path):
        entries = walk_corpus(make_tree(tmp_path))
        bk06 = next(e for e in entries if e.doc_type == BK06)
        assert bk06.fiscal_year == 2567
        assert bk06.normalized_key == "ตำบลหัวเขา/projects/2567/โครงการถนน คสล หมู่ ๔/bk06.pdf"
        assert bk06.is_pdf

    def test_trailing_space_project_dir_normalized(self, tmp_path):
        entries = walk_corpus(make_tree(tmp_path))
        bk01 = next(e for e in entries if e.doc_type == BK01)
        assert bk01.project_name == "โครงการถนนดิน"
        assert "dirname-normalized" in bk01.anomalies

    def test_leading_combining_mark_filename(self, tmp_path):
        entries = walk_corpus(make_tree(tmp_path))
        contract = next(e for e in entries if e.doc_type == CONTRACT_SUMMARY)
        assert contract.fiscal_year == 2565
        assert contract.normalized_key.endswith("/contract_summary.pdf")

    def test_budget_report_year_from_filename(self, tmp_path):
        entries = walk_corpus(make_tree(tmp_path))
        budget = next(e for e in entries if e.scope == "SUB_DISTRICT")
        assert budget.fiscal_year == 2566
        assert budget.normalized_key == "ตำบลหัวเขา/budget_reports/รายงานงบ66.pdf"

    def test_source_paths_untouched(self, tmp_path):
        root = make_tree(tmp_path)
        entries = walk_corpus(root)
        for e in entries:
            assert (root / e.source_path).exists()  # originals never renamed
