"""Chat guardrails — lexicon sentence-gating, citation existence, refusal."""

from __future__ import annotations

from app.guardrails.chat_guards import (
    BLOCKED_NOTICE_TH,
    SentenceGate,
    cited_labels,
    verify_citations,
)


def _drain(gate: SentenceGate, deltas: list[str]) -> tuple[str, bool]:
    """Feed deltas, then flush; return (emitted_text, blocked)."""
    emitted = []
    for d in deltas:
        for seg in gate.push(d):
            emitted.append(seg.text)
            if seg.blocked:
                return "".join(emitted), True
    for seg in gate.flush():
        emitted.append(seg.text)
    return "".join(emitted), gate.blocked


def test_clean_answer_streams_through_in_segments():
    text = "ตามเอกสาร [C1] พบว่าราคาสูงขึ้น.\nควรตรวจสอบเพิ่มเติม [C2].\n"
    emitted, blocked = _drain(SentenceGate(), list(text))
    assert not blocked
    assert emitted == text  # nothing dropped, order preserved


def test_banned_term_blocks_and_replaces_segment():
    # "ทุจริต" used as a verdict must never be shown.
    text = "โครงการนี้มีการทุจริตอย่างชัดเจน"
    emitted, blocked = _drain(SentenceGate(), list(text))
    assert blocked
    assert BLOCKED_NOTICE_TH in emitted
    assert "ทุจริต" not in emitted


def test_banned_term_split_across_segment_boundary_is_caught():
    # The term is split so no single flush segment contains it whole; the tail
    # overlap guard must still catch it.
    gate = SentenceGate(first_flush=4, max_segment=4)
    emitted, blocked = _drain(gate, ["ทุจ", "ริต", " เพิ่ม"])
    assert blocked
    assert "ทุจริต" not in emitted


def test_english_banned_term_case_insensitive():
    emitted, blocked = _drain(SentenceGate(), list("This shows FRAUD clearly"))
    assert blocked
    assert "FRAUD" not in emitted


def test_cited_labels_extracts_used_markers():
    assert cited_labels("ก [C1] ข [C3] ค [C1]") == {1, 3}


def test_verify_citations_drops_hallucinated_markers():
    # model cited C1, C2, C9 but only C1, C2 were retrieved
    assert verify_citations({1, 2, 9}, {1, 2, 3}) == {1, 2}
