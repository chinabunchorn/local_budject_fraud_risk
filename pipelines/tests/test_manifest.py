"""Manifest parsing: shape, validation, duplicate detection."""

import pytest

from common.manifest import parse_manifest

VALID = """
sub_districts:
  - name_th: เทศบาลตำบลท่าช้าง
    district_th: เมืองนครนายก
    province_th: นครนายก
    projects:
      - name_th: โครงการปรับปรุงถนนสายหลัก
        fiscal_year: 2567
        budget_total: 1500000.00
        category_th: โครงสร้างพื้นฐาน
        documents:
          - key: tha-chang/road/contract.pdf
            doc_type: contract
          - key: tha-chang/road/report.pdf
"""


class TestParseManifest:
    def test_valid_manifest_roundtrip(self):
        sds = parse_manifest(VALID)
        assert len(sds) == 1
        proj = sds[0].projects[0]
        assert proj.fiscal_year == 2567
        assert proj.budget_total == 1500000.0
        assert [d.key for d in proj.documents] == [
            "tha-chang/road/contract.pdf",
            "tha-chang/road/report.pdf",
        ]
        assert proj.documents[0].doc_type == "contract"
        assert proj.documents[1].doc_type is None

    def test_duplicate_document_key_rejected(self):
        dup = VALID + """
  - name_th: อบต.บ้านใหม่
    district_th: เมือง
    province_th: นครนายก
    projects:
      - name_th: โครงการอื่น
        fiscal_year: 2567
        budget_total: 1.0
        documents:
          - key: tha-chang/road/contract.pdf
"""
        with pytest.raises(ValueError, match="duplicate document key"):
            parse_manifest(dup)

    def test_fiscal_year_must_be_buddhist_era(self):
        with pytest.raises(ValueError, match="พ.ศ."):
            parse_manifest(VALID.replace("2567", "2024"))

    def test_missing_sub_districts_rejected(self):
        with pytest.raises(ValueError, match="sub_districts"):
            parse_manifest("projects: []")
