"""Deterministic tracked-item extraction from budget-report lines — no LLM.

Budget reports (รายงานงบประมาณ) list expenditure lines like

    | 14 | จัดซื้อถังน้ำพลาสติก ขนาด 2,000 ลิตร จำนวน 5 ใบ | 22,500 | 23 ก.ย. 67 |

which carry the ONE fact the contract summaries lack: the quantity. This
module extracts (description, quantity, unit, total) for items in a small
explicit catalog of TRACKED items, then matches each line to its project by
sub-district + fiscal year + exact amount equality (Decimal) + the project
name matching the same item pattern. Ambiguity is skipped, never guessed —
every extracted row cites its source document, page, and quoted line.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

from common.thai_num import normalize_digits, parse_amount

# Units a quantity may be expressed in (ใบ for tanks; extend as items grow)
_UNITS = "ใบ|อัน|เครื่อง|ชุด|คัน|หัว|ตัว|หลัง"

_QUANTITY = re.compile(rf"จำนวน\s*([\d,]+)\s*({_UNITS})")

# a pipe-table expenditure row: | no | description | amount | date |
_TABLE_ROW = re.compile(
    r"\|\s*\d+\s*\|\s*(?P<desc>[^|]+?)\s*\|\s*(?P<amount>[\d,]+(?:\.\d+)?)\s*\|"
)


@dataclass(frozen=True)
class TrackedItem:
    """One item class the anomaly checks follow across years."""

    item_key: str
    label_th: str
    pattern: re.Pattern[str]  # applied to digit-normalized text


TRACKED_ITEMS: tuple[TrackedItem, ...] = (
    TrackedItem(
        item_key="water-tank-plastic-2000l",
        label_th="ถังน้ำพลาสติก ขนาด 2,000 ลิตร",
        # tolerate ถังน้ำพลาสติก / ถังน้ำแบบพลาสติก and spacing/comma variants
        pattern=re.compile(r"ถังน้ำ(?:แบบ)?พลาสติก.{0,60}?2\s*,?\s*000\s*ลิตร"),
    ),
)


@dataclass(frozen=True)
class ItemLine:
    """One tracked-item expenditure line found in a budget report."""

    item_key: str
    description_th: str
    quantity: Decimal
    unit_th: str
    total_amount: Decimal
    page: int | None
    quote_th: str


def match_tracked_item(text: str) -> TrackedItem | None:
    normalized = normalize_digits(text)
    for item in TRACKED_ITEMS:
        if item.pattern.search(normalized):
            return item
    return None


def extract_item_lines(chunk_text: str, page: int | None) -> list[ItemLine]:
    """Scan one budget-report chunk for tracked-item expenditure rows."""
    out: list[ItemLine] = []
    normalized = normalize_digits(chunk_text)
    for m in _TABLE_ROW.finditer(normalized):
        desc = re.sub(r"\s+", " ", m.group("desc")).strip()
        item = match_tracked_item(desc)
        if item is None:
            continue
        qty_match = _QUANTITY.search(desc)
        if qty_match is None:
            continue  # a tracked item without a stated quantity is unusable
        quantity = parse_amount(qty_match.group(1))
        total = parse_amount(m.group("amount"))
        if quantity is None or total is None or quantity <= 0:
            continue
        out.append(
            ItemLine(
                item_key=item.item_key,
                description_th=desc,
                quantity=quantity,
                unit_th=qty_match.group(2),
                total_amount=total,
                page=page,
                quote_th=desc + f" | {m.group('amount')}",
            )
        )
    return out


@dataclass(frozen=True)
class CandidateProject:
    project_id: str
    sub_district_id: str
    fiscal_year: int
    name_th: str
    contract_price: Decimal | None


def match_line_to_project(
    line: ItemLine, candidates: list[CandidateProject]
) -> CandidateProject | None:
    """Match by exact amount AND project name matching the same item pattern.
    Anything ambiguous (0 or >1 matches) returns None — never guess."""
    hits = [
        c
        for c in candidates
        if c.contract_price is not None
        and c.contract_price == line.total_amount
        and match_tracked_item(c.name_th) is not None
        and match_tracked_item(c.name_th).item_key == line.item_key  # type: ignore[union-attr]
    ]
    return hits[0] if len(hits) == 1 else None


def report_fiscal_year(filename: str) -> int | None:
    """"รายงานงบ 67.pdf" / "รายงานงบ68.pdf" → 2567 / 2568."""
    m = re.search(r"(\d{2,4})", normalize_digits(filename))
    if not m:
        return None
    year = int(m.group(1))
    if year < 100:
        year += 2500
    return year if 2500 <= year <= 2600 else None
