"""Unit tests for budget-report line-item summing."""

from decimal import Decimal

from common.budget_report_extract import MIN_LINE_ITEMS, sum_budget_report


def _rows(*pairs: tuple[str, str]) -> str:
    """Build a pipe-table chunk from (description, amount) pairs."""
    lines = [
        f"| {i + 1} | {desc} | {amt} | 1 ม.ค. 68 |" for i, (desc, amt) in enumerate(pairs)
    ]
    return "\n".join(lines)


def test_sums_amounts_and_counts_rows():
    chunk = _rows(
        ("โครงการก่อสร้างถนน หมู่ 1", "142,000"),
        ("จัดซื้อถังน้ำพลาสติก จำนวน 5 ใบ", "22,500"),
        ("โครงการเบี้ยยังชีพผู้สูงอายุ", "12,327,000"),
    )
    s = sum_budget_report([chunk])
    assert s.project_count == 3
    assert s.total_budget == Decimal("12491500")


def test_dedupes_overlapping_chunks():
    # the middle row repeats across two overlapping chunks — counted once
    a = _rows(("โครงการ ก", "100,000"), ("โครงการ ข", "200,000"))
    b = _rows(("โครงการ ข", "200,000"), ("โครงการ ค", "300,000"))
    s = sum_budget_report([a, b])
    assert s.project_count == 3
    assert s.total_budget == Decimal("600000")


def test_parses_thai_digits():
    chunk = "| ๑ | โครงการทดสอบ | ๒๒,๕๐๐ | ๒๓ ก.ย. ๖๗ |"
    s = sum_budget_report([chunk])
    assert s.project_count == 1
    assert s.total_budget == Decimal("22500")


def test_skips_non_numeric_and_zero():
    chunk = (
        "| 1 | โครงการมีงบ | 50,000 | x |\n"
        "| 2 | โครงการงบผู้บริหาร | งบประมาณของผู้บริหาร | x |\n"
        "| 3 | โครงการศูนย์ | 0 | x |"
    )
    s = sum_budget_report([chunk])
    assert s.project_count == 1
    assert s.total_budget == Decimal("50000")


def test_min_line_items_constant_is_sane():
    # narrative reports with a few stray rows must fall below the table bar
    assert MIN_LINE_ITEMS >= 5


def test_empty_report():
    s = sum_budget_report(["no table here, just prose about the budget policy"])
    assert s.project_count == 0
    assert s.total_budget == Decimal("0")
