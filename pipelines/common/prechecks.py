"""Deterministic pre-checks over extracted accounting facts (Phase F).

Pure arithmetic — no LLM, no float — producing factual, non-accusatory
findings. Each finding is `{name, status, detail, values}` where status is:

    OK   — checked, nothing notable
    WARN — a pattern an auditor should look at
    FLAG — a hard inconsistency or rule mismatch
    NA   — could not be checked (a needed figure was not extracted)

These land in `precheck_results.checks` and are the settled evidence the
Phase-G model reasons over. Wording stays neutral ("requires review", never a
verdict) per the flag-never-accuse rule in CLAUDE.md.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal

from common.thai_num import normalize_digits

# เฉพาะเจาะจง is permitted up to this ราคากลาง; above it the e-bidding route
# applies (ระเบียบกระทรวงการคลัง ข้อ ๒๐ — the threshold-splitting citation).
SPECIFIC_METHOD_CEILING = Decimal("500000")
# how close to the ceiling still counts as "just under" and worth a look
THRESHOLD_PROXIMITY = Decimal("0.05")
# rounding slack when comparing two independently-stated ราคากลาง figures
CROSS_CHECK_TOLERANCE = Decimal("0.01")
# a recurring project whose year-over-year budget grows by at least this much
# (100% = the budget at least doubles) trips yoy_budget_anomaly (fixed,
# deterministic — tune here only)
YOY_GROWTH_THRESHOLD = Decimal("1.00")
# a contractor winning the recurring project in at least this share of the
# years it ran (and in ≥2 distinct years) is the "same contractor most years"
# escalation to HIGH severity
CONTRACTOR_CONCENTRATION_RATIO = Decimal("0.5")


@dataclass(frozen=True)
class BidFact:
    name: str
    amount: Decimal
    is_winner: bool


@dataclass(frozen=True)
class ProjectFacts:
    procurement_method: str | None = None
    budget: Decimal | None = None
    reference_price: Decimal | None = None
    contract_price: Decimal | None = None
    bids: list[BidFact] = field(default_factory=list)
    form_reference_price: Decimal | None = None  # บก.01/บก.๐๖ ราคากลาง
    boq_total: Decimal | None = None
    present_doc_types: set[str] = field(default_factory=set)


def _s(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


def _ratio(part: Decimal, whole: Decimal) -> Decimal:
    return (part / whole).quantize(Decimal("0.0001"))


def _finding(name: str, status: str, detail: str, **values: object) -> dict:
    return {"name": name, "status": status, "detail": detail, "values": values}


def _cross_check_reference_price(f: ProjectFacts) -> dict:
    a, b = f.reference_price, f.form_reference_price
    if a is None or b is None:
        return _finding(
            "reference_price_cross_check", "NA",
            "contract-summary and บก.01/บก.๐๖ ราคากลาง not both available",
            contract_summary=_s(a), reference_form=_s(b),
        )
    delta = abs(a - b)
    rel = _ratio(delta, b) if b else Decimal("0")
    status = "OK" if rel <= CROSS_CHECK_TOLERANCE else "FLAG"
    return _finding(
        "reference_price_cross_check", status,
        "ราคากลาง on the contract summary matches the บก. form"
        if status == "OK"
        else "ราคากลาง differs between the contract summary and the บก. form",
        contract_summary=_s(a), reference_form=_s(b), abs_delta=_s(delta),
        relative_delta=_s(rel),
    )


def _boq_vs_form(f: ProjectFacts) -> dict:
    total, ref = f.boq_total, f.form_reference_price
    if total is None or ref is None:
        return _finding(
            "boq_vs_bk01_total", "NA",
            "BOQ grand total or บก.01 ราคากลาง not available",
            boq_total=_s(total), reference_form=_s(ref),
        )
    delta = abs(total - ref)
    rel = _ratio(delta, ref) if ref else Decimal("0")
    status = "OK" if rel <= CROSS_CHECK_TOLERANCE else "WARN"
    return _finding(
        "boq_vs_bk01_total", status,
        "BOQ grand total reconciles with the บก.01 ราคากลาง"
        if status == "OK"
        else "BOQ grand total does not reconcile with the บก.01 ราคากลาง",
        boq_total=_s(total), reference_form=_s(ref), abs_delta=_s(delta),
        relative_delta=_s(rel),
    )


def _reference_within_budget(f: ProjectFacts) -> dict:
    ref, budget = f.reference_price, f.budget
    if ref is None or budget is None or budget == 0:
        return _finding(
            "reference_within_budget", "NA",
            "budget or ราคากลาง not available",
            budget=_s(budget), reference_price=_s(ref),
        )
    utilization = _ratio(ref, budget)
    status = "FLAG" if ref > budget else "OK"
    return _finding(
        "reference_within_budget", status,
        "ราคากลาง exceeds the allocated budget"
        if status == "FLAG"
        else "ราคากลาง is within the allocated budget",
        budget=_s(budget), reference_price=_s(ref), utilization=_s(utilization),
    )


def _contract_within_reference(f: ProjectFacts) -> dict:
    contract, ref = f.contract_price, f.reference_price
    if contract is None or ref is None or ref == 0:
        return _finding(
            "contract_within_reference", "NA",
            "contract price or ราคากลาง not available",
            contract_price=_s(contract), reference_price=_s(ref),
        )
    of_reference = _ratio(contract, ref)
    savings = _ratio(ref - contract, ref)
    status = "FLAG" if contract > ref else "OK"
    return _finding(
        "contract_within_reference", status,
        "contract price exceeds ราคากลาง"
        if status == "FLAG"
        else "contract price is at or below ราคากลาง",
        contract_price=_s(contract), reference_price=_s(ref),
        contract_of_reference=_s(of_reference), savings_ratio=_s(savings),
    )


def _bid_competition(f: ProjectFacts) -> dict:
    n = len(f.bids)
    competitive = f.procurement_method in ("E_BIDDING", "SELECTION")
    winner = next((b for b in f.bids if b.is_winner), None)
    values: dict[str, object] = {"bidder_count": n, "procurement_method": f.procurement_method}
    lowest: Decimal | None = None
    if n >= 2:
        amounts = sorted(b.amount for b in f.bids)
        lowest = amounts[0]
        values["lowest_bid"] = _s(lowest)
        values["bid_spread_ratio"] = _s(_ratio(amounts[-1] - lowest, lowest)) if lowest else None
    if winner is not None:
        values["winning_bid"] = _s(winner.amount)
        if lowest is not None:
            values["winner_is_lowest"] = winner.amount <= lowest

    if n == 0:
        return _finding("bid_competition", "NA", "no bidders extracted", **values)
    if competitive and n <= 1:
        return _finding(
            "bid_competition", "WARN",
            "a competitive route drew a single quotation — competition requires review",
            **values,
        )
    if winner is not None and lowest is not None and winner.amount > lowest:
        return _finding(
            "bid_competition", "WARN",
            "the winning bid was not the lowest quotation — selection rationale requires review",
            **values,
        )
    return _finding(
        "bid_competition", "OK",
        f"{n} quotation(s) recorded for a {f.procurement_method or 'unknown'} route",
        **values,
    )


def _procurement_threshold(f: ProjectFacts) -> dict:
    amount = f.reference_price or f.budget
    if amount is None or f.procurement_method is None:
        return _finding(
            "procurement_threshold", "NA",
            "ราคากลาง/budget or procurement method not available",
            amount=_s(amount), procurement_method=f.procurement_method,
            ceiling=_s(SPECIFIC_METHOD_CEILING),
        )
    values = {
        "amount": _s(amount),
        "procurement_method": f.procurement_method,
        "ceiling": _s(SPECIFIC_METHOD_CEILING),
    }
    if f.procurement_method == "SPECIFIC" and amount > SPECIFIC_METHOD_CEILING:
        return _finding(
            "procurement_threshold", "FLAG",
            "เฉพาะเจาะจง used above the ๕๐๐,๐๐๐ ceiling for that route (ข้อ ๒๐)",
            **values,
        )
    near = SPECIFIC_METHOD_CEILING * (Decimal("1") - THRESHOLD_PROXIMITY)
    if f.procurement_method == "SPECIFIC" and near <= amount <= SPECIFIC_METHOD_CEILING:
        return _finding(
            "procurement_threshold", "WARN",
            "ราคากลาง sits just under the ๕๐๐,๐๐๐ ceiling — verify no scope splitting",
            **values,
        )
    return _finding(
        "procurement_threshold", "OK",
        "procurement route is consistent with the ราคากลาง against the ceiling",
        **values,
    )


# expected document set per route (see docs/DATA_TEAM_GUIDE.md doc_types).
# a reference-price form is either บก.01 (construction) or บก.๐๖ (non-construction).
_EXPECTED: dict[str | None, tuple[str, ...]] = {
    "E_BIDDING": ("contract_summary", "reference_form", "tor", "winner_announcement"),
    "SELECTION": ("contract_summary", "reference_form", "tor"),
    "SPECIFIC": ("contract_summary",),
    None: ("contract_summary",),
}


def _expected_documents(f: ProjectFacts) -> dict:
    present = f.present_doc_types
    has_reference_form = bool(present & {"bk01", "bk06"})
    missing: list[str] = []
    for expected in _EXPECTED.get(f.procurement_method, _EXPECTED[None]):
        if expected == "reference_form":
            if not has_reference_form:
                missing.append("bk01/bk06")
        elif expected not in present:
            missing.append(expected)
    status = "WARN" if missing else "OK"
    return _finding(
        "expected_documents", status,
        "expected documents for the route are present"
        if not missing
        else "expected documents are missing for the route",
        procurement_method=f.procurement_method,
        present=sorted(present),
        missing=missing,
    )


def compute_prechecks(facts: ProjectFacts) -> list[dict]:
    """Run every single-project check; order is stable so re-runs produce
    identical JSONB. The cross-project YoY check is added by
    `compute_yoy_findings` (it needs the whole sub-district portfolio)."""
    return [
        _cross_check_reference_price(facts),
        _boq_vs_form(facts),
        _reference_within_budget(facts),
        _contract_within_reference(facts),
        _bid_competition(facts),
        _procurement_threshold(facts),
        _expected_documents(facts),
    ]


# ---------------------------------------------------------------------------
# Year-over-year recurring-project redundancy + contractor concentration.
#
# A cross-project, cross-year check over the curated `projects`/`bids` tables
# (no PDF parsing): recurring projects (same sub-district, same work-type and
# location across fiscal years) whose budget spikes year-over-year are FLAGged,
# and when the same contractor won the recurring project across most of those
# years the finding escalates to severity HIGH with a factual justification.
# Deterministic and non-accusatory throughout.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProjectRecord:
    project_id: str
    sub_district_id: str
    fiscal_year: int
    name_th: str
    budget: Decimal | None = None
    winner: str | None = None  # winning contractor (bids.bidder_name_th where is_winner)


# canonical work-type → filename-style keywords (searched on a de-spaced,
# ค.ส.ล./คอนกรีตเสริมเหล็ก-normalized name). First match wins.
_WORK_TYPES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("ถนนคสล", ("ถนนคสล",)),
    ("ถนนดิน", ("ถนนดิน",)),
    ("ถนนลูกรัง", ("ถนนลูกรัง", "ถนนลุกรัง")),
    ("ท่อระบายน้ำ", ("ท่อระบายน้ำ",)),
    ("ห้องน้ำ", ("ห้องน้ำ",)),
    ("อาคาร", ("อาคาร",)),
    ("กล้องวงจรปิด", ("กล้อง", "cctv")),
    ("ซ่อมรถ", ("ซ่อมรถ", "ซ่อมแซมรถ")),
    ("จัดซื้อรถ", ("จัดซื้อรถ", "รถบรรทุก")),
)


def _work_type(name: str) -> str | None:
    squashed = (
        normalize_digits(name)
        .replace(" ", "")
        .replace(".", "")
        .replace("คอนกรีตเสริมเหล็ก", "คสล")
    ).lower()
    for label, keywords in _WORK_TYPES:
        if any(kw in squashed for kw in keywords):
            return label
    return None


def _locations(name: str) -> tuple[set[str], set[str]]:
    """(หมู่ numbers, บ้าน names) — the location fingerprint of a project."""
    norm = normalize_digits(name)
    moo = set(re.findall(r"หมู่\s*(?:ที่)?\s*(\d+)", norm))
    villages = {
        re.sub(r"[^ก-๙a-zA-Z0-9]+$", "", v) for v in re.findall(r"บ้าน(\S{2,})", norm)
    }
    return moo, villages


def _same_recurring(a: ProjectRecord, b: ProjectRecord) -> bool:
    """Same recurring project: identical work-type and an overlapping location.

    บ้าน names disambiguate best, so when both carry them they must intersect;
    only when a name lacks a บ้าน token do we fall back to the หมู่ number."""
    wa = _work_type(a.name_th)
    if wa is None or wa != _work_type(b.name_th):
        return False
    moo_a, village_a = _locations(a.name_th)
    moo_b, village_b = _locations(b.name_th)
    if village_a and village_b:
        return bool(village_a & village_b)
    return bool(moo_a & moo_b)


def _cluster_recurring(records: list[ProjectRecord]) -> list[list[ProjectRecord]]:
    """Union-find the records into recurring-project clusters (transitive)."""
    parent = list(range(len(records)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(records)):
        for j in range(i + 1, len(records)):
            if _same_recurring(records[i], records[j]):
                parent[find(i)] = find(j)

    clusters: dict[int, list[ProjectRecord]] = defaultdict(list)
    for i, record in enumerate(records):
        clusters[find(i)].append(record)
    return list(clusters.values())


def _repeat_contractor(
    cluster: list[ProjectRecord], years: list[int]
) -> tuple[str, list[int], Decimal] | None:
    """The contractor that won the recurring project in the most distinct years,
    if that is ≥2 years and ≥ the concentration ratio of the years it ran.
    Returns (contractor, won_years, cumulative_budget)."""
    won_years: dict[str, set[int]] = defaultdict(set)
    cumulative: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for record in cluster:
        if not record.winner:
            continue
        won_years[record.winner].add(record.fiscal_year)
        if record.budget is not None:
            cumulative[record.winner] += record.budget
    if not won_years:
        return None
    top = max(sorted(won_years), key=lambda name: len(won_years[name]))
    span = sorted(won_years[top])
    if len(span) >= 2 and Decimal(len(span)) / Decimal(len(years)) >= (
        CONTRACTOR_CONCENTRATION_RATIO
    ):
        return top, span, cumulative[top]
    return None


def _representative(cluster: list[ProjectRecord]) -> ProjectRecord:
    return max(cluster, key=lambda r: (r.budget or Decimal("0"), r.fiscal_year))


def yoy_ok_finding() -> dict:
    """Default 8th check for a project with no flagged recurring pattern."""
    return _finding(
        "yoy_budget_anomaly", "OK",
        "no recurring same-location project with a year-over-year budget spike",
    )


def _yoy_finding(
    cluster: list[ProjectRecord],
    years: list[int],
    budget_by_year: dict[int, Decimal | None],
    max_growth: Decimal,
    spike: tuple[int, int],
    repeat: tuple[str, list[int], Decimal] | None,
) -> dict:
    rep = _representative(cluster)
    values: dict[str, object] = {
        "recurring_scope": rep.name_th,
        "fiscal_years": years,
        "recurrence_count": len(cluster),
        "budget_by_year": {str(y): _s(budget_by_year[y]) for y in years},
        "max_yoy_growth": _s(max_growth),
        "spike_from_year": spike[0],
        "spike_to_year": spike[1],
        "severity": "MEDIUM",
    }
    detail = (
        f"recurring same-location project across fiscal years {years}; "
        f"budget grew up to {max_growth * 100:.0f}% between "
        f"{spike[0]} and {spike[1]} — requires review"
    )
    if repeat is not None:
        contractor, span, cumulative = repeat
        values["severity"] = "HIGH"
        values["repeat_contractor"] = contractor
        values["contractor_win_years"] = span
        values["contractor_win_count"] = len(span)
        values["contractor_cumulative_budget"] = _s(cumulative)
        values["justification"] = (
            f"[ระดับความเสี่ยง: สูง] โครงการเกิดซ้ำในพื้นที่เดียวกัน ปรากฏใน {len(years)} "
            f"ปีงบประมาณ ({', '.join(map(str, years))}); "
            f"งบประมาณเพิ่มขึ้นสูงสุด {max_growth * 100:.0f}% ระหว่างปี {spike[0]}–{spike[1]}; "
            f"ผู้รับจ้างรายเดียวกัน ({contractor}) เป็นผู้ชนะ {len(span)} ครั้ง "
            f"ในปี {', '.join(map(str, span))} รวมมูลค่างานสะสม {cumulative:,.2f} บาท; "
            f"ควรตรวจสอบเพิ่มเติมโดยผู้ตรวจสอบเป็นผู้วินิจฉัยขั้นสุดท้าย"
        )
    return {"name": "yoy_budget_anomaly", "status": "FLAG", "detail": detail, "values": values}


def compute_yoy_findings(
    records: list[ProjectRecord], threshold: Decimal = YOY_GROWTH_THRESHOLD
) -> dict[str, dict]:
    """project_id → yoy_budget_anomaly finding, for every project in a recurring
    cluster whose year-over-year budget spikes past `threshold`. Projects with
    no flagged pattern are absent (callers use `yoy_ok_finding`)."""
    by_sub: dict[str, list[ProjectRecord]] = defaultdict(list)
    for record in records:
        by_sub[record.sub_district_id].append(record)

    findings: dict[str, dict] = {}
    for _sub_id, sub_records in sorted(by_sub.items()):
        for cluster in _cluster_recurring(sub_records):
            years = sorted({r.fiscal_year for r in cluster})
            if len(years) < 2:
                continue
            budget_by_year: dict[int, Decimal | None] = {}
            for year in years:
                budgets = [
                    r.budget for r in cluster if r.fiscal_year == year and r.budget is not None
                ]
                budget_by_year[year] = sum(budgets, Decimal("0")) if budgets else None

            max_growth: Decimal | None = None
            spike: tuple[int, int] | None = None
            for prev, curr in zip(years, years[1:], strict=False):
                before, after = budget_by_year[prev], budget_by_year[curr]
                if before and after and before > 0:
                    growth = ((after - before) / before).quantize(Decimal("0.0001"))
                    if growth >= threshold and (max_growth is None or growth > max_growth):
                        max_growth, spike = growth, (prev, curr)
            if max_growth is None or spike is None:
                continue

            finding = _yoy_finding(
                cluster, years, budget_by_year, max_growth, spike,
                _repeat_contractor(cluster, years),
            )
            for record in cluster:
                findings[record.project_id] = finding
    return findings
