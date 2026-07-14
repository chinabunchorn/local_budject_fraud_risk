"""Deterministic pre-check logic — pure arithmetic over extracted facts."""

from decimal import Decimal

from common.prechecks import BidFact, ProjectFacts, compute_prechecks


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
