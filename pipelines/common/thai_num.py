"""Deterministic Thai/Arabic numeric parsing for structured extraction.

Government forms mix Thai digits (๐-๙, in OCR'd บก.01/บก.๐๖/BOQ) with Arabic
digits (born-digital contract summaries), thousands separators, and stray
" .-" baht ornamentation. Every amount that lands in `projects`, `bids`, or a
pre-check is parsed here with `Decimal` — no float, no LLM — so the arithmetic
is exact and auditable.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

_THAI_TO_ARABIC = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")

# a numeric run with optional thousands commas and optional decimal fraction
_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")
# an amount immediately preceding บาท, tolerating a " .-" ornament in between
_AMOUNT_BAHT = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(?:\.-)?\s*บาท")


def normalize_digits(text: str) -> str:
    """Map Thai digits ๐-๙ to 0-9; everything else untouched."""
    return text.translate(_THAI_TO_ARABIC)


def parse_amount(raw: str | None) -> Decimal | None:
    """Parse the first numeric run in `raw` (a cell/token) to an exact Decimal.

    Handles Thai digits and thousands commas; returns None when there is no
    number (empty cells, dashes, placeholder text)."""
    if raw is None:
        return None
    match = _NUMBER.search(normalize_digits(raw))
    if not match:
        return None
    try:
        return Decimal(match.group(0).replace(",", ""))
    except InvalidOperation:  # pragma: no cover - regex already guards the shape
        return None


def amounts_before_baht(text: str) -> list[Decimal]:
    """All amounts written as `<number> บาท`, in reading order.

    This is the reliable anchor for the money fields on Thai budget forms,
    where labels and values are laid out in separate columns but every value
    carries its บาท unit."""
    out: list[Decimal] = []
    for match in _AMOUNT_BAHT.finditer(normalize_digits(text)):
        amount = parse_amount(match.group(1))
        if amount is not None:
            out.append(amount)
    return out


def money_amounts(text: str) -> list[Decimal]:
    """Numbers formatted as money — carrying a thousands comma or a decimal
    fraction — in reading order.

    On บก.01/บก.๐๖ forms, born-digital extraction puts the value after a bare
    `บาท` unit header and next to dates, so `amounts_before_baht` misses it;
    but the money value is always the comma/decimal-formatted token while day,
    month-name, พ.ศ. year, and item numbers are bare integers. That shape is
    the discriminator here."""
    out: list[Decimal] = []
    for match in _NUMBER.finditer(normalize_digits(text)):
        token = match.group(0)
        if "," in token or "." in token:
            amount = parse_amount(token)
            if amount is not None:
                out.append(amount)
    return out
