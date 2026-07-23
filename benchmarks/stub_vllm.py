"""Stub vLLM server — an offline stand-in for the LANTA tunnel endpoint.

Implements just enough of the OpenAI-compatible surface the backend chat path
uses — `POST /v1/chat/completions` (streaming SSE + trailing usage chunk),
`GET /v1/models`, and a Prometheus `GET /metrics` with a growing
`vllm:request_queue_time_seconds` histogram — so the whole Phase-4 path
(retrieval → guardrails → telemetry → SSE) and the benchmark harness run with
LANTA down. Latency knobs let it emit believable TTFT / queue-wait / tokens-sec
numbers for development; the REAL optimization figures come from the attended
LANTA window (this is a dev/CI stand-in, and the runbook says so).

Run:  uv run --project ../backend python stub_vllm.py   # serves :8000
Knobs (env): STUB_TTFT_MS, STUB_TOKEN_MS, STUB_QUEUE_MS, STUB_PORT.
"""

from __future__ import annotations

import asyncio
import json
import os

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

app = FastAPI()

_TTFT_MS = float(os.environ.get("STUB_TTFT_MS", "180"))
_TOKEN_MS = float(os.environ.get("STUB_TOKEN_MS", "18"))
_QUEUE_MS = float(os.environ.get("STUB_QUEUE_MS", "40"))

# A canned, non-accusatory Thai answer that cites [C1] — exercises the citation
# and lexicon guards without any real model.
_ANSWER = (
    "จากเอกสารที่ค้นได้ พบว่าราคาต่อหน่วยเพิ่มขึ้นจากปีก่อน [C1] "
    "ซึ่งเป็นจุดที่ควรตรวจสอบเพิ่มเติมถึงเหตุผลของการเปลี่ยนแปลงราคา "
    "ทั้งนี้เป็นเพียงข้อสังเกตเบื้องต้น การวินิจฉัยขั้นสุดท้ายเป็นดุลยพินิจของผู้ตรวจสอบ"
)

_state = {"queue_sum": 0.0, "queue_count": 0}


@app.get("/v1/models")
async def models() -> dict:
    return {"object": "list", "data": [{"id": "typhoon-chat", "object": "model"}]}


@app.get("/metrics")
async def metrics() -> StreamingResponse:
    body = (
        "# TYPE vllm:request_queue_time_seconds histogram\n"
        f'vllm:request_queue_time_seconds_sum{{model_name="typhoon-chat"}} '
        f'{_state["queue_sum"]}\n'
        f'vllm:request_queue_time_seconds_count{{model_name="typhoon-chat"}} '
        f'{_state["queue_count"]}\n'
    )
    return StreamingResponse(iter([body]), media_type="text/plain")


def _chunk(content: str | None = None, usage: dict | None = None) -> str:
    choices = [] if content is None else [{"index": 0, "delta": {"content": content}}]
    payload: dict = {"object": "chat.completion.chunk", "choices": choices}
    if usage is not None:
        payload["usage"] = usage
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@app.post("/v1/chat/completions")
async def completions(request: Request) -> StreamingResponse:
    body = await request.json()
    max_tokens = int(body.get("max_tokens") or 768)
    # Simulate scheduler queue wait (recorded into the histogram) + prefill.
    _state["queue_sum"] += _QUEUE_MS / 1000
    _state["queue_count"] += 1

    async def gen():
        await asyncio.sleep(_TTFT_MS / 1000)
        tokens = _ANSWER.split(" ")
        emitted = 0
        for i, tok in enumerate(tokens):
            if emitted >= max_tokens:
                break
            piece = tok if i == 0 else " " + tok
            yield _chunk(piece)
            emitted += 1
            await asyncio.sleep(_TOKEN_MS / 1000)
        yield _chunk(usage={"completion_tokens": emitted, "prompt_tokens": 512})
        yield "data: [DONE]\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("STUB_PORT", "8000")))
