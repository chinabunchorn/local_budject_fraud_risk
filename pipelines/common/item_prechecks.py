"""Item-level deterministic findings: unit-price spikes, vendor locks, and
standard-price comparison. Same contract as common/prechecks.py findings —
factual, non-accusatory {name, status, detail, values} dicts; the verdict
enum stays reserved for the guardrails-validated LLM path.

Thresholds are explicit constants, not tuned silently:
  UNIT_SPIKE_THRESHOLD — a ≥30% year-over-year rise in the unit price of the
  SAME item is worth an auditor's attention (unlike whole-project budgets,
  the item is identical across years, so a much lower bar than the 100%
  yoy_budget_anomaly threshold is justified).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

UNIT_SPIKE_THRESHOLD = Decimal("0.30")


@dataclass(frozen=True)
class ItemFact:
    """One project's extracted line for a tracked item, joined with its
    procurement facts (winner from bids; None when no winner recorded)."""

    project_id: str
    sub_district_id: str
    fiscal_year: int
    project_name_th: str
    item_key: str
    label_th: str
    quantity: Decimal
    unit_th: str
    unit_price: Decimal
    total_amount: Decimal
    winner_name: str | None
    bid_count: int
    procurement_method: str | None


@dataclass(frozen=True)
class StandardPrice:
    item_key: str
    description_th: str
    unit_price: Decimal


def _finding(name: str, status: str, detail: str, **values: object) -> dict:
    return {"name": name, "status": status, "detail": detail, "values": values}


def _pct(new: Decimal, old: Decimal) -> Decimal:
    return (new - old) / old * 100


def _match_name(name: str) -> str:
    return "".join(name.split())


def _groups(facts: list[ItemFact]) -> dict[tuple[str, str], list[ItemFact]]:
    """Group by (sub_district, item), deduped on project_id — overlapping
    source chunks can surface the same line twice; one project is one fact."""
    grouped: dict[tuple[str, str], dict[str, ItemFact]] = {}
    for f in facts:
        grouped.setdefault((f.sub_district_id, f.item_key), {}).setdefault(f.project_id, f)
    return {
        k: sorted(v.values(), key=lambda f: f.fiscal_year) for k, v in grouped.items()
    }


def compute_item_findings(
    facts: list[ItemFact], standards: dict[str, StandardPrice]
) -> dict[str, list[dict]]:
    """All item findings, keyed by project_id (a group finding attaches to
    every member project so the auditor sees the context from either year)."""
    out: dict[str, list[dict]] = {f.project_id: [] for f in facts}

    for (_, item_key), group in _groups(facts).items():
        label = group[0].label_th

        # --- unit-price YoY spike over consecutive recorded years ------------
        spikes: list[tuple[ItemFact, ItemFact, Decimal]] = []
        for prev, cur in zip(group, group[1:], strict=False):
            if prev.unit_price > 0:
                growth = (cur.unit_price - prev.unit_price) / prev.unit_price
                if growth >= UNIT_SPIKE_THRESHOLD:
                    spikes.append((prev, cur, growth))
        for prev, cur, _growth in spikes:
            same_vendor = (
                prev.winner_name is not None
                and cur.winner_name is not None
                and _match_name(prev.winner_name) == _match_name(cur.winner_name)
            )
            severity = "HIGH" if same_vendor else "MEDIUM"
            detail = (
                f"ราคาต่อหน่วยของ{label}เพิ่มขึ้น {_pct(cur.unit_price, prev.unit_price):.1f}% "
                f"ระหว่างปีงบประมาณ {prev.fiscal_year} ({prev.unit_price:,.2f} บาท/{prev.unit_th}) "
                f"และ {cur.fiscal_year} ({cur.unit_price:,.2f} บาท/{cur.unit_th}) "
                f"— ควรตรวจสอบเพิ่มเติม"
            )
            values: dict[str, object] = {
                "item_key": item_key,
                "item_label": label,
                "from_year": prev.fiscal_year,
                "to_year": cur.fiscal_year,
                "unit_price_from": str(prev.unit_price),
                "unit_price_to": str(cur.unit_price),
                "quantity_from": str(prev.quantity),
                "quantity_to": str(cur.quantity),
                "growth_pct": f"{_pct(cur.unit_price, prev.unit_price):.1f}",
                "severity": severity,
            }
            if same_vendor:
                values["repeat_vendor"] = cur.winner_name
                values["justification"] = (
                    f"[ระดับความเสี่ยง: สูง] ราคาต่อหน่วยของ{label}เพิ่มขึ้น "
                    f"{_pct(cur.unit_price, prev.unit_price):.1f}% "
                    f"({prev.unit_price:,.2f} → {cur.unit_price:,.2f} บาท/{cur.unit_th}) "
                    f"ระหว่างปี {prev.fiscal_year}–{cur.fiscal_year} "
                    f"โดยจัดซื้อรายการเดียวกันจากผู้ขายรายเดิม ({cur.winner_name}) "
                    f"ทั้งสองปี; ควรตรวจสอบเพิ่มเติมโดยผู้ตรวจสอบเป็นผู้วินิจฉัยขั้นสุดท้าย"
                )
            for member in (prev, cur):
                out[member.project_id].append(
                    _finding("unit_price_yoy_spike", "FLAG", detail, **values)
                )

        # --- vendor lock: same winner across the recurring item's years ------
        winners = {_match_name(f.winner_name) for f in group if f.winner_name}
        if len(group) >= 2 and len(winners) == 1 and all(f.winner_name for f in group):
            years = [f.fiscal_year for f in group]
            single_bid_years = [f.fiscal_year for f in group if f.bid_count <= 1]
            detail = (
                f"จัดซื้อ{label}จากผู้ขายรายเดียวกัน ({group[-1].winner_name}) "
                f"ต่อเนื่อง {len(group)} ปีงบประมาณ ({', '.join(map(str, years))})"
                + (
                    " โดยแต่ละครั้งมีผู้เสนอราคารายเดียว"
                    if len(single_bid_years) == len(group)
                    else ""
                )
                + " — ควรตรวจสอบการเปิดโอกาสแข่งขัน"
            )
            for member in group:
                out[member.project_id].append(
                    _finding(
                        "item_vendor_lock",
                        "FLAG",
                        detail,
                        item_key=item_key,
                        item_label=label,
                        vendor=group[-1].winner_name,
                        fiscal_years=[f.fiscal_year for f in group],
                        single_bid_years=single_bid_years,
                        cumulative_amount=str(sum(f.total_amount for f in group)),
                    )
                )

        # --- unit price vs the curated standard reference price --------------
        standard = standards.get(item_key)
        for member in group:
            if standard is None:
                out[member.project_id].append(
                    _finding(
                        "unit_price_vs_standard",
                        "NA",
                        f"ไม่มีราคามาตรฐานอ้างอิงสำหรับ{label}ในระบบ",
                        item_key=item_key,
                    )
                )
                continue
            ratio = member.unit_price / standard.unit_price * 100
            over = member.unit_price > standard.unit_price
            detail = (
                f"ราคาต่อหน่วยปี {member.fiscal_year} ({member.unit_price:,.2f} บาท/{member.unit_th}) "
                f"คิดเป็น {ratio:.1f}% ของราคามาตรฐาน ({standard.unit_price:,.2f} บาท) "
                + ("— สูงกว่าราคามาตรฐาน ควรตรวจสอบเพิ่มเติม" if over else "— ไม่เกินราคามาตรฐาน")
            )
            out[member.project_id].append(
                _finding(
                    "unit_price_vs_standard",
                    "FLAG" if over else "OK",
                    detail,
                    item_key=item_key,
                    item_label=label,
                    fiscal_year=member.fiscal_year,
                    unit_price=str(member.unit_price),
                    standard_unit_price=str(standard.unit_price),
                    ratio_pct=f"{ratio:.1f}",
                )
            )

    return out


ITEM_CHECK_NAMES = ("unit_price_yoy_spike", "item_vendor_lock", "unit_price_vs_standard")
