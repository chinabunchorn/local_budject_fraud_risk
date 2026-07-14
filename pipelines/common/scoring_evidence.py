"""Per-project evidence assembly for risk scoring (Phase G).

Turns the curated tables into the three free-form blocks the v1 user template
expects, deterministically and from committed data only:

- `budget_lines`  → the structured financial facts + the Phase-F
  `precheck_results` findings (the settled arithmetic — the model reasons over
  it, it never recomputes numbers);
- `document_excerpts` → real project chunks, each labelled with its `chunk_id`
  so the model's `Citation`s resolve against the `chunks` table (guardrails
  re-checks existence);
- `regulation_context` → exactly the regulation sections the factor templates
  reference, fetched from the regulations index and labelled with their
  `regulation_id` (guardrails re-checks resolution).

No LLM here — this is deterministic prompt context assembly.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import Engine, text

from common.prompts import PromptBundle

# project doc_types worth citing, in priority order
_EXCERPT_DOC_TYPES = ("contract_summary", "bk01", "bk06", "tor", "tech_spec", "boq")
_MAX_EXCERPTS = 24
_MAX_EXCERPT_CHARS = 3500  # keep the whole prompt under --max-model-len 8192
_MAX_REG_CHARS = 700

_METHOD_TH = {
    "E_BIDDING": "ประกวดราคาอิเล็กทรอนิกส์ (e-bidding)",
    "SELECTION": "คัดเลือก",
    "SPECIFIC": "เฉพาะเจาะจง",
}
_REG_CODE = re.compile(r"`([a-z0-9-]+/[a-z0-9.]+)`")


@dataclass(frozen=True)
class ProjectEvidence:
    project_id: str
    sub_district: str
    project_name: str
    fiscal_year: int
    budget_total: str
    budget_lines: str
    document_excerpts: str
    regulation_context: str


def regulation_ids_in(bundle: PromptBundle) -> list[str]:
    """The regulation_ids the factor templates reference (guardrails-resolvable)."""
    codes: set[str] = set()
    for template in bundle.factors.values():
        codes.update(_REG_CODE.findall(template))
    return sorted(codes)


def _amount(value) -> str:
    return f"{Decimal(value):,.2f}" if value is not None else "—"


def _budget_block(proj, bids, checks) -> str:
    method = _METHOD_TH.get(proj.procurement_method, proj.procurement_method or "—")
    lines = [
        f"- วิธีจัดซื้อจัดจ้าง: {method}",
        f"- ราคากลาง: {_amount(proj.reference_price)} บาท",
        f"- ราคาที่ทำสัญญากับผู้ชนะ: {_amount(proj.contract_price)} บาท",
    ]
    if bids:
        lines.append("- ผู้เสนอราคา (จากข้อมูลสาระสำคัญในสัญญา):")
        lines.extend(
            f"  • {b.bidder_name_th} — {_amount(b.bid_amount)} บาท"
            f"{' (ผู้ชนะ)' if b.is_winner else ''}"
            for b in bids
        )
    check_list = checks if isinstance(checks, list) else (json.loads(checks) if checks else [])
    if check_list:
        lines.append("- ผลการตรวจสอบเชิงกฎเกณฑ์อัตโนมัติ (คำนวณด้วยรหัส ไม่ใช่โมเดล):")
        for check in check_list:
            values = check.get("values", {})
            severity = f" [{values['severity']}]" if values.get("severity") else ""
            lines.append(
                f"  • {check['name']}: {check['status']}{severity} — {check.get('detail', '')}"
            )
            if values.get("justification"):
                lines.append(f"    {values['justification']}")
    return "\n".join(lines)


def _excerpt_block(chunks) -> str:
    ordered = sorted(
        chunks, key=lambda c: (_EXCERPT_DOC_TYPES.index(c.doc_type), c.chunk_index)
    )
    out: list[str] = []
    total = 0
    for chunk in ordered[:_MAX_EXCERPTS]:
        body = chunk.text.strip()
        if out and total + len(body) > _MAX_EXCERPT_CHARS:
            break
        page = f", หน้า {chunk.page}" if chunk.page else ""
        out.append(f"[chunk_id: {chunk.id}] (เอกสาร: {chunk.doc_type}{page})\n{body}")
        total += len(body)
    return "\n\n".join(out) if out else "(ไม่มีข้อความเอกสารที่สกัดได้)"


def _regulation_block(regs) -> str:
    out = []
    for reg in regs:
        title = f" {reg.section_title_th}" if reg.section_title_th else ""
        body = reg.text.strip()[:_MAX_REG_CHARS]
        out.append(
            f"[regulation_id: {reg.regulation_code}] {reg.act_name_th} "
            f"มาตรา/ข้อ {reg.section_no}{title}\n{body}"
        )
    return "\n\n".join(out) if out else "(ไม่มีบริบทกฎหมาย)"


def assemble_evidence(
    engine: Engine, project_id: str, bundle: PromptBundle
) -> ProjectEvidence | None:
    codes = regulation_ids_in(bundle)
    with engine.connect() as conn:
        proj = conn.execute(
            text(
                """
                SELECT p.name_th, p.fiscal_year, p.budget_total, p.reference_price,
                       p.contract_price, p.procurement_method, sd.name_th AS sub_district
                FROM projects p JOIN sub_districts sd ON sd.id = p.sub_district_id
                WHERE p.id = :pid
                """
            ),
            {"pid": project_id},
        ).one_or_none()
        if proj is None:
            return None
        bids = conn.execute(
            text(
                "SELECT bidder_name_th, bid_amount, is_winner FROM bids "
                "WHERE project_id = :pid ORDER BY bid_amount"
            ),
            {"pid": project_id},
        ).fetchall()
        checks = conn.execute(
            text("SELECT checks FROM precheck_results WHERE project_id = :pid"),
            {"pid": project_id},
        ).scalar_one_or_none()
        chunks = conn.execute(
            text(
                """
                SELECT c.id, c.text, c.page, c.chunk_index, d.doc_type
                FROM chunks c JOIN documents d ON d.id = c.document_id
                WHERE d.project_id = :pid AND d.doc_type = ANY(:types)
                """
            ),
            {"pid": project_id, "types": list(_EXCERPT_DOC_TYPES)},
        ).fetchall()
        regs = (
            conn.execute(
                text(
                    "SELECT regulation_code, act_name_th, section_no, section_title_th, text "
                    "FROM regulations WHERE regulation_code = ANY(:codes)"
                ),
                {"codes": codes},
            ).fetchall()
            if codes
            else []
        )

    return ProjectEvidence(
        project_id=str(project_id),
        sub_district=proj.sub_district,
        project_name=proj.name_th,
        fiscal_year=proj.fiscal_year,
        budget_total=_amount(proj.budget_total),
        budget_lines=_budget_block(proj, bids, checks),
        document_excerpts=_excerpt_block(chunks),
        regulation_context=_regulation_block(regs),
    )
