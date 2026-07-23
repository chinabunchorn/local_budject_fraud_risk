"""TEI rerank client — clamping + batching under the reranker's token budget.

Regression for the live 413 (Payload Too Large): the whole candidate set can't
be reranked in one request, so passages are clamped and sent in batches, with
scores scattered back to the caller's original order.
"""

from __future__ import annotations

import json

import httpx

from app.services.tei import _RERANK_BATCH, _RERANK_CLAMP, TEIClient


async def test_rerank_clamps_and_batches_preserving_order():
    seen_batches: list[int] = []
    max_len = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal max_len
        body = json.loads(request.content)
        texts = body["texts"]
        seen_batches.append(len(texts))
        max_len = max(max_len, max(len(t) for t in texts))
        # score = local index, so we can verify global alignment
        return httpx.Response(
            200, json=[{"index": i, "score": float(i)} for i in range(len(texts))]
        )

    n = _RERANK_BATCH + 3  # forces two batches
    texts = [f"passage-{i} " + "ก" * 500 for i in range(n)]
    client = TEIClient(
        "http://embed", "http://rerank", transport=httpx.MockTransport(handler)
    )
    scores = await client.rerank("คำถาม", texts)
    await client.aclose()

    assert len(scores) == n
    # two batches: full one then the remainder
    assert seen_batches == [_RERANK_BATCH, 3]
    # each passage was clamped before sending
    assert max_len <= _RERANK_CLAMP
    # score for global index i is its position within its batch
    assert scores[0] == 0.0 and scores[_RERANK_BATCH] == 0.0
    assert scores[_RERANK_BATCH - 1] == float(_RERANK_BATCH - 1)


async def test_rerank_empty_is_noop():
    client = TEIClient("http://embed", "http://rerank")
    assert await client.rerank("q", []) == []
    await client.aclose()
