"""Unit tests for the Act parser — synthetic text covering every known artifact."""

import pytest

from common.act_parser import clean_page_text, split_sections

ACT_CODE = "fiscal-discipline-act-2561"

SAMPLE = """\
พระราชบัญญัติ
วินัยการเงินการคลังของรัฐ
พ.ศ. ๒๕๖๑
มาตรา ๑ พระราชบัญญัตินี้เรียกว่า "พระราชบัญญัติวินัยการเงินการคลังของรัฐ พ.ศ. ๒๕๖๑"
มาตรา ๒ พระราชบัญญัตินี้ให้ใช้บังคับตั้งแต่วันถัดจากวันประกาศ
หมวด ๑
บททั่วไป
มาตรา ๓ ในกรณีที่มีเหตุจำเป็น รัฐจะดำเนินการตาม
มาตรา ๒ วรรคหนึ่งก็ได้
ส่วนที่ ๑
วินัยการคลัง
มาตรา ๔ การใช้จ่ายต้องเป็นไปตามกฎหมายว่าด้วยวิธีการงบประมาณ
บทเฉพาะกาล
มาตรา ๕ ให้ดำเนินการให้แล้วเสร็จภายในสองปี
ผู้รับสนองพระราชโองการ
พลเอก ประยุทธ์ จันทร์โอชา
นายกรัฐมนตรี
หมายเหตุ :- เหตุผลในการประกาศใช้พระราชบัญญัติฉบับนี้ คือ ...
"""


def sections():
    return split_sections(SAMPLE, ACT_CODE)


class TestCleanPageText:
    def test_removes_space_before_combining_marks(self):
        assert clean_page_text("นายกร ัฐมนตร ี") == "นายกรัฐมนตรี"

    def test_recomposes_sara_am(self):
        # nikhahit + sara aa (2 codepoints) → sara am
        assert clean_page_text("อํานาจ") == "อำนาจ"

    def test_strips_page_headers(self):
        page = "หน้า   ๓ \nเล่ม   ๑๓๕   ตอนที่   ๒๗   ก ราชกิจจานุเบกษา ๑๙   เมษายน   ๒๕๖๑ \nเนื้อหาจริง"
        assert clean_page_text(page) == "เนื้อหาจริง"

    def test_collapses_runs_of_spaces(self):
        assert clean_page_text("ก   ข\tค") == "ก ข ค"


class TestSplitSections:
    def test_preamble_captured(self):
        first = sections()[0]
        assert first.section_no == "preamble"
        assert first.regulation_code == f"{ACT_CODE}/preamble"
        assert "พระราชบัญญัติ" in first.text

    def test_all_sections_found_with_arabic_numbers(self):
        nos = [s.section_no for s in sections() if s.section_no.isdigit()]
        assert nos == ["1", "2", "3", "4", "5"]

    def test_regulation_code_format(self):
        by_no = {s.section_no: s for s in sections()}
        assert by_no["4"].regulation_code == f"{ACT_CODE}/s.4"

    def test_regulation_code_carries_act(self):
        procurement = split_sections(SAMPLE, "procurement-act-2560")
        assert procurement[1].regulation_code == "procurement-act-2560/s.1"
        assert "จัดซื้อจัดจ้าง" in procurement[1].act_name_th

    def test_unknown_act_code_rejected(self):
        with pytest.raises(ValueError, match="unknown act_code"):
            split_sections(SAMPLE, "some-other-act")

    def test_wrapped_reference_does_not_split(self):
        """"มาตรา ๒" at a wrapped-line start inside มาตรา ๓ is a reference, not a section."""
        by_no = {s.section_no: s for s in sections()}
        assert "มาตรา ๒ วรรคหนึ่ง" in by_no["3"].text
        # and มาตรา ๒ itself was emitted exactly once
        assert sum(1 for s in sections() if s.section_no == "2") == 1

    def test_chapter_and_part_headings_carried(self):
        by_no = {s.section_no: s for s in sections()}
        assert by_no["1"].section_title_th is None
        assert by_no["3"].section_title_th == "หมวด ๑ บททั่วไป"
        assert by_no["4"].section_title_th == "หมวด ๑ บททั่วไป / ส่วนที่ ๑ วินัยการคลัง"
        assert by_no["5"].section_title_th == "บทเฉพาะกาล"

    def test_regulation_document_splits_on_kho(self):
        """ระเบียบ number their clauses ข้อ, end at ประกาศ ณ วันที่, and are
        published in special gazette issues (ตอนพิเศษ header variant)."""
        sample = (
            "เล่ม ๑๓๔ ตอนพิเศษ ๒๑๐ ง ราชกิจจานุเบกษา ๒๓ สิงหาคม ๒๕๖๐\n"
            "ระเบียบกระทรวงการคลัง\n"
            "ว่าด้วยการจัดซื้อจัดจ้างและการบริหารพัสดุภาครัฐ พ.ศ. ๒๕๖๐\n"
            "ข้อ ๑ ระเบียบนี้เรียกว่า “ระเบียบกระทรวงการคลัง...”\n"
            "หมวด ๑\n"
            "ข้อกำหนดทั่วไป\n"
            "ส่วนที่ ๑\n"
            "วงเงินการซื้อหรือจ้าง\n"
            "การแบ่งซื้อหรือแบ่งจ้าง\n"  # unnumbered topic heading (3rd level)
            "ข้อ ๒ ห้ามมิให้แบ่งซื้อหรือแบ่งจ้างโดยลดวงเงินที่จะซื้อหรือจ้างในครั้งเดียวกัน\n"
            "ประกาศ ณ วันที่ ๒๓ สิงหาคม พ.ศ. ๒๕๖๐\n"
            "อภิศักดิ์ ตันติวรวงศ์\n"
            "บัญชีเอกสารแนบท้าย\n"
            "๑. แบบประกาศเชิญชวน\n"
        )
        clean = clean_page_text(sample)
        assert "ตอนพิเศษ" not in clean  # header variant stripped
        secs = split_sections(clean, "mof-procurement-regulation-2560")
        by_no = {s.section_no: s for s in secs}
        # topic heading became title context for ข้อ ๒ — NOT a phantom duplicate clause
        assert [s.section_no for s in secs if s.section_no.isdigit()] == ["1", "2"]
        assert by_no["2"].regulation_code == "mof-procurement-regulation-2560/k.2"
        assert (
            by_no["2"].section_title_th
            == "หมวด ๑ ข้อกำหนดทั่วไป / ส่วนที่ ๑ วงเงินการซื้อหรือจ้าง / การแบ่งซื้อหรือแบ่งจ้าง"
        )
        assert "แบ่งซื้อ" in by_no["2"].text
        # promulgation block and attachment list are not law text
        joined = "\n".join(s.text for s in secs)
        assert "ประกาศ ณ วันที่" not in joined
        assert "บัญชีเอกสารแนบท้าย" not in joined

    def test_countersignature_dropped_end_note_kept(self):
        all_text = "\n".join(s.text for s in sections())
        assert "ผู้รับสนองพระราชโองการ" not in all_text
        note = [s for s in sections() if s.section_no == "note"]
        assert len(note) == 1
        assert note[0].text.startswith("หมายเหตุ")
        assert note[0].regulation_code == f"{ACT_CODE}/note"
