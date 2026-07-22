"""Structured extraction over faithful snippets of the real corpus.

Fixtures are trimmed-but-verbatim reconstructions of documents actually in the
ingested corpus (e-GP contract summaries, บก.01 in both OCR and born-digital
shapes, บก.๐๖), so these are regression tests for the exact bytes the flow
parses — including the page-break continuation table that hides a winner.
"""

from decimal import Decimal

from common.structured_extract import (
    parse_boq_total,
    parse_contract_summary,
    parse_reference_form,
    reconstruct,
)

# e-bidding CCTV: budget/ref merged onto the name line, 3 bidders, winner in §7
CONTRACT_SUMMARY_EBIDDING = """## ข้อมูลสาระสำคัญในสัญญา
1. หน่วยงาน
2. เลขที่โครงการ
3. ชื่อโครงการ
4. งบประมาณ
5. ราคากลาง
เทศบาลตำบลท่าช้าง
68029056808
ประกวดราคาซื้อโครงการติดตั้งกล้องโทรทัศน์วงจรปิด ด้วยวิธีประกวดราคาอิเล็กทรอนิกส์ (e-bidding) 10000000 บาท
9775000 บาท
## 6. รายชื่อผู้เสนอราคา มีดังนี้
|    | รายการพิจารณา | เลขประจำตัวผู้เสียภาษีอากร | รายชื่อผู้เสนอราคา | ราคาที่เสนอ |
|----|----|----|----|----|
|  1 | ติดตั้งกล้อง | 0655564001537 | บริษัท ไฮ ซิสเต็ม ไทย จำกัด | 9,770,000.00 |
|    |    | 0903554000835 | ห้างหุ้นส่วนจำกัด พี เค อิเล็กโทรนิคส์ | 9,750,000.00 |
|    |    | 0903556003785 | ห้างหุ้นส่วนจำกัด มิกซ์คอมพิวเตอร์ | 7,233,500.00 |
## 7. ผู้ที่ได้รับการคัดเลือก ได้แก่
|   ลำดับ | เลขประจำตัว | ชื่อผู้ขาย | เลขคุมสัญญา | จำนวนเงิน | สถานะสัญญา |
|----|----|----|----|----|----|
|  1 | 0655564001537 | บริษัท ไฮ ซิสเต็ม ไทย จำกัด | 680801004122 | 9,750,000.00 | ส่งงานล่าช้า |"""

# เฉพาะเจาะจง: single quotation, winner in §7
CONTRACT_SUMMARY_SPECIFIC = """## ข้อมูลสาระสำคัญในสัญญา
1. หน่วยงาน
4. งบประมาณ
5. ราคากลาง
เทศบาลตำบลท่าช้าง
65087639323
จ้างก่อสร้างถนน คสล. ถนนสายควนหยี ซอย 2/1 หมู่ที่ 9 โดยวิธีเฉพาะเจาะจง
488300 บาท
419933.63 บาท
## 6. รายชื่อผู้เสนอราคา มีดังนี้
|    | รายการพิจารณา | เลขประจำตัวผู้เสียภาษีอากร | รายชื่อผู้เสนอราคา | ราคาที่เสนอ |
|----|----|----|----|----|
|  1 | ก่อสร้างถนน | 0905562004650 | บริษัท มาริสา ไม้ไทย จำกัด | 419,000.00 |
## 7. ผู้ที่ได้รับการคัดเลือก ได้แก่
|   ลำดับ | เลขประจำตัว ผู้เสียภาษีอากร | ชื่อผู้ขาย | จำนวนเงิน | สถานะสัญญา |
|----|----|----|----|----|
|  1 | 0905562004650 | บริษัท มาริสา ไม้ไทย จำกัด | 419,000.00 | ส่งงานครบถ้วน |"""

# a long bidder list Docling splits at a page break: the winner (lowest bid) is
# in a HEADERLESS continuation table under a repeated "## 6"
CONTRACT_SUMMARY_CONTINUATION = """## ข้อมูลสาระสำคัญในสัญญา
4. งบประมาณ
5. ราคากลาง
เทศบาลตำบลท่าช้าง
ประกวดราคาจ้างก่อสร้างถนน คสล. ซอยหลังโรงเรียนบ้านโคกเมา ด้วยวิธีประกวดราคาอิเล็กทรอนิกส์ (e-bidding)
698000 บาท
707004.00 บาท
## 6. รายชื่อผู้เสนอราคา มีดังนี้
|    | รายการพิจารณา | เลขประจำตัวผู้เสียภาษีอากร | รายชื่อผู้เสนอราคา | ราคาที่เสนอ |
|----|----|----|----|----|
|  1 | ก่อสร้างถนน | 0903539000790 | ห้างหุ้นส่วนจำกัด กระแสสินธุ์การโยธา | 520,000.00 |
|    |    | 0905559006043 | บริษัท เก้ากวินคอนสตรัคชั่น จำกัด | 552,499.00 |
## 6. รายชื่อผู้เสนอราคา มีดังนี้
|   0905566005421 | บริษัท ก้าวที่กล้าก่อสร้าง จำกัด | 589,000.00 |
|----|----|----|
|   0915564000457 | บริษัท เอชวายจี เอ็นจิเนียริ่ง จำกัด | 509,000.00 |
## 7. ผู้ที่ได้รับการคัดเลือก ได้แก่
|   ลำดับ | เลขประจำตัว ผู้เสียภาษีอากร | ชื่อผู้ขาย | จำนวนเงิน | สถานะสัญญา |
|----|----|----|----|----|
|  1 | 0915564000457 | บริษัท เอชวายจี เอ็นจิเนียริ่ง จำกัด | 509,000.00 | ส่งงานครบถ้วน |"""

# OCR'd บก.01 — Thai digits, prose form, amount before บาท
BK01_OCR = """# ตารางแสดงวงเงินงบประมาณที่ได้รับจัดสรรและราคากลางในงานจ้างก่อสร้าง
๑. ชื่อโครงการ ก่อสร้างถนน คสล. ซอยหลังโรงเรียนบ้านโคกเมา หมู่ที่ ๗
๓. วงเงินงบประมาณที่ได้รับจัดสรร ๖๕๐,๐๐๐.๐๐ บาท
๕. ราคากลางคำนวณ ณ วันที่ ๑๔ ธันวาคม ๒๕๖๖ เป็นเงิน ๗๐๗,๐๐๔.๐๐ บาท
๖. บัญชีประมาณการราคากลาง"""

# born-digital บก.01 — form linearization, amount AFTER a bare บาท header, dates inline
BK01_BORN_DIGITAL = """## ตารางแสดงวงเงินงบประมาณที่ได้รับจัดสรรและราคากลางในงานจ้างก่อสร้าง
- ราคากลางคำนวณ ณ วันที่ บาท 5. เป็นเงิน 23 กรกฎาคม 2567 2,090,014.77
- 3. วงเงินงบประมาณที่ได้รับจัดสรร บาท 2,089,600.00
- ชื่อโครงการ 1."""

BK06 = """แบบ บก.๐๖
๓. วงเงินงบประมาณที่ได้รับจัดสรร ๑๐,๐๐๐,๐๐๐.๐๐ บาท (สิบล้านบาทถ้วน)
๔. วันที่กำหนดราคากลาง (ราคาอ้างอิง) ณ วันที่ ๑๘ กรกฎาคม ๒๕๖๗
เป็นเงิน ๙,๗๗๕,๐๐๐.๐๐ บาท (เก้าล้านเจ็ดแสนเจ็ดหมื่นห้าพันบาทถ้วน)"""


class TestContractSummaryEbidding:
    def setup_method(self):
        self.cs = parse_contract_summary(CONTRACT_SUMMARY_EBIDDING)

    def test_method_and_money(self):
        assert self.cs.procurement_method == "E_BIDDING"
        assert self.cs.budget == Decimal("10000000")
        assert self.cs.reference_price == Decimal("9775000")

    def test_all_bidders_with_amounts(self):
        assert [(b.name, b.amount) for b in self.cs.bidders] == [
            ("บริษัท ไฮ ซิสเต็ม ไทย จำกัด", Decimal("9770000.00")),
            ("ห้างหุ้นส่วนจำกัด พี เค อิเล็กโทรนิคส์", Decimal("9750000.00")),
            ("ห้างหุ้นส่วนจำกัด มิกซ์คอมพิวเตอร์", Decimal("7233500.00")),
        ]

    def test_winner_and_contract_price(self):
        assert self.cs.winner is not None
        assert self.cs.winner.name == "บริษัท ไฮ ซิสเต็ม ไทย จำกัด"
        # contract signed below the winning bid — §7 จำนวนเงิน, not the §6 offer
        assert self.cs.winner.contract_price == Decimal("9750000.00")


class TestContractSummarySpecific:
    def test_sole_bidder_is_winner(self):
        cs = parse_contract_summary(CONTRACT_SUMMARY_SPECIFIC)
        assert cs.procurement_method == "SPECIFIC"
        assert len(cs.bidders) == 1
        assert cs.winner is not None
        assert cs.winner.name == "บริษัท มาริสา ไม้ไทย จำกัด"
        assert cs.winner.contract_price == Decimal("419000.00")


class TestContractSummaryContinuation:
    """The winner (lowest bid) lives in a headerless continuation table."""

    def setup_method(self):
        self.cs = parse_contract_summary(CONTRACT_SUMMARY_CONTINUATION)

    def test_continuation_bidders_recovered(self):
        names = [b.name for b in self.cs.bidders]
        assert "บริษัท ก้าวที่กล้าก่อสร้าง จำกัด" in names
        assert "บริษัท เอชวายจี เอ็นจิเนียริ่ง จำกัด" in names
        assert len(self.cs.bidders) == 4

    def test_winner_matches_a_continuation_bidder(self):
        assert self.cs.winner is not None
        assert self.cs.winner.name == "บริษัท เอชวายจี เอ็นจิเนียริ่ง จำกัด"
        assert self.cs.winner.contract_price == Decimal("509000.00")


class TestReferenceForm:
    def test_ocr_thai_digit_form(self):
        rf = parse_reference_form(BK01_OCR)
        assert rf.budget == Decimal("650000.00")
        assert rf.reference_price == Decimal("707004.00")

    def test_born_digital_amount_after_baht_and_dates(self):
        rf = parse_reference_form(BK01_BORN_DIGITAL)
        assert rf.budget == Decimal("2089600.00")
        assert rf.reference_price == Decimal("2090014.77")

    def test_bk06_non_construction(self):
        rf = parse_reference_form(BK06)
        assert rf.budget == Decimal("10000000.00")
        assert rf.reference_price == Decimal("9775000.00")


class TestBoqTotal:
    def test_stated_prose_total(self):
        text = "มติที่ประชุม - เห็นชอบใช้ราคากลาง ๑,๑๘๐,๗๕๔.๖๖ .- บาท -"
        assert parse_boq_total(text) == Decimal("1180754.66")

    def test_no_prose_total_returns_none(self):
        # a table-only BOQ with no "ราคากลาง … บาท" line is not fabricated
        assert parse_boq_total("<table><tr><td>รายการ</td><td>ราคากลาง</td></tr></table>") is None


class TestReconstruct:
    def test_drops_one_line_overlap_within_page(self):
        chunks = [
            (0, 1, "หัวเรื่อง\n| ก | ข |\n| 1 | 2 |"),
            (1, 1, "| 1 | 2 |\n| 3 | 4 |"),  # first line repeats the overlap
        ]
        assert reconstruct(chunks) == "หัวเรื่อง\n| ก | ข |\n| 1 | 2 |\n| 3 | 4 |"

    def test_no_dedup_across_page_boundary(self):
        chunks = [(0, 1, "บรรทัด"), (1, 2, "บรรทัด")]
        assert reconstruct(chunks) == "บรรทัด\nบรรทัด"
