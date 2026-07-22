"""Prompt bundle tests — completeness, assembly, and the lexicon self-check."""

import re

import pytest
from schemas import BANNED_TERMS, RiskFactorType

from common.prompts import PROMPTS_DIR, build_messages, load_risk_scoring


@pytest.fixture(scope="module")
def bundle():
    return load_risk_scoring("v1")


class TestLoad:
    def test_version_string_matches_prompt_version_convention(self, bundle):
        assert bundle.version == "risk_scoring/v1"

    def test_all_five_factors_present(self, bundle):
        assert set(bundle.factors) == set(RiskFactorType)
        for factor_type, block in bundle.factors.items():
            assert factor_type.value in block  # each block names its factor

    def test_system_prompt_states_the_ground_rules(self, bundle):
        assert "ผู้ตรวจสอบ" in bundle.system  # human decides
        assert "EVIDENCE" in bundle.system and "INTERPRETATION" in bundle.system
        assert "REQUIRES_INVESTIGATION" in bundle.system

    def test_unknown_version_rejected(self):
        with pytest.raises(FileNotFoundError):
            load_risk_scoring("v999")


class TestBuildMessages:
    def test_assembly_fills_every_placeholder(self, bundle):
        messages = build_messages(
            bundle,
            sub_district="เทศบาลตำบลท่าช้าง",
            project_name="โครงการปรับปรุงถนน",
            fiscal_year=2567,
            budget_total="1,500,000.00",
            budget_lines="1. งานผิวทาง 998,000 บาท — หจก.ทดสอบ",
            document_excerpts="[chunk 123] ข้อความจากสัญญา...",
            regulation_context="[fiscal-discipline-act-2561/s.37] มาตรา ๓๗ ...",
        )
        assert [m["role"] for m in messages] == ["system", "user"]
        user = messages[1]["content"]
        assert "เทศบาลตำบลท่าช้าง" in user
        assert "THRESHOLD_SPLITTING" in user  # factor blocks inlined
        assert not re.search(r"\{\w+\}", user)  # no unfilled placeholders

    def test_threshold_splitting_cites_the_direct_regulation(self, bundle):
        assert "mof-procurement-regulation-2560/k.20" in bundle.factors[
            RiskFactorType.THRESHOLD_SPLITTING
        ]


class TestLexiconSelfCheck:
    def test_no_template_contains_banned_terms(self):
        """Our own prompts must obey flag-never-accuse: instructions are
        phrased positively, without ever writing the banned words."""
        for path in (PROMPTS_DIR / "risk_scoring").rglob("*.md"):
            content = path.read_text(encoding="utf-8").lower()
            for term in BANNED_TERMS:
                assert term not in content, f"{term!r} found in {path}"
