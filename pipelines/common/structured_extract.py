"""Deterministic structured extraction from the ingested corpus text.

Pure parsers over the reconstructed document markdown (see `reconstruct`):

- `parse_contract_summary` — the e-GP ข้อมูลสาระสำคัญในสัญญา form, born-digital
  and present for every project. THE precision source: budget (งบประมาณ),
  reference price (ราคากลาง), procurement method, the full bidder table with
  amounts (§6), and the winner + contract price (§7).
- `parse_reference_form` — บก.01 (construction) / บก.๐๖ (non-construction):
  budget + ราคากลาง, used to cross-check the contract summary.
- `parse_boq_total` — the stated grand total (ราคากลาง) on a BOQ / price-
  approval sheet, for the BOQ↔บก.01 sum check. Per-line BOQ values are OCR-
  noisy and deliberately NOT trusted (see docs/ROADMAP.md Phase F).

No LLM, no float: every number comes through `common.thai_num` as a Decimal.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal

from common.thai_num import (
    amounts_before_baht,
    money_amounts,
    normalize_digits,
    parse_amount,
)


@dataclass(frozen=True)
class Bidder:
    name: str
    amount: Decimal


@dataclass(frozen=True)
class Winner:
    name: str
    contract_price: Decimal | None


@dataclass(frozen=True)
class ContractSummary:
    budget: Decimal | None = None
    reference_price: Decimal | None = None
    procurement_method: str | None = None  # E_BIDDING | SELECTION | SPECIFIC
    bidders: list[Bidder] = field(default_factory=list)
    winner: Winner | None = None


@dataclass(frozen=True)
class ReferenceForm:
    budget: Decimal | None = None
    reference_price: Decimal | None = None


# ---------------------------------------------------------------------------
# document reconstruction from chunks
# ---------------------------------------------------------------------------

def reconstruct(chunks: list[tuple[int, int | None, str]]) -> str:
    """Rebuild a document's markdown from its `chunks` rows.

    `chunks` is (chunk_index, page, text) — the chunker packs page lines with a
    one-line overlap between consecutive chunks of the same page, so drop a
    leading line that merely repeats the previous chunk's trailing line
    (tables split across a chunk boundary reassemble intact)."""
    lines: list[str] = []
    prev_page: int | None = None
    for _idx, page, text in sorted(chunks, key=lambda c: c[0]):
        chunk_lines = text.split("\n")
        if page == prev_page and lines and chunk_lines and lines[-1] == chunk_lines[0]:
            chunk_lines = chunk_lines[1:]
        lines.extend(chunk_lines)
        prev_page = page
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# markdown table helpers
# ---------------------------------------------------------------------------

def _iter_tables(section: str):
    """Yield each contiguous block of pipe-delimited lines as raw row strings."""
    rows: list[str] = []
    for line in section.splitlines():
        stripped = line.strip()
        if stripped.startswith("|"):
            rows.append(stripped)
        elif rows:
            yield rows
            rows = []
    if rows:
        yield rows


def _cells(row: str) -> list[str]:
    return [c.strip() for c in row.strip().strip("|").split("|")]


def _parse_table(rows: list[str]) -> tuple[list[str], list[list[str]]]:
    """(header cells, data rows) — separator rows and header echoes dropped.

    Chunk overlap can duplicate the header/separator across a boundary, so an
    exact repeat of the header is skipped too."""
    parsed = [_cells(r) for r in rows]
    header = parsed[0]
    data: list[list[str]] = []
    for cells in parsed[1:]:
        if set("".join(cells)) <= set("-: "):  # markdown separator
            continue
        if cells == header:  # overlap echo
            continue
        data.append(cells)
    return header, data


def _col_index(header: list[str], *needles: str) -> int | None:
    for i, cell in enumerate(header):
        if any(needle in cell for needle in needles):
            return i
    return None


def _clean_name(raw: str) -> str:
    return re.sub(r"\s+", " ", raw).strip()


def _match_key(name: str) -> str:
    """Whitespace-insensitive key for matching a winner to a §6 bidder."""
    return re.sub(r"\s+", "", name)


# ---------------------------------------------------------------------------
# contract summary (ข้อมูลสาระสำคัญในสัญญา)
# ---------------------------------------------------------------------------

def _heading_start(text: str, number: str) -> int | None:
    match = re.search(rf"^#+\s*{number}\.", text, re.MULTILINE)
    return match.start() if match else None


def _detect_method(text: str) -> str | None:
    if "e-bidding" in text or "ประกวดราคาอิเล็กทรอนิกส์" in text:
        return "E_BIDDING"
    if "คัดเลือก" in text:
        return "SELECTION"
    if "เฉพาะเจาะจง" in text:
        return "SPECIFIC"
    return None


# cells that mark a §6 header/label row rather than a bidder data row
_BIDDER_HEADER_TOKENS = (
    "รายชื่อผู้เสนอราคา", "ราคาที่เสนอ", "รายการพิจารณา", "เลขประจำตัว",
)


def _parse_bidders(section: str) -> list[Bidder]:
    """Every bidder in §6, positionally: the bid amount is always the last
    cell and the bidder name the cell before it.

    A long bidder list spans a page break, and Docling emits the continuation
    as a *headerless* table (rows of just tax-id | name | amount under a
    repeated `## 6`). Reading rows positionally — rather than by the first
    table's header columns — keeps those continuation bidders (and the winner,
    when the winning bid is on the second page)."""
    bidders: list[Bidder] = []
    seen: set[str] = set()
    for row in section.splitlines():
        stripped = row.strip()
        if not stripped.startswith("|"):
            continue
        cells = _cells(stripped)
        if len(cells) < 2:
            continue
        joined = "".join(cells)
        if set(joined) <= set("-: "):  # markdown separator
            continue
        if any(token in joined for token in _BIDDER_HEADER_TOKENS):  # header echo
            continue
        amount = parse_amount(cells[-1])
        name = _clean_name(cells[-2])
        if amount is None or not name:
            continue
        key = _match_key(name)
        if key in seen:
            continue
        seen.add(key)
        bidders.append(Bidder(name=name, amount=amount))
    return bidders


def _parse_winner(section: str) -> Winner | None:
    for rows in _iter_tables(section):
        header, data = _parse_table(rows)
        name_i = _col_index(header, "ชื่อผู้ขาย", "ผู้ที่ได้รับการคัดเลือก")
        amount_i = _col_index(header, "จำนวนเงิน")
        if name_i is None:
            continue
        for cells in data:
            if name_i >= len(cells):
                continue
            name = _clean_name(cells[name_i])
            if not name:
                continue
            price = (
                parse_amount(cells[amount_i])
                if amount_i is not None and amount_i < len(cells)
                else None
            )
            return Winner(name=name, contract_price=price)
    return None


def parse_contract_summary(text: str) -> ContractSummary:
    i6 = _heading_start(text, "6")
    i7 = _heading_start(text, "7")
    header_block = text[: i6 if i6 is not None else len(text)]
    section6 = text[i6:i7] if i6 is not None else ""
    section7 = text[i7:] if i7 is not None else ""

    amounts = amounts_before_baht(header_block)
    budget = amounts[0] if len(amounts) >= 1 else None
    reference_price = amounts[1] if len(amounts) >= 2 else None

    bidders = _parse_bidders(section6)
    winner = _parse_winner(section7)
    # เฉพาะเจาะจง with a sole quote and no §7 table: that bidder is the winner
    if winner is None and len(bidders) == 1:
        winner = Winner(name=bidders[0].name, contract_price=None)

    return ContractSummary(
        budget=budget,
        reference_price=reference_price,
        procurement_method=_detect_method(header_block),
        bidders=bidders,
        winner=winner,
    )


# ---------------------------------------------------------------------------
# บก.01 / บก.๐๖ reference-price forms
# ---------------------------------------------------------------------------

def parse_reference_form(text: str) -> ReferenceForm:
    """Parse budget + ราคากลาง from บก.01/บก.๐๖.

    Handles both extraction shapes: OCR prose (`… ๗๐๗,๐๐๔.๐๐ บาท`, amount before
    the บาท unit) and born-digital form linearization (`… วงเงินงบประมาณ… บาท
    2,089,600.00`, amount after a bare บาท header, mixed with the ราคากลาง
    calculation date). On the labelled line the money value is the last
    comma/decimal-formatted token — dates and item numbers are bare integers."""
    budget: Decimal | None = None
    reference_price: Decimal | None = None
    for line in text.splitlines():
        if budget is None and "วงเงินงบประมาณ" in line:
            amounts = money_amounts(line)
            if amounts:
                budget = amounts[-1]
        if reference_price is None and ("เป็นเงิน" in line or "ราคากลางคำนวณ" in line):
            amounts = money_amounts(line)
            if amounts:
                reference_price = amounts[-1]
    if reference_price is None:  # some forms state ราคากลาง on its own label line
        for line in text.splitlines():
            if "ราคากลาง" in line:
                amounts = money_amounts(line)
                if amounts:
                    reference_price = amounts[-1]
                    break
    return ReferenceForm(budget=budget, reference_price=reference_price)


# ---------------------------------------------------------------------------
# BOQ / price-approval grand total
# ---------------------------------------------------------------------------

def parse_boq_total(text: str) -> Decimal | None:
    """The stated grand total (ราคากลาง … บาท). Per-line table cells are OCR-
    noisy and ignored; the committee's stated total is the trusted figure."""
    candidates: list[Decimal] = []
    for line in normalize_digits(text).splitlines():
        if "ราคากลาง" in line:
            candidates.extend(amounts_before_baht(line))
    return max(candidates) if candidates else None
