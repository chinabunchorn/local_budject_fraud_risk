"""Chat output guardrails — the live-answer half of "flag, never accuse".

Three controls on the streamed answer, all reusing the one shared lexicon
(`schemas.guardrails`) so batch and chat behave identically:

  1. Sentence-gated lexicon check — the answer is released in flush segments,
     and each segment is scanned for banned verdict terms *before* it reaches
     the client, so an accusatory word is never displayed even for an instant
     (the streaming/guardrail reconciliation chosen for Phase 4). A hit replaces
     the segment with a neutral notice and halts the stream.
  2. Citation existence — every `[C#]` marker the model emits must point at a
     passage that was actually retrieved for this query; unknown markers are the
     primary anti-hallucination control.
  3. Refuse-when-unsupported — with no retrieved context the endpoint returns a
     templated Thai refusal instead of letting the model answer from memory.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from schemas.guardrails import find_banned_terms

# Longest banned term is "corruption" (10 chars); a 12-char tail from already
# emitted text is prepended when scanning a new segment so a term split across a
# segment boundary can't slip through.
_TAIL = 12

_CITATION_RE = re.compile(r"\[C(\d+)\]")
_BOUNDARY_CHARS = "\n।.!?…"

# Shown when the lexicon check trips — the answer is withheld, not paraphrased.
BLOCKED_NOTICE_TH = (
    "\n\n[ระบบระงับการแสดงผลบางส่วน: พบถ้อยคำที่อาจสื่อไปในเชิงกล่าวหา "
    "ระบบนี้แสดงเฉพาะข้อสังเกตเชิงความเสี่ยง การวินิจฉัยขั้นสุดท้ายเป็นของผู้ตรวจสอบ]"
)

# Returned when retrieval finds nothing relevant — never answer from memory.
UNSUPPORTED_TH = (
    "ขออภัย ไม่พบข้อมูลที่เกี่ยวข้องในเอกสารโครงการหรือระเบียบที่ระบบมีอยู่ "
    "จึงไม่สามารถตอบคำถามนี้โดยอ้างอิงหลักฐานได้ "
    "กรุณาปรับคำถามหรือตรวจสอบจากเอกสารต้นทางในแดชบอร์ด"
)


@dataclass(frozen=True)
class Segment:
    """A validated slice of the answer ready to stream, or a blocking notice."""

    text: str
    blocked: bool = False


class SentenceGate:
    """Buffers streamed deltas and releases lexicon-clean flush segments.

    Segments are a pragmatic unit (sentence-ender, newline, or a length cap at a
    word boundary), not linguistically perfect Thai sentences — enough to check
    text before it is shown while keeping perceived latency low. `first_flush`
    caps the very first segment shorter so display-TTFT stays small."""

    def __init__(self, *, first_flush: int = 48, max_segment: int = 160) -> None:
        self._buf = ""
        self._tail = ""  # clean tail of already-emitted text (split-term guard)
        self._first_emitted = False
        self._first_flush = first_flush
        self._max_segment = max_segment
        self.blocked = False

    def _limit(self) -> int:
        return self._max_segment if self._first_emitted else self._first_flush

    def _next_cut(self, buf: str) -> int:
        limit = self._limit()
        for i, ch in enumerate(buf):
            if ch in _BOUNDARY_CHARS:
                return i + 1
        if len(buf) >= limit:
            window = buf[:limit]
            space = window.rfind(" ")
            return space + 1 if space > limit // 2 else limit
        return -1

    def _validate(self, segment: str) -> Segment:
        if find_banned_terms(self._tail + segment):
            self.blocked = True
            return Segment(text=BLOCKED_NOTICE_TH, blocked=True)
        self._first_emitted = True
        self._tail = (self._tail + segment)[-_TAIL:]
        return Segment(text=segment)

    def push(self, delta: str) -> list[Segment]:
        """Feed a token delta; return zero or more segments now safe to stream."""
        if self.blocked:
            return []
        self._buf += delta
        out: list[Segment] = []
        while (cut := self._next_cut(self._buf)) != -1:
            segment, self._buf = self._buf[:cut], self._buf[cut:]
            out.append(self._validate(segment))
            if self.blocked:
                self._buf = ""
                break
        return out

    def flush(self) -> list[Segment]:
        """End of stream — release whatever remains (after one final check)."""
        if self.blocked or not self._buf:
            return []
        segment, self._buf = self._buf, ""
        return [self._validate(segment)]


def cited_labels(text: str) -> set[int]:
    """The citation indices the answer actually referenced (`[C3]` → 3)."""
    return {int(m.group(1)) for m in _CITATION_RE.finditer(text)}


def verify_citations(used: set[int], available: set[int]) -> set[int]:
    """Citations that resolve to a genuinely retrieved passage. Unknown markers
    are dropped (not surfaced), so the UI only ever offers real sources."""
    return used & available
