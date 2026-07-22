"""Manifest v2 parsing + generation: scopes, optional budget, round-trip."""

import pytest

from common.corpus_catalog import CorpusFile
from common.manifest import parse_manifest
from common.manifest_gen import generate_manifest

VALID = """
reference_documents:
  - key: reference/กรมบัญชีกลาง/บัญชีค่าแรงงาน.pdf
    doc_type: reference_standard
sub_districts:
  - name_th: ตำบลท่าช้าง
    district_th: บางกล่ำ
    province_th: สงขลา
    budget_reports:
      - key: ตำบลท่าช้าง/budget_reports/ท่าช้าง67.pdf
        doc_type: budget_report
    projects:
      - name_th: โครงการปรับปรุงถนนสายหลัก
        fiscal_year: 2567
        budget_total: 1500000.00
        category_th: โครงสร้างพื้นฐาน
        documents:
          - key: ตำบลท่าช้าง/projects/2567/โครงการปรับปรุงถนนสายหลัก/contract_summary.pdf
            doc_type: contract_summary
      - name_th: จ้างซ่อมรถจักรยานยนต์
        fiscal_year: 2567
        documents:
          - key: ตำบลท่าช้าง/projects/2567/จ้างซ่อมรถจักรยานยนต์/contract_summary.pdf
"""


class TestParseManifest:
    def test_valid_manifest_all_scopes(self):
        manifest = parse_manifest(VALID)
        assert len(manifest.reference_documents) == 1
        sd = manifest.sub_districts[0]
        assert sd.budget_reports[0].doc_type == "budget_report"
        assert sd.projects[0].budget_total == 1500000.0
        assert sd.projects[1].budget_total is None  # optional — extracted later
        assert sd.projects[1].documents[0].doc_type is None

    def test_duplicate_key_rejected_across_scopes(self):
        dup = VALID.replace(
            "key: reference/กรมบัญชีกลาง/บัญชีค่าแรงงาน.pdf",
            "key: ตำบลท่าช้าง/budget_reports/ท่าช้าง67.pdf",
        )
        with pytest.raises(ValueError, match="duplicate document key"):
            parse_manifest(dup)

    def test_fiscal_year_must_be_buddhist_era(self):
        with pytest.raises(ValueError, match="พ.ศ."):
            parse_manifest(VALID.replace("fiscal_year: 2567", "fiscal_year: 2024"))

    def test_missing_sub_districts_rejected(self):
        with pytest.raises(ValueError, match="sub_districts"):
            parse_manifest("projects: []")


def entry(**overrides) -> CorpusFile:
    base = dict(
        source_path="x",
        scope="PROJECT",
        normalized_key="ตำบลหัวเขา/projects/2568/โครงการทดสอบ/contract_summary.pdf",
        is_pdf=True,
        sub_district="ตำบลหัวเขา",
        fiscal_year=2568,
        project_name="โครงการทดสอบ",
        doc_type="contract_summary",
    )
    return CorpusFile(**{**base, **overrides})


class TestGenerateManifest:
    def test_generated_manifest_round_trips(self):
        entries = [
            entry(),
            entry(
                normalized_key="ตำบลหัวเขา/projects/2568/โครงการทดสอบ/bk01.pdf",
                doc_type="bk01",
            ),
            entry(
                scope="SUB_DISTRICT",
                normalized_key="ตำบลหัวเขา/budget_reports/รายงานงบ68.pdf",
                project_name=None,
                doc_type="budget_report",
            ),
            entry(
                scope="REFERENCE",
                normalized_key="reference/กรมบัญชีกลาง/ค่าแรง.pdf",
                sub_district=None,
                fiscal_year=None,
                project_name=None,
                doc_type="reference_standard",
            ),
        ]
        manifest = parse_manifest(generate_manifest(entries))
        assert len(manifest.reference_documents) == 1
        sd = manifest.sub_districts[0]
        assert sd.district_th == "เดิมบางนางบวช" and sd.province_th == "สุพรรณบุรี"
        assert len(sd.budget_reports) == 1
        assert len(sd.projects) == 1
        assert len(sd.projects[0].documents) == 2
        assert sd.projects[0].budget_total is None  # never invented

    def test_unknown_sub_district_fails_loudly(self):
        with pytest.raises(ValueError, match="ตำบลปริศนา"):
            generate_manifest([entry(sub_district="ตำบลปริศนา")])
