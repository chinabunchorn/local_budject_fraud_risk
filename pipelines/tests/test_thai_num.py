"""Deterministic number parsing — exact Decimal assertions (no float slop)."""

from decimal import Decimal

from common.thai_num import (
    amounts_before_baht,
    money_amounts,
    normalize_digits,
    parse_amount,
)


class TestNormalizeDigits:
    def test_thai_digits_map_to_arabic(self):
        assert normalize_digits("๑๒๓,๔๕๖.๗๘") == "123,456.78"

    def test_non_digits_untouched(self):
        assert normalize_digits("ราคากลาง ๗๐๗ บาท") == "ราคากลาง 707 บาท"


class TestParseAmount:
    def test_arabic_with_commas_and_decimal(self):
        assert parse_amount("9,750,000.00") == Decimal("9750000.00")

    def test_thai_digits(self):
        assert parse_amount("๖๕๐,๐๐๐.๐๐") == Decimal("650000.00")

    def test_plain_integer(self):
        assert parse_amount("10000000") == Decimal("10000000")

    def test_none_and_placeholders(self):
        assert parse_amount(None) is None
        assert parse_amount("-") is None
        assert parse_amount("") is None

    def test_first_numeric_run_only(self):
        # a bare tax-id-like token still parses to its digits; callers gate on shape
        assert parse_amount("419,000.00 บาท") == Decimal("419000.00")


class TestAmountsBeforeBaht:
    def test_reading_order(self):
        text = "งบประมาณ 10000000 บาท\nราคากลาง 9775000 บาท"
        assert amounts_before_baht(text) == [Decimal("10000000"), Decimal("9775000")]

    def test_thai_digits_and_dash_ornament(self):
        # OCR often writes "๑,๑๘๐,๗๕๔.๖๖ .- บาท"
        assert amounts_before_baht("ราคากลาง ๑,๑๘๐,๗๕๔.๖๖ .- บาท") == [
            Decimal("1180754.66")
        ]

    def test_baht_with_no_preceding_number_ignored(self):
        assert amounts_before_baht("ราคา/หน่วย (ถ้ามี) บาท") == []


class TestMoneyAmounts:
    def test_excludes_bare_integers(self):
        # born-digital บก.01: "… บาท 5. เป็นเงิน 23 กรกฎาคม 2567 2,090,014.77"
        line = "ราคากลางคำนวณ ณ วันที่ บาท 5. เป็นเงิน 23 กรกฎาคม 2567 2,090,014.77"
        assert money_amounts(line) == [Decimal("2090014.77")]

    def test_keeps_only_comma_or_decimal_formatted(self):
        assert money_amounts("3. วงเงินงบประมาณที่ได้รับจัดสรร บาท 2,089,600.00") == [
            Decimal("2089600.00")
        ]

    def test_thai_digit_money(self):
        assert money_amounts("๓. ... ๑๐,๐๐๐,๐๐๐.๐๐ บาท") == [Decimal("10000000.00")]
