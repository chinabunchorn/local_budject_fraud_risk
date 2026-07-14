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

from dataclasses import dataclass, field
from decimal import Decimal

# เฉพาะเจาะจง is permitted up to this ราคากลาง; above it the e-bidding route
# applies (ระเบียบกระทรวงการคลัง ข้อ ๒๐ — the threshold-splitting citation).
SPECIFIC_METHOD_CEILING = Decimal("500000")
# how close to the ceiling still counts as "just under" and worth a look
THRESHOLD_PROXIMITY = Decimal("0.05")
# rounding slack when comparing two independently-stated ราคากลาง figures
CROSS_CHECK_TOLERANCE = Decimal("0.01")


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
    """Run every check; order is stable so re-runs produce identical JSONB."""
    return [
        _cross_check_reference_price(facts),
        _boq_vs_form(facts),
        _reference_within_budget(facts),
        _contract_within_reference(facts),
        _bid_competition(facts),
        _procurement_threshold(facts),
        _expected_documents(facts),
    ]
