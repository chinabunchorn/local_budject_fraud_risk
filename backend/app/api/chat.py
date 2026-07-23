"""Live RAG chat — the ONLY endpoint allowed to call live inference (CLAUDE.md).

Pipeline 3 (ARCHITECTURE): embed → pgvector top-k over documents + regulations →
BGE-rerank → cited prompt → streamed generation through the SSH tunnel → output
guardrails → SSE. Two constraints shape the stream loop:

  * "flag, never accuse" while streaming — answer text is released in
    lexicon-checked flush segments (`SentenceGate`); a banned verdict term is
    never shown. Citations are revealed only after an end-of-stream
    citation-existence check against the actually-retrieved passages.
  * offline-first — if the tunnel is down the model call raises `TunnelDown` and
    we emit a `degraded` event ("outside demonstration window"), never a 500.

Per-request streaming telemetry (TTFT raw/display, queue wait, tokens/sec, e2e,
stage breakdown) rides along as a final `telemetry` SSE event and into Langfuse
— the measurement surface the optimization story is built on.

The DB session for retrieval is opened *inside* the stream (not the request-
scoped dependency), because a request-scoped session is finalized around the
StreamingResponse lifecycle; retrieval captures all provenance up front, so the
session closes before the long generation.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.api.schemas import ChatRequest
from app.core.dependencies import CurrentUser, SettingsDep
from app.db.session import get_session_factory
from app.guardrails.chat_guards import (
    UNSUPPORTED_TH,
    SentenceGate,
    cited_labels,
    verify_citations,
)
from app.rag.graph import ChatDeps, run_retrieval
from app.rag.prompt import CHAT_PROMPT_VERSION
from app.rag.retrieval import RetrievedContext
from app.services.observability import trace_chat
from app.services.tei import TEIClient, TEIError
from app.services.telemetry import StreamTelemetry
from app.services.vllm import TunnelDown, VLLMChatClient, VLLMError

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])

DISCLAIMER_TH = (
    "ผู้ช่วยนี้แจ้งจุดที่ควรตรวจสอบจากเอกสารเท่านั้น ไม่ใช่ข้อสรุป "
    "การวินิจฉัยขั้นสุดท้ายเป็นของผู้ตรวจสอบ"
)
DEGRADED_TH = (
    "ผู้ช่วยสนทนาสดไม่พร้อมใช้งานในขณะนี้ (อยู่นอกช่วงเวลาสาธิต) "
    "ข้อมูลความเสี่ยงและหลักฐานทั้งหมดยังดูได้จากแดชบอร์ดตามปกติ"
)


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _citation_payload(context: list[RetrievedContext], valid: set[int]) -> list[dict]:
    """Serialize the citations the answer actually used AND that resolve to a
    retrieved passage — provenance for the one-click source viewer."""
    out = []
    for c in context:
        if c.label not in valid:
            continue
        out.append(
            {
                "label": c.label,
                "kind": c.kind,
                "source_label_th": c.source_label_th,
                "quote_th": c.text[:400],
                "document_id": str(c.document_id) if c.document_id else None,
                "page": c.page,
                "regulation_code": c.regulation_code,
            }
        )
    return out


@router.post("/chat")
async def chat(
    payload: ChatRequest, user: CurrentUser, settings: SettingsDep
) -> StreamingResponse:
    telemetry = StreamTelemetry()
    tei = TEIClient(settings.tei_embed_url, settings.tei_rerank_url)
    # Per-request overrides (benchmark A/B) fall back to settings defaults.
    rerank_top_n = payload.rerank_top_n or settings.chat_rerank_top_n
    max_tokens = payload.max_tokens or settings.chat_max_tokens
    vllm = VLLMChatClient(
        settings.vllm_base_url,
        settings.vllm_served_model,
        settings.vllm_metrics_url,
        max_tokens=max_tokens,
    )
    # Keep only the most recent turns for context (stateless backend).
    history = [m.model_dump() for m in payload.history][
        -(settings.chat_history_turns * 2) :
    ]

    async def event_stream() -> AsyncIterator[str]:
        try:
            # --- retrieval (own session, closed before generation) ---
            async with get_session_factory()() as session:
                deps = ChatDeps(
                    session=session,
                    tei=tei,
                    telemetry=telemetry,
                    top_k=settings.chat_retrieval_top_k,
                    rerank_top_n=rerank_top_n,
                )
                try:
                    state = await run_retrieval(deps, payload.question, history)
                except TEIError as exc:
                    logger.warning("retrieval failed (TEI): %s", exc)
                    yield _sse("error", {"message": "ระบบค้นหาเอกสารขัดข้องชั่วคราว"})
                    return

            context: list[RetrievedContext] = state.get("context", [])
            messages = state["messages"]

            # --- refuse-when-unsupported ---
            if not context:
                telemetry.mark_first_display()
                yield _sse("token", {"text": UNSUPPORTED_TH})
                telemetry.mark_done()
                yield _sse("telemetry", telemetry.as_dict())
                yield _sse("done", {"disclaimer_th": DISCLAIMER_TH})
                return

            # --- streamed generation through the tunnel ---
            queue_before = await vllm.queue_time_totals()
            gate = SentenceGate()
            answer_parts: list[str] = []
            try:
                async for delta in vllm.stream(messages, telemetry):
                    for seg in gate.push(delta):
                        telemetry.mark_first_display()
                        yield _sse("token", {"text": seg.text, "blocked": seg.blocked})
                        if not seg.blocked:
                            answer_parts.append(seg.text)
                    if gate.blocked:
                        break
                for seg in gate.flush():
                    telemetry.mark_first_display()
                    yield _sse("token", {"text": seg.text, "blocked": seg.blocked})
                    if not seg.blocked:
                        answer_parts.append(seg.text)
            except TunnelDown as exc:
                logger.info("chat degraded — tunnel down: %s", exc)
                telemetry.degraded = True
                telemetry.mark_done()
                yield _sse("degraded", {"message": DEGRADED_TH})
                yield _sse("telemetry", telemetry.as_dict())
                yield _sse("done", {"disclaimer_th": DISCLAIMER_TH})
                return
            except VLLMError as exc:
                logger.error("vLLM error: %s", exc)
                yield _sse("error", {"message": "ระบบประมวลผลคำตอบขัดข้อง"})
                return

            # --- queue wait (metrics delta around this single request) ---
            queue_after = await vllm.queue_time_totals()
            if queue_before and queue_after and queue_after[1] > queue_before[1]:
                telemetry.queue_wait_ms = (
                    (queue_after[0] - queue_before[0])
                    / (queue_after[1] - queue_before[1])
                    * 1000
                )

            # --- citation existence + reveal ---
            answer = "".join(answer_parts)
            valid = verify_citations(cited_labels(answer), {c.label for c in context})
            citations = _citation_payload(context, valid)
            yield _sse("citations", {"citations": citations})

            telemetry.mark_done()
            metrics = telemetry.as_dict()
            yield _sse("telemetry", metrics)
            yield _sse("done", {"disclaimer_th": DISCLAIMER_TH})

            trace_chat(
                model=settings.vllm_model_id,
                messages=messages,
                answer=answer,
                metadata={
                    "prompt_version": f"chat/{CHAT_PROMPT_VERSION}",
                    "user": user.username,
                    "retrieval": [
                        {"label": c.label, "kind": c.kind, "source": c.source_label_th}
                        for c in context
                    ],
                    "cited_labels": sorted(valid),
                    "telemetry": metrics,
                    "guardrail_blocked": gate.blocked,
                },
                usage=(
                    {"output": telemetry.output_tokens}
                    if telemetry.output_tokens
                    else None
                ),
            )
        finally:
            await tei.aclose()
            await vllm.aclose()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
