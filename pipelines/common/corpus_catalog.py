"""Corpus catalog — normalizes the data team's real folder tree (Phase A).

Walks `data/corpus/real_data/` (layout per docs/DATA_TEAM_GUIDE.md), detects
true file types by magic bytes (several บก.01/บก.๐๖ files arrive without a
.pdf extension), infers canonical doc_types from Thai filenames, normalizes
years (`ปี 68` and `2568` both → 2568) and whitespace damage, and emits the
entries the manifest generator (Phase C) and MinIO upload build on.

Originals are never renamed — normalization lives in `normalized_key` only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

REFERENCE_DIR = "เอกสารกลาง"
BUDGET_REPORT_DIR = "รายงานงบประมาณ"
PROJECTS_DIR = "โครงการ"

# canonical doc_type slugs (from docs/DATA_TEAM_GUIDE.md + observed extras)
CONTRACT_SUMMARY = "contract_summary"
BOQ = "boq"
TOR = "tor"
TECH_SPEC = "tech_spec"
BK01 = "bk01"
BK06 = "bk06"
WINNER_ANNOUNCEMENT = "winner_announcement"
PRICE_APPROVAL_MEMO = "price_approval_memo"
BUDGET_REPORT = "budget_report"
REFERENCE_STANDARD = "reference_standard"

_THAI_DIGITS = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")
_LEADING_COMBINING = re.compile(r"^[ัิ-ฺ็-๎]+")
_YEAR_FOLDER = re.compile(r"^(?:ปี\s*)?([0-9๐-๙]{2,4})$")
_BK_NUMBER = re.compile(r"บก[\s.]*([0-9๐-๙]{1,2})")

# order matters: first match wins
_DOC_TYPE_RULES: tuple[tuple[str, str], ...] = (
    (r"สาระสำคัญ", CONTRACT_SUMMARY),
    (r"ประกาศผู้ชนะ", WINNER_ANNOUNCEMENT),
    (r"อนุมัติราคากลาง", PRICE_APPROVAL_MEMO),
    (r"boq|ปร[\s.]*[45๔๕]", BOQ),
    (r"tor|ขอบเขตของงาน", TOR),
    (r"เทคนิค", TECH_SPEC),
)


@dataclass(frozen=True)
class CorpusFile:
    source_path: str  # relative to the corpus root, exactly as on disk
    scope: str  # PROJECT | SUB_DISTRICT | REFERENCE
    normalized_key: str  # MinIO object key
    is_pdf: bool
    sub_district: str | None = None
    fiscal_year: int | None = None
    project_name: str | None = None
    doc_type: str | None = None
    anomalies: tuple[str, ...] = field(default_factory=tuple)


def clean_component(name: str) -> str:
    """Strip edge whitespace, leading combining marks, collapse space runs."""
    name = _LEADING_COMBINING.sub("", name.strip())
    return re.sub(r"\s+", " ", name)


def normalize_year(folder: str) -> int | None:
    """"ปี 68" / "ปี 67 " / "2565" / "๒๕๖๖" → 4-digit พ.ศ."""
    m = _YEAR_FOLDER.match(clean_component(folder))
    if not m:
        return None
    year = int(m.group(1).translate(_THAI_DIGITS))
    if year < 100:
        year += 2500
    return year if 2500 <= year <= 2600 else None


def infer_doc_type(filename: str) -> str | None:
    name = clean_component(filename).lower()
    for pattern, doc_type in _DOC_TYPE_RULES:
        if re.search(pattern, name):
            return doc_type
    if m := _BK_NUMBER.search(name):
        number = int(m.group(1).translate(_THAI_DIGITS))
        if number == 1:
            return BK01
        if number == 6:
            return BK06
    return None


def _is_pdf(path: Path) -> bool:
    with path.open("rb") as fh:
        return fh.read(5) == b"%PDF-"


def _basename(filename: str, doc_type: str | None) -> tuple[str, list[str]]:
    """Canonical basename for the MinIO key; always .pdf-suffixed."""
    anomalies = []
    cleaned = clean_component(filename)
    if cleaned != filename:
        anomalies.append("filename-normalized")
    if doc_type in (CONTRACT_SUMMARY, BOQ, TOR, TECH_SPEC, BK01, BK06,
                    WINNER_ANNOUNCEMENT, PRICE_APPROVAL_MEMO):
        return f"{doc_type}.pdf", anomalies
    if not cleaned.lower().endswith(".pdf"):
        anomalies.append("extension-added")
        return f"{cleaned}.pdf", anomalies
    return cleaned, anomalies


def walk_corpus(root: Path) -> list[CorpusFile]:
    entries: list[CorpusFile] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name.startswith("."):
            continue
        if path.suffix.lower() == ".md":
            continue  # data-team guide copies — never corpus content
        rel = path.relative_to(root)
        parts = list(rel.parts)
        anomalies: list[str] = []
        if any(p != clean_component(p) for p in parts[:-1]):
            anomalies.append("dirname-normalized")

        is_pdf = _is_pdf(path)
        if not is_pdf:
            anomalies.append("not-a-pdf")

        top = clean_component(parts[0])
        if top == REFERENCE_DIR:
            doc_type = REFERENCE_STANDARD
            base, extra = _basename(parts[-1], None)
            key_dirs = "/".join(clean_component(p) for p in parts[1:-1])
            entries.append(
                CorpusFile(
                    source_path=str(rel),
                    scope="REFERENCE",
                    normalized_key="/".join(filter(None, ["reference", key_dirs, base])),
                    is_pdf=is_pdf,
                    doc_type=doc_type,
                    anomalies=tuple(anomalies + extra),
                )
            )
            continue

        sub_district = top
        section = clean_component(parts[1]) if len(parts) > 2 else None
        if section == BUDGET_REPORT_DIR:
            base, extra = _basename(parts[-1], None)
            # fiscal year hint from the filename, e.g. "รายงานงบ66.pdf"
            year_match = re.search(r"([0-9๐-๙]{2,4})", clean_component(parts[-1]))
            fiscal_year = normalize_year(year_match.group(1)) if year_match else None
            entries.append(
                CorpusFile(
                    source_path=str(rel),
                    scope="SUB_DISTRICT",
                    normalized_key=f"{sub_district}/budget_reports/{base}",
                    is_pdf=is_pdf,
                    sub_district=sub_district,
                    fiscal_year=fiscal_year,
                    doc_type=BUDGET_REPORT,
                    anomalies=tuple(anomalies + extra),
                )
            )
            continue

        if section == PROJECTS_DIR and len(parts) == 5:
            fiscal_year = normalize_year(parts[2])
            if fiscal_year is None:
                anomalies.append("unparseable-year-folder")
            project_name = clean_component(parts[3])
            doc_type = infer_doc_type(parts[4])
            if doc_type is None:
                anomalies.append("unknown-doc-type")
            base, extra = _basename(parts[4], doc_type)
            entries.append(
                CorpusFile(
                    source_path=str(rel),
                    scope="PROJECT",
                    normalized_key=(
                        f"{sub_district}/projects/{fiscal_year or 'unknown'}/"
                        f"{project_name}/{base}"
                    ),
                    is_pdf=is_pdf,
                    sub_district=sub_district,
                    fiscal_year=fiscal_year,
                    project_name=project_name,
                    doc_type=doc_type,
                    anomalies=tuple(anomalies + extra),
                )
            )
            continue

        entries.append(
            CorpusFile(
                source_path=str(rel),
                scope="REFERENCE",
                normalized_key=f"unclassified/{clean_component(parts[-1])}",
                is_pdf=is_pdf,
                anomalies=tuple(anomalies + ["unrecognized-layout"]),
            )
        )
    return entries


def report(entries: list[CorpusFile]) -> str:
    lines = [f"total files: {len(entries)}"]
    for scope in ("PROJECT", "SUB_DISTRICT", "REFERENCE"):
        scoped = [e for e in entries if e.scope == scope]
        lines.append(f"  {scope}: {len(scoped)}")
    projects = sorted(
        {(e.sub_district, e.fiscal_year, e.project_name) for e in entries if e.project_name}
    )
    lines.append(f"projects: {len(projects)}")
    by_type: dict[str, int] = {}
    for e in entries:
        by_type[e.doc_type or "UNKNOWN"] = by_type.get(e.doc_type or "UNKNOWN", 0) + 1
    lines.append("doc_types: " + ", ".join(f"{k}={v}" for k, v in sorted(by_type.items())))
    flagged = [e for e in entries if e.anomalies]
    lines.append(f"files with anomalies: {len(flagged)}")
    for e in flagged:
        lines.append(f"  {e.source_path} → {', '.join(e.anomalies)}")
    non_pdf = [e for e in entries if not e.is_pdf]
    lines.append(f"non-PDF files: {len(non_pdf)}")
    return "\n".join(lines)


if __name__ == "__main__":
    import sys

    root = Path(sys.argv[1] if len(sys.argv) > 1 else "../data/corpus/real_data")
    print(report(walk_corpus(root)))
