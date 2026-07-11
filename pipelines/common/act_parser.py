"""Parser for the State Fiscal and Financial Discipline Act B.E. 2561 PDF.

The source is a born-digital ราชกิจจานุเบกษา PDF. pypdf extracts the Thai text
well but with two systematic artifacts that MUST be fixed before indexing:

1. Spurious spaces before combining marks ("ร ัฐมนตร ี" → "รัฐมนตรี").
2. Decomposed sara am (nikhahit + sara aa, "อํานาจ") — recomposed by
   `pythainlp.util.normalize`.

Sections are split on `มาตรา <thai-digits>` at line start, guarded by
monotonic numbering (a line-wrapped *reference* like "...ตาม\nมาตรา ๕ วรรคสอง"
must not open a new section). The running หมวด / ส่วนที่ / บทเฉพาะกาล heading
is carried as each section's title context.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from pythainlp.util import normalize as thai_normalize


@dataclass(frozen=True)
class ActSpec:
    """How one legal document is structured.

    พ.ร.บ. (acts) number their sections มาตรา → code prefix "s.";
    ระเบียบ (ministerial regulations) number theirs ข้อ → code prefix "k.".
    """

    name_th: str
    section_word: str = "มาตรา"
    code_prefix: str = "s."


# Known documents: code → spec. The code is the regulation_code prefix that
# RegulationReference citations resolve against.
ACTS: dict[str, ActSpec] = {
    "fiscal-discipline-act-2561": ActSpec(
        name_th="พระราชบัญญัติวินัยการเงินการคลังของรัฐ พ.ศ. ๒๕๖๑",
    ),
    "procurement-act-2560": ActSpec(
        name_th="พระราชบัญญัติการจัดซื้อจัดจ้างและการบริหารพัสดุภาครัฐ พ.ศ. ๒๕๖๐",
    ),
    "mof-procurement-regulation-2560": ActSpec(
        name_th="ระเบียบกระทรวงการคลังว่าด้วยการจัดซื้อจัดจ้างและการบริหารพัสดุภาครัฐ พ.ศ. ๒๕๖๐",
        section_word="ข้อ",
        code_prefix="k.",
    ),
}

# Thai combining marks: upper/lower vowels, tone marks, thanthakhat, nikhahit
_THAI_COMBINING = "ัิ-ฺ็-๎"
_SPACE_BEFORE_COMBINING = re.compile(rf"[ \t]+([{_THAI_COMBINING}])")

# ราชกิจจานุเบกษา page furniture, e.g. "หน้า   ๓" / "เล่ม ๑๓๕ ตอนที่ ๒๗ ก ..."
# / "เล่ม ๑๓๔ ตอนพิเศษ ๒๑๐ ง ..." (ระเบียบ are published in special issues)
_PAGE_HEADER = re.compile(
    r"^\s*(หน้า\s+[๐-๙]+\s*$|เล่ม\s+[๐-๙]+\s+ตอน(ที่|พิเศษ)\s+.*ราชกิจจานุเบกษา)"
)

_CHAPTER_START = re.compile(r"^\s*(หมวด\s+[๐-๙]+|บทเฉพาะกาล)\s*$")
_PART_START = re.compile(r"^\s*ส่วนที่\s+[๐-๙]+\s*$")
# Body ends at the countersignature (พ.ร.บ.) or the promulgation date (ระเบียบ)
_COUNTERSIGN = re.compile(r"^\s*(ผู้รับสนองพระราชโองการ|ประกาศ\s*ณ\s*วันที่)")
_END_NOTE = re.compile(r"^\s*หมายเหตุ\s*:?-?")


def _section_start(section_word: str) -> re.Pattern[str]:
    return re.compile(rf"^\s*{section_word}\s+([๐-๙]+)\b")


# มาตรา is also what a section-start looks like in heading-title lookahead
_ANY_SECTION_START = re.compile(r"^\s*(มาตรา|ข้อ)\s+[๐-๙]+\b")

_THAI_DIGITS = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")


@dataclass(frozen=True)
class ActSection:
    """One row for the `regulations` table (pre-embedding)."""

    act_code: str  # key into ACTS, e.g. "fiscal-discipline-act-2561"
    section_no: str  # Arabic digits, e.g. "37" — or "preamble" / "note"
    section_title_th: str | None  # running หมวด/ส่วนที่ context, not a per-section title
    text: str

    @property
    def act_name_th(self) -> str:
        return ACTS[self.act_code].name_th

    @property
    def regulation_code(self) -> str:
        if self.section_no in ("preamble", "note"):
            return f"{self.act_code}/{self.section_no}"
        return f"{self.act_code}/{ACTS[self.act_code].code_prefix}{self.section_no}"


def clean_page_text(page_text: str) -> str:
    """Strip page furniture and repair the extraction artifacts, line by line."""
    lines = []
    for line in page_text.splitlines():
        if _PAGE_HEADER.match(line):
            continue
        line = _SPACE_BEFORE_COMBINING.sub(r"\1", line)
        line = thai_normalize(line)
        line = re.sub(r"[ \t]+", " ", line).strip()
        if line:
            lines.append(line)
    return "\n".join(lines)


def extract_act_text(pdf_path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(pdf_path))
    return "\n".join(clean_page_text(page.extract_text() or "") for page in reader.pages)


def _is_heading_title(line: str) -> bool:
    """The name line printed under a bare "หมวด ๓" / "ส่วนที่ ๑" heading.

    In ราชกิจจานุเบกษา layout that next line is ALWAYS the heading's name, so
    the checks are structural; the length cap (some names run >60 chars, e.g.
    Procurement Act หมวด ๒ at 62) is only a sanity bound.
    """
    line = line.strip()
    return (
        bool(line)
        and len(line) <= 100
        and not _ANY_SECTION_START.match(line)
        and not _CHAPTER_START.match(line)
        and not _PART_START.match(line)
    )


def split_sections(act_text: str, act_code: str) -> list[ActSection]:
    if act_code not in ACTS:
        raise ValueError(f"unknown act_code {act_code!r}; add it to ACTS first")
    section_start = _section_start(ACTS[act_code].section_word)
    sections: list[ActSection] = []
    chapter: str | None = None
    part: str | None = None
    current_no = "preamble"
    current_title: str | None = None
    current_lines: list[str] = []
    expected_next = 1  # monotonic guard against line-wrapped มาตรา references
    # ระเบียบ have a third, unnumbered heading level: topic lines between a
    # หมวด/ส่วนที่ block and its first clause (e.g. "การจัดทำร่างขอบเขตของงาน...").
    # While in_gap, lines are topic context for the NEXT section — never body
    # text of the previous one (that produced phantom duplicate clauses).
    in_gap = False
    gap_topic: list[str] = []

    def emit() -> None:
        text = "\n".join(current_lines).strip()
        if text:
            sections.append(ActSection(act_code, current_no, current_title, text))
        current_lines.clear()

    def heading() -> str | None:
        topic = " ".join(gap_topic) if gap_topic else None
        parts = [p for p in (chapter, part, topic) if p]
        return " / ".join(parts) if parts else None

    lines = act_text.splitlines()
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]

        if _COUNTERSIGN.match(line):
            emit()
            while i < n and not _END_NOTE.match(lines[i]):
                i += 1  # drop the countersignature block
            if i < n:
                current_no, current_title = "note", None
                current_lines.extend(lines[i:])
                emit()
            return sections

        if _CHAPTER_START.match(line):
            emit()
            chapter, part = line.strip(), None
            gap_topic.clear()
            in_gap = True
            if i + 1 < n and _is_heading_title(lines[i + 1]):
                chapter = f"{chapter} {lines[i + 1].strip()}"
                i += 1
            i += 1
            continue

        if _PART_START.match(line):
            emit()
            part = line.strip()
            gap_topic.clear()
            in_gap = True
            if i + 1 < n and _is_heading_title(lines[i + 1]):
                part = f"{part} {lines[i + 1].strip()}"
                i += 1
            i += 1
            continue

        m = section_start.match(line)
        if m and int(m.group(1).translate(_THAI_DIGITS)) == expected_next:
            emit()
            current_no = m.group(1).translate(_THAI_DIGITS)
            current_title = heading()
            expected_next += 1
            in_gap = False
            gap_topic.clear()
            current_lines.append(line.strip())
            i += 1
            continue

        if in_gap:
            gap_topic.append(line.strip())
        else:
            current_lines.append(line)
        i += 1

    emit()
    return sections


def parse_act(pdf_path: Path, act_code: str) -> list[ActSection]:
    return split_sections(extract_act_text(pdf_path), act_code)
