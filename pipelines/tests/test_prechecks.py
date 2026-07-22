"""Deterministic pre-check logic — pure arithmetic over extracted facts."""

from decimal import Decimal

from common.prechecks import (
    BidFact,
    ProjectFacts,
    ProjectRecord,
    compute_prechecks,
    compute_yoy_findings,
    yoy_ok_finding,
)


def _by_name(facts: ProjectFacts) -> dict[str, dict]:
    return {c["name"]: c for c in compute_prechecks(facts)}


def _bid(name: str, amount: str, winner: bool = False) -> BidFact:
    return BidFact(name=name, amount=Decimal(amount), is_winner=winner)


class TestReferenceCrossCheck:
    def test_match_within_tolerance_is_ok(self):
        facts = ProjectFacts(
            reference_price=Decimal("707004.00"), form_reference_price=Decimal("707004.00")
        )
        assert _by_name(facts)["reference_price_cross_check"]["status"] == "OK"

    def test_divergence_flags(self):
        facts = ProjectFacts(
            reference_price=Decimal("707004.00"), form_reference_price=Decimal("650000.00")
        )
        assert _by_name(facts)["reference_price_cross_check"]["status"] == "FLAG"

    def test_missing_form_is_na(self):
        facts = ProjectFacts(reference_price=Decimal("707004.00"))
        assert _by_name(facts)["reference_price_cross_check"]["status"] == "NA"


class TestReferenceWithinBudget:
    def test_reference_above_budget_flags(self):
        facts = ProjectFacts(budget=Decimal("650000"), reference_price=Decimal("707004"))
        check = _by_name(facts)["reference_within_budget"]
        assert check["status"] == "FLAG"
        assert check["values"]["utilization"] == "1.0877"

    def test_within_budget_ok(self):
        facts = ProjectFacts(budget=Decimal("10000000"), reference_price=Decimal("9775000"))
        assert _by_name(facts)["reference_within_budget"]["status"] == "OK"


class TestContractWithinReference:
    def test_contract_above_reference_flags(self):
        facts = ProjectFacts(
            reference_price=Decimal("2600"), contract_price=Decimal("2660")
        )
        assert _by_name(facts)["contract_within_reference"]["status"] == "FLAG"

    def test_savings_ratio_reported(self):
        facts = ProjectFacts(
            reference_price=Decimal("707004"), contract_price=Decimal("509000")
        )
        check = _by_name(facts)["contract_within_reference"]
        assert check["status"] == "OK"
        assert check["values"]["savings_ratio"] == "0.2801"


class TestBidCompetition:
    def test_single_quote_on_competitive_route_warns(self):
        facts = ProjectFacts(
            procurement_method="E_BIDDING", bids=[_bid("บ. เดียว", "500000", winner=True)]
        )
        assert _by_name(facts)["bid_competition"]["status"] == "WARN"

    def test_winner_not_lowest_warns(self):
        facts = ProjectFacts(
            procurement_method="E_BIDDING",
            bids=[
                _bid("ผู้ชนะ", "1350000", winner=True),
                _bid("รายต่ำสุด", "1255000"),
                _bid("รายกลาง", "1394000"),
            ],
        )
        check = _by_name(facts)["bid_competition"]
        assert check["status"] == "WARN"
        assert check["values"]["winner_is_lowest"] is False
        assert check["values"]["lowest_bid"] == "1255000"

    def test_winner_is_lowest_ok(self):
        facts = ProjectFacts(
            procurement_method="E_BIDDING",
            bids=[_bid("ผู้ชนะ", "509000", winner=True), _bid("รายสูง", "589000")],
        )
        check = _by_name(facts)["bid_competition"]
        assert check["status"] == "OK"
        assert check["values"]["winner_is_lowest"] is True

    def test_single_quote_on_specific_route_is_ok(self):
        facts = ProjectFacts(
            procurement_method="SPECIFIC", bids=[_bid("อู่ช่างโต", "2660", winner=True)]
        )
        assert _by_name(facts)["bid_competition"]["status"] == "OK"


class TestProcurementThreshold:
    def test_specific_above_ceiling_flags(self):
        facts = ProjectFacts(procurement_method="SPECIFIC", reference_price=Decimal("650000"))
        assert _by_name(facts)["procurement_threshold"]["status"] == "FLAG"

    def test_specific_just_under_ceiling_warns(self):
        facts = ProjectFacts(procurement_method="SPECIFIC", reference_price=Decimal("488300"))
        assert _by_name(facts)["procurement_threshold"]["status"] == "WARN"

    def test_ebidding_above_ceiling_ok(self):
        facts = ProjectFacts(procurement_method="E_BIDDING", reference_price=Decimal("9775000"))
        assert _by_name(facts)["procurement_threshold"]["status"] == "OK"


class TestExpectedDocuments:
    def test_ebidding_missing_docs_warns(self):
        facts = ProjectFacts(
            procurement_method="E_BIDDING", present_doc_types={"contract_summary", "bk01"}
        )
        check = _by_name(facts)["expected_documents"]
        assert check["status"] == "WARN"
        assert "tor" in check["values"]["missing"]
        assert "winner_announcement" in check["values"]["missing"]

    def test_reference_form_satisfied_by_bk06(self):
        facts = ProjectFacts(
            procurement_method="SELECTION",
            present_doc_types={"contract_summary", "bk06", "tor"},
        )
        assert _by_name(facts)["expected_documents"]["status"] == "OK"

    def test_specific_only_needs_contract_summary(self):
        facts = ProjectFacts(
            procurement_method="SPECIFIC", present_doc_types={"contract_summary"}
        )
        assert _by_name(facts)["expected_documents"]["status"] == "OK"


def _rec(pid, year, name, budget, winner=None, sub="SD-HUAKHAO"):
    return ProjectRecord(
        project_id=pid,
        sub_district_id=sub,
        fiscal_year=year,
        name_th=name,
        budget=Decimal(budget) if budget is not None else None,
        winner=winner,
    )


# the real ตำบลหัวเขา หมู่ ๔ บ้านวัดไทร recurrence (2566→2568)
WATSAI = [
    _rec("p1", 2566, "ก่อสร้างโครงการก่อสร้างถนน ค.ส.ล. หมู่ ๔ บ้านวัดไทร", "1724000", "ว.วิเชียร"),
    _rec("p2", 2566, "โครงการก่อสร้างถนนคอนกรีตเสริมเหล็ก หมู่ที่ ๔ บ้านวัดไทร", "2652000", "ส.พงษ์พัฒนา"),
    _rec("p3", 2567, "โครงการก่อสร้างถนน คสล หมู่ ๔ บ้านวัดไทร", "919000", "ส.พงษ์พัฒนา"),
    _rec("p4", 2568, "ก่อสร้างถนนคอนกรีตเสริมเหล็ก หมู่ที่ ๔ บ้านวัดไทร", "7794000", "บุญเอื้อฟาร์ม"),
]


class TestYoYRedundancy:
    def test_recurring_spike_flags_every_cluster_project(self):
        findings = compute_yoy_findings(WATSAI)
        assert set(findings) == {"p1", "p2", "p3", "p4"}
        assert all(f["status"] == "FLAG" for f in findings.values())

    def test_budget_aggregated_by_year_and_growth(self):
        v = compute_yoy_findings(WATSAI)["p4"]["values"]
        assert v["budget_by_year"] == {
            "2566": "4376000",  # two 2566 projects summed
            "2567": "919000",
            "2568": "7794000",
        }
        assert v["max_yoy_growth"] == "7.4810"
        assert (v["spike_from_year"], v["spike_to_year"]) == (2567, 2568)
        assert v["recurrence_count"] == 4

    def test_contractor_concentration_escalates_to_high(self):
        v = compute_yoy_findings(WATSAI)["p1"]["values"]
        assert v["severity"] == "HIGH"
        assert v["repeat_contractor"] == "ส.พงษ์พัฒนา"
        assert v["contractor_win_years"] == [2566, 2567]
        assert v["contractor_cumulative_budget"] == "3571000"
        assert "[ระดับความเสี่ยง: สูง]" in v["justification"]

    def test_no_concentration_stays_medium(self):
        records = [
            _rec("a", 2566, "ก่อสร้างถนน คสล หมู่ ๔ บ้านวัดไทร", "1000000", "รายที่หนึ่ง"),
            _rec("b", 2567, "ก่อสร้างถนน คสล หมู่ ๔ บ้านวัดไทร", "1000000", "รายที่สอง"),
            _rec("c", 2568, "ก่อสร้างถนน คสล หมู่ ๔ บ้านวัดไทร", "3000000", "รายที่สาม"),
        ]
        v = compute_yoy_findings(records)["c"]["values"]
        assert v["severity"] == "MEDIUM"
        assert "repeat_contractor" not in v
        assert "justification" not in v

    def test_recurring_but_below_threshold_not_flagged(self):
        # +90% recurrence stays quiet — the threshold is a full doubling (100%)
        records = [
            _rec("a", 2566, "ก่อสร้างถนน คสล หมู่ ๔ บ้านวัดไทร", "1000000"),
            _rec("b", 2567, "ก่อสร้างถนน คสล หมู่ ๔ บ้านวัดไทร", "1900000"),  # +90% < 100%
        ]
        assert compute_yoy_findings(records) == {}

    def test_different_work_type_same_location_not_clustered(self):
        # ถนนคสล vs ถนนดิน at บ้านน้ำพุ are distinct works → no cross-year recurrence
        records = [
            _rec("a", 2566, "ก่อสร้างถนน คสล หมู่ ๕ บ้านน้ำพุ", "1000000"),
            _rec("b", 2567, "ก่อสร้างถนนดิน หมู่ ๕ บ้านน้ำพุ", "5000000"),
        ]
        assert compute_yoy_findings(records) == {}

    def test_different_villages_not_clustered(self):
        records = [
            _rec("a", 2566, "ซ่อมแซมถนนลูกรัง หมู่ ๑๐ บ้านหัวเขา", "1000000"),
            _rec("b", 2567, "ซ่อมแซมถนนลูกรัง หมู่ ๑ บ้านเขาคีรี", "5000000"),
        ]
        assert compute_yoy_findings(records) == {}

    def test_ok_finding_shape(self):
        f = yoy_ok_finding()
        assert f["name"] == "yoy_budget_anomaly"
        assert f["status"] == "OK"

    def test_deterministic_repeatable(self):
        assert compute_yoy_findings(WATSAI) == compute_yoy_findings(WATSAI)


class TestDeterminism:
    def test_stable_order_and_repeatable(self):
        facts = ProjectFacts(procurement_method="E_BIDDING", budget=Decimal("10000000"))
        first = compute_prechecks(facts)
        assert [c["name"] for c in first] == [
            "reference_price_cross_check",
            "boq_vs_bk01_total",
            "reference_within_budget",
            "contract_within_reference",
            "bid_competition",
            "procurement_threshold",
            "expected_documents",
        ]
        assert compute_prechecks(facts) == first
