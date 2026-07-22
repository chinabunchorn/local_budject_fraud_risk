"""Detector tests — synthetic samples of every known failure mode."""

from common.garbled import (
    BROKEN_COMBINING,
    LOW_THAI_RATIO,
    MOJIBAKE,
    NO_TEXT_LAYER,
    REPLACEMENT_CHARS,
    UNRECOGNIZED_THAI,
    decide_page,
)

CLEAN = (
    "หน่วยงานของรัฐจะก่อหนี้ผูกพันหรือจ่ายเงินได้ก็แต่โดยอาศัยอำนาจที่มีอยู่ตามกฎหมาย "
    "การใช้จ่ายเงินของหน่วยงานของรัฐต้องเป็นไปอย่างโปร่งใส คุ้มค่าและประหยัด "
    "โดยพิจารณาเป้าหมาย ประโยชน์ที่ได้รับ และประสิทธิภาพของหน่วยงานของรัฐ"
)


class TestCleanText:
    def test_clean_thai_passes(self):
        report = decide_page(CLEAN)
        assert not report.needs_ocr
        assert report.reasons == []
        assert report.dict_coverage is not None and report.dict_coverage > 0.6

    def test_clean_with_numbers_and_punctuation_passes(self):
        report = decide_page(CLEAN + " จำนวน ๔๙๘,๐๐๐ บาท (สี่แสนเก้าหมื่นแปดพันบาทถ้วน)")
        assert not report.needs_ocr


class TestFailureModes:
    def test_empty_page_is_no_text_layer(self):
        assert decide_page("").reasons == [NO_TEXT_LAYER]

    def test_near_empty_page_is_no_text_layer(self):
        # a scanned page often yields just a page number or stray mark
        assert decide_page("  - ๓ -  ").reasons == [NO_TEXT_LAYER]

    def test_replacement_chars_flagged(self):
        report = decide_page(CLEAN.replace("ก", "�"))
        assert REPLACEMENT_CHARS in report.reasons

    def test_utf8_as_latin1_mojibake_flagged(self):
        mojibake = "à¸«à¸™à¹ˆà¸§à¸¢à¸‡à¸²à¸™à¸‚à¸­à¸‡à¸£à¸±à¸ " * 5
        report = decide_page(mojibake)
        assert MOJIBAKE in report.reasons

    def test_orphan_combining_marks_flagged(self):
        # marks with no consonant base — broken layout recovery
        report = decide_page(CLEAN + " า้ า้ า้ า้ า้ า้ า้ า้ า้ า้")
        assert BROKEN_COMBINING in report.reasons

    def test_legacy_font_nonsense_thai_flagged(self):
        # valid Thai codepoints in dictionary-nonsense order (PUA glyph remap)
        soup = "ฃฅฆฑฌญฐฎ ฏศฑฒณ ฃฅฆฑฌญ ฐฎฏศฑฒ ฆฑฌฃฅญ " * 4
        report = decide_page(soup)
        assert UNRECOGNIZED_THAI in report.reasons

    def test_clean_short_text_not_judged_by_dictionary(self):
        # under DICT_MIN_THAI_CHARS Thai chars → coverage is None, not a verdict
        report = decide_page("x" * 50 + " กข")
        assert report.dict_coverage is None
        assert UNRECOGNIZED_THAI not in report.reasons

    def test_legacy_font_latin_mapped_layer_flagged(self):
        """Caught by the Phase-D gate on a real TOR: Thai glyphs extracted as
        LATIN junk — substantial page, near-zero Thai letters."""
        junk = "hunununing uinnwa nin inualns namnauaaueiunuuunuay mmto ushaad " * 4
        report = decide_page(junk)
        assert LOW_THAI_RATIO in report.reasons
        assert report.thai_letter_ratio == 0.0

    def test_mostly_thai_with_some_english_terms_passes(self):
        # real docs mix in terms like "e-bidding" — must not trip the ratio
        report = decide_page(CLEAN + " ด้วยวิธีประกวดราคาอิเล็กทรอนิกส์ (e-bidding) Factor F")
        assert LOW_THAI_RATIO not in report.reasons

    def test_short_mixed_text_not_judged_by_ratio(self):
        report = decide_page("PDF page 7 of 12 - รวม 12,500 บาท")
        assert report.thai_letter_ratio is None
        assert LOW_THAI_RATIO not in report.reasons
