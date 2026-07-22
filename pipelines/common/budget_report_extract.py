"""Deterministic budget-report summing — no LLM.

Sub-district budget reports (รายงานงบประมาณ) are line-item project tables:

    | 14 | จัดซื้อถังน้ำพลาสติก ... จำนวน 5 ใบ | 22,500 | 23 ก.ย. 67 |

This sums the amount column and counts the rows per report to produce one
(total_budget, project_count) per year for the ภาพรวม budget-trend chart.

Only genuine line-item tables are summable this way. The reports are chunked
with overlap, so the same row can appear in two chunks — rows are deduped by
(description-prefix, amount) before summing (validated against the real Hua
Khao FY66/67/68 reports: 28.26M/76, 21.12M/64, 21.46M/61).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

from common.thai_num import normalize_digits, parse_amount

# A pipe-table budget row: | <no> | <description> | <amount> | ... — the same
# table shape common/item_extract.py parses, but here every row counts (not
# just tracked items). Applied to digit-normalized text.
_BUDGET_ROW = re.compile(r"\|\s*\d+\s*\|\s*([^|]+?)\s*\|\s*([0-9][0-9,]*(?:\.\d+)?)\s*\|")

# A report must yield at least this many distinct line items to be treated as a
# real budget table (guards against narrative reports with a few stray rows).
MIN_LINE_ITEMS = 10


@dataclass(frozen=True)
class BudgetLineItem:
    description_th: str
    amount: Decimal


@dataclass(frozen=True)
class BudgetReportSummary:
    total_budget: Decimal
    project_count: int
    line_items: list[BudgetLineItem]


def _dedupe_key(description: str, amount: Decimal) -> tuple[str, str]:
    # collapse overlapping-chunk repeats of the same row; 40-char prefix is
    # enough to distinguish real projects while tolerating minor OCR drift
    return (re.sub(r"\s+", " ", description).strip()[:40], str(amount))


def sum_budget_report(chunk_texts: list[str]) -> BudgetReportSummary:
    """Sum a single report's line items across its (possibly overlapping)
    chunks. Non-numeric budget cells and non-positive amounts are skipped."""
    seen: dict[tuple[str, str], BudgetLineItem] = {}
    for text in chunk_texts:
        for desc, amount_raw in _BUDGET_ROW.findall(normalize_digits(text)):
            amount = parse_amount(amount_raw)
            if amount is None or amount <= 0:
                continue
            desc_clean = re.sub(r"\s+", " ", desc).strip()
            key = _dedupe_key(desc_clean, amount)
            if key not in seen:
                seen[key] = BudgetLineItem(description_th=desc_clean, amount=amount)
    items = list(seen.values())
    total = sum((li.amount for li in items), Decimal("0"))
    return BudgetReportSummary(total_budget=total, project_count=len(items), line_items=items)
