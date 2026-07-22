"""Deterministic budget-report summing — no LLM.

Sub-district budget reports (รายงานงบประมาณ) are line-item project tables:

    | 14 | จัดซื้อถังน้ำพลาสติก ... จำนวน 5 ใบ | 22,500 | 23 ก.ย. 67 |

This sums the amount column and counts the rows per report to produce one
(total_budget, project_count) per year for the ภาพรวม budget-trend chart.

Two real-data facts drive the parsing rules, verified against the documents'
own stated grand totals (e.g. Hua Khao FY66 page 14: "๘๐ โครงการ ...
๓๗,๙๖๑,๘๔๐.๐๕ บาท"):

  1. Centrally-funded (งบกลาง) projects carry a funding note IN the amount
     cell, after the number — `| 13 | ...ถนน ค.ส.ล. คลอง ๖... | 7,248,000 งบกลาง |`.
     The amount regex therefore tolerates trailing non-pipe text after the
     number; requiring the number to be flush against the closing pipe silently
     dropped every large งบกลาง project (the original bug: FY66 undercounted by
     ฿9,698,000).
  2. Zero-budget projects (a dash "-" or "งบประมาณของผู้บริหาร" in the amount
     cell) ARE counted in the document's project total but contribute ฿0 to the
     money total — so they count toward `project_count` with amount 0.

Reports are chunked with overlap, so the same row appears in several chunks;
rows are deduped by (full description, amount). Header / section / summary rows
(empty or very short descriptions, or "ส่วนที่/ด้านที่/รวม/ลำดับ" leaders) are
excluded. Validated: FY66 = 80 / ฿37,961,840.05 (exact, penny-perfect);
FY67/FY68 land within OCR-source noise of their printed totals.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

from common.thai_num import normalize_digits, parse_amount

# A pipe-table budget row: | <no> | <description> | <amount-cell> | ...
# The amount cell is captured whole (it may hold "7,248,000 งบกลาง" or a bare
# "-"); the leading number is pulled out separately. Applied to digit-
# normalized text.
_BUDGET_ROW = re.compile(r"\|\s*\d+\s*\|\s*([^|]+?)\s*\|\s*([^|]*?)\s*\|")
# The amount at the START of the amount cell (ignores any trailing funding note).
_AMOUNT_HEAD = re.compile(r"([0-9][0-9,]*(?:\.\d+)?)")

# Rows whose description is empty/tiny or a table structural label are not
# projects (header, section marker, subtotal, column-header leftovers).
_MIN_DESC_LEN = 8
_SKIP_PREFIXES = ("ส่วนที่", "ด้านที่", "รวม", "ลำดับ")

# A report must yield at least this many distinct line items to be treated as a
# real budget table (guards against narrative reports with a few stray rows).
MIN_LINE_ITEMS = 10


@dataclass(frozen=True)
class BudgetLineItem:
    description_th: str
    amount: Decimal  # 0 for a counted-but-unbudgeted project (dash "-")


@dataclass(frozen=True)
class BudgetReportSummary:
    total_budget: Decimal
    project_count: int
    line_items: list[BudgetLineItem]


def _is_project_row(description: str) -> bool:
    return len(description) >= _MIN_DESC_LEN and not description.startswith(_SKIP_PREFIXES)


def sum_budget_report(chunk_texts: list[str]) -> BudgetReportSummary:
    """Sum a single report's line items across its (possibly overlapping)
    chunks. Zero-budget projects (dash / non-numeric amount cell) are counted
    with amount 0; header/section rows are skipped."""
    seen: dict[tuple[str, str], BudgetLineItem] = {}
    for text in chunk_texts:
        for desc, amount_cell in _BUDGET_ROW.findall(normalize_digits(text)):
            desc_clean = re.sub(r"\s+", " ", desc).strip()
            if not _is_project_row(desc_clean):
                continue
            m = _AMOUNT_HEAD.match(amount_cell.strip())
            amount = parse_amount(m.group(1)) if m else None
            if amount is None or amount <= 0:
                amount = Decimal("0")  # counted project, no allocated budget
            key = (desc_clean, str(amount))
            if key not in seen:
                seen[key] = BudgetLineItem(description_th=desc_clean, amount=amount)
    items = list(seen.values())
    total = sum((li.amount for li in items), Decimal("0"))
    return BudgetReportSummary(total_budget=total, project_count=len(items), line_items=items)


def top_line_items(summary: BudgetReportSummary, n: int = 3) -> list[dict]:
    """The n highest-budget line items, amount-descending, as JSON-ready dicts
    (amount kept as a string to preserve Decimal exactness)."""
    ranked = sorted(summary.line_items, key=lambda li: li.amount, reverse=True)[:n]
    return [{"description_th": li.description_th, "amount": str(li.amount)} for li in ranked]
