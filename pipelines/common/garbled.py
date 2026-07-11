"""Garbled-Thai detector — decides which pages go to Typhoon-OCR on LANTA.

Extracted text from Thai government PDFs fails in known ways:

- scanned pages have no text layer at all;
- TIS-620/UTF-8 misdecodes produce Latin-1 mojibake ("à¸«à¸™...");
- damaged extractions leave U+FFFD replacement chars;
- legacy TH Sarabun-era fonts map glyphs through private-use areas, so the
  extracted codepoints are valid Thai letters in nonsense order — detectable
  only as text the Thai dictionary doesn't recognize;
- broken layout recovery orphans combining marks (a vowel/tone mark with no
  consonant to sit on).

Thresholds are module constants, deliberately conservative defaults — the
Phase-2 parsing quality gate tunes them against the real nasty corpus BEFORE
mass indexing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache

from pythainlp.tokenize import word_tokenize

# ---- reasons (stable strings; stored in the OCR outbox manifest) ----
NO_TEXT_LAYER = "NO_TEXT_LAYER"
REPLACEMENT_CHARS = "REPLACEMENT_CHARS"
MOJIBAKE = "MOJIBAKE"
BROKEN_COMBINING = "BROKEN_COMBINING"
UNRECOGNIZED_THAI = "UNRECOGNIZED_THAI"

# ---- tunable thresholds (quality-gate these on the real corpus) ----
MIN_TEXT_CHARS = 40  # below this a page is treated as having no text layer
MOJIBAKE_RATIO_MAX = 0.05
ORPHAN_RATIO_MAX = 0.02
DICT_COVERAGE_MIN = 0.50
DICT_MIN_THAI_CHARS = 30  # don't judge dictionary coverage on tiny samples

_THAI = re.compile(r"[ก-๛]")
# Latin-1 supplement letters — the signature of UTF-8/TIS-620 misdecoding
_MOJIBAKE = re.compile(r"[À-ÿ]")
_COMBINING = re.compile(r"[ัิ-ฺ็-๎]")
# a combining mark may legitimately follow a consonant (ก-ฮ, ฤ, ฦ) or stack
# on another combining mark (e.g. กั้น = ก + ั + ้)
_VALID_MARK_BASE = re.compile(r"[ก-ฮฤฦัิ-ฺ็-๎]")


@lru_cache(maxsize=1)
def _thai_dict() -> frozenset[str]:
    from pythainlp.corpus import thai_words

    return frozenset(thai_words())


@dataclass(frozen=True)
class GarbleReport:
    """Per-page verdict with the measurements that produced it."""

    text_chars: int
    thai_chars: int
    mojibake_ratio: float
    orphan_ratio: float
    dict_coverage: float | None  # None when too little Thai text to judge
    reasons: list[str] = field(default_factory=list)

    @property
    def needs_ocr(self) -> bool:
        return bool(self.reasons)


def _orphan_marks(text: str) -> int:
    orphans = 0
    for m in _COMBINING.finditer(text):
        i = m.start()
        if i == 0 or not _VALID_MARK_BASE.match(text[i - 1]):
            orphans += 1
    return orphans


def _dict_coverage(text: str, thai_chars: int) -> float | None:
    """Fraction of Thai characters covered by dictionary-recognized tokens."""
    if thai_chars < DICT_MIN_THAI_CHARS:
        return None
    words = _thai_dict()
    covered = sum(
        len(tok)
        for tok in word_tokenize(text, engine="newmm", keep_whitespace=False)
        if len(tok) >= 2 and _THAI.search(tok) and tok in words
    )
    return covered / thai_chars


def decide_page(text: str) -> GarbleReport:
    stripped = text.strip()
    n = len(stripped)
    thai_chars = len(_THAI.findall(stripped))
    reasons: list[str] = []

    if n < MIN_TEXT_CHARS:
        return GarbleReport(n, thai_chars, 0.0, 0.0, None, [NO_TEXT_LAYER])

    if "�" in stripped:
        reasons.append(REPLACEMENT_CHARS)

    mojibake_ratio = len(_MOJIBAKE.findall(stripped)) / n
    if mojibake_ratio > MOJIBAKE_RATIO_MAX:
        reasons.append(MOJIBAKE)

    orphan_ratio = _orphan_marks(stripped) / n
    if orphan_ratio > ORPHAN_RATIO_MAX:
        reasons.append(BROKEN_COMBINING)

    dict_coverage = _dict_coverage(stripped, thai_chars)
    if dict_coverage is not None and dict_coverage < DICT_COVERAGE_MIN:
        reasons.append(UNRECOGNIZED_THAI)

    return GarbleReport(n, thai_chars, mojibake_ratio, orphan_ratio, dict_coverage, reasons)
