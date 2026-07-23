"""Streaming vLLM client + the /api/chat SSE endpoint, fully offline.

The tunnel and TEI are simulated (httpx.MockTransport / monkeypatch), so these
run with LANTA and the DB down — they verify SSE parsing, usage accounting,
graceful tunnel-down degradation, citation existence, and the telemetry event.
"""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from app.services.telemetry import StreamTelemetry
from app.services.vllm import TunnelDown, VLLMChatClient

_SSE = (
    'data: {"choices":[{"delta":{"role":"assistant"}}]}\n\n'
    'data: {"choices":[{"delta":{"content":"ตามเอกสาร "}}]}\n\n'
    'data: {"choices":[{"delta":{"content":"[C1] ราคาสูงขึ้น"}}]}\n\n'
    'data: {"choices":[],"usage":{"completion_tokens":7}}\n\n'
    "data: [DONE]\n\n"
)


async def test_stream_parses_sse_and_records_usage():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=_SSE)

    client = VLLMChatClient(
        "http://tunnel/v1", "typhoon-chat", "http://tunnel/metrics",
        transport=httpx.MockTransport(handler),
    )
    tel = StreamTelemetry()
    parts = [c async for c in client.stream([{"role": "user", "content": "hi"}], tel)]
    await client.aclose()

    assert "".join(parts) == "ตามเอกสาร [C1] ราคาสูงขึ้น"
    assert tel.output_tokens == 7
    assert tel.first_token_at is not None


async def test_stream_raises_tunneldown_when_connection_refused():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    client = VLLMChatClient(
        "http://tunnel/v1", "typhoon-chat", "http://tunnel/metrics",
        transport=httpx.MockTransport(handler),
    )
    tel = StreamTelemetry()
    with pytest.raises(TunnelDown):
        async for _ in client.stream([{"role": "user", "content": "hi"}], tel):
            pass
    await client.aclose()


# ---- endpoint-level (monkeypatched retrieval + tunnel) ------------------------


def _auth_app(monkeypatch, *, context, deltas=None, tunnel_down=False):
    """Build a TestClient with auth + retrieval + tunnel all stubbed."""
    from types import SimpleNamespace

    from app import main
    from app.api import chat as chat_mod
    from app.core.dependencies import get_current_user

    async def fake_run_retrieval(deps, question, history):
        return {"context": context, "messages": [{"role": "user", "content": question}]}

    class FakeTEI:
        def __init__(self, *a, **k): ...
        async def aclose(self): ...

    class FakeVLLM:
        def __init__(self, *a, **k):
            self.calls = 0

        async def queue_time_totals(self):
            # before -> (1.0, 1); after -> (1.4, 2)  => delta 0.4s/1 = 400ms
            self.calls += 1
            return (1.0, 1) if self.calls == 1 else (1.4, 2)

        async def stream(self, messages, telemetry):
            if tunnel_down:
                raise TunnelDown("no tunnel")
            for d in deltas or []:
                telemetry.mark_token()
                yield d

        async def aclose(self): ...

    monkeypatch.setattr(chat_mod, "run_retrieval", fake_run_retrieval)
    monkeypatch.setattr(chat_mod, "TEIClient", FakeTEI)
    monkeypatch.setattr(chat_mod, "VLLMChatClient", FakeVLLM)
    main.app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        username="tester"
    )
    client = TestClient(main.app)
    return client, main.app


def _ctx():
    from app.rag.retrieval import RetrievedContext

    return [
        RetrievedContext(
            kind="document", text="ราคากลาง 34,000 บาท", score=0.9, label=1,
            filename="contract_summary.pdf", page=3,
        )
    ]


def test_endpoint_streams_answer_citations_and_telemetry(monkeypatch):
    client, app = _auth_app(
        monkeypatch, context=_ctx(),
        deltas=["ตามเอกสาร ", "[C1] ราคาสูงขึ้น.\n"],
    )
    try:
        r = client.post("/api/chat", json={"question": "ราคาถังน้ำเท่าไร"})
        assert r.status_code == 200
        body = r.text
        assert "event: token" in body
        assert "event: citations" in body
        assert '"label": 1' in body
        assert "event: telemetry" in body
        assert '"queue_wait_ms": 400.0' in body
        assert "event: done" in body
    finally:
        app.dependency_overrides.clear()


def test_endpoint_degrades_when_tunnel_down(monkeypatch):
    client, app = _auth_app(monkeypatch, context=_ctx(), tunnel_down=True)
    try:
        r = client.post("/api/chat", json={"question": "x"})
        assert r.status_code == 200
        assert "event: degraded" in r.text
        assert "นอกช่วงเวลาสาธิต" in r.text
        assert "event: token" not in r.text
    finally:
        app.dependency_overrides.clear()


def test_endpoint_refuses_when_no_context(monkeypatch):
    client, app = _auth_app(monkeypatch, context=[], deltas=["ignored"])
    try:
        r = client.post("/api/chat", json={"question": "x"})
        assert r.status_code == 200
        assert "ไม่พบข้อมูลที่เกี่ยวข้อง" in r.text
        assert "event: citations" not in r.text
    finally:
        app.dependency_overrides.clear()
