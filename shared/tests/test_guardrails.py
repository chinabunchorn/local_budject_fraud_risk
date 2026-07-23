"""Lexicon guardrail tests — the free-text half of "flag, never accuse"."""

import pytest
from test_risk import make_assessment, make_factor, make_step

from schemas import RiskAssessment, find_banned_terms, lexicon_violations

PROCUREMENT_CH2_TITLE = "การมีส่วนร่วมของภาคประชาชนและผู้ประกอบการในการป้องกันการทุจริต"


class TestFindBannedTerms:
    @pytest.mark.parametrize("term", ["ทุจริต", "โกง", "ฉ้อโกง", "คอร์รัปชัน"])
    def test_thai_terms_found_as_substrings(self, term):
        assert term in find_banned_terms(f"พบพฤติกรรมที่เข้าข่าย{term}ในโครงการนี้")

    @pytest.mark.parametrize("word", ["Fraud", "CORRUPTION", "fraudulent"])
    def test_english_terms_case_insensitive(self, word):
        assert find_banned_terms(f"this indicates {word} activity")

    def test_clean_neutral_text_passes(self):
        assert (
            find_banned_terms("พบความผิดปกติที่ควรตรวจสอบเพิ่มเติมโดยผู้ตรวจสอบ") == []
        )

    def test_quoted_regulation_title_exempted(self):
        text = f"อ้างอิงหมวด ๒ {PROCUREMENT_CH2_TITLE} แห่งพระราชบัญญัติ"
        assert find_banned_terms(text, allowed_phrases=(PROCUREMENT_CH2_TITLE,)) == []

    def test_banned_term_outside_allowed_phrase_still_caught(self):
        text = f"{PROCUREMENT_CH2_TITLE} และพบว่ามีการโกงเกิดขึ้น"
        assert find_banned_terms(text, allowed_phrases=(PROCUREMENT_CH2_TITLE,)) == ["โกง"]


class TestLexiconViolations:
    def test_clean_assessment_has_no_violations(self):
        assessment = RiskAssessment.model_validate(make_assessment())
        assert lexicon_violations(assessment) == []

    def test_violation_located_in_reasoning_step(self):
        factor = make_factor(
            reasoning_steps=[
                make_step(step_type="INTERPRETATION", text_th="รูปแบบนี้อาจเป็นการโกง")
            ]
        )
        assessment = RiskAssessment.model_validate(make_assessment(factors=[factor]))
        violations = lexicon_violations(assessment)
        assert len(violations) == 1
        assert violations[0].location == "factors[0].reasoning_steps[0].text_th"
        assert violations[0].term == "โกง"

    def test_violation_in_summary_located(self):
        assessment = RiskAssessment.model_validate(
            make_assessment(summary_th="โครงการนี้มีการทุจริตอย่างชัดเจน")
        )
        assert [v.location for v in lexicon_violations(assessment)] == ["summary_th"]
