"""Async Text-Embeddings-Inference client — BGE-M3 embed + BGE-reranker-v2-m3.

Both run in TEI on the app VM (CPU is enough at prototype scale), so retrieval
for the live chatbot never depends on LANTA being up — only the final
generation call goes through the tunnel. Mirrors the sync pipeline client
(`pipelines/common/tei.py`) but async, for the SSE request path.
"""

from __future__ import annotations

import httpx
from schemas import EMBEDDING_DIM


class TEIError(RuntimeError):
    """TEI (embed or rerank) is unreachable or returned an unexpected shape.

    Unlike the tunnel, TEI lives beside the API and is expected up — a failure
    here is a real 500, not the graceful "outside demonstration window" state."""


# The reranker runs with a small --max-batch-tokens budget (1024 on the dev-Mac
# CPU image — memory `dev-machine-docker`), so the whole candidate set can't be
# scored in one request. Clamp each passage to its relevance-bearing head and
# send in small batches that fit the budget; scores are per (query, passage) so
# batching is exact.
_RERANK_CLAMP = 220
_RERANK_BATCH = 12


class TEIClient:
    def __init__(
        self,
        embed_url: str,
        rerank_url: str,
        *,
        timeout: float = 120.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._embed = httpx.AsyncClient(
            base_url=embed_url, timeout=timeout, transport=transport
        )
        self._rerank = httpx.AsyncClient(
            base_url=rerank_url, timeout=timeout, transport=transport
        )

    async def embed(self, text: str) -> list[float]:
        """Embed a single query. `truncate=True` mirrors the server's
        --auto-truncate; a long question still carries its retrieval signal."""
        try:
            resp = await self._embed.post(
                "/embed", json={"inputs": text, "truncate": True}
            )
            resp.raise_for_status()
            (vector,) = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise TEIError(f"embed failed: {exc}") from exc
        if len(vector) != EMBEDDING_DIM:
            raise TEIError(
                f"TEI returned {len(vector)}-dim vector, expected {EMBEDDING_DIM}"
            )
        return vector

    async def rerank(self, query: str, texts: list[str]) -> list[float]:
        """Return a relevance score per passage, aligned to `texts` order.

        TEI's /rerank returns `[{index, score}, ...]` sorted by score; we
        scatter the scores back into the caller's original order so the caller
        can pair each score with its retrieved chunk."""
        if not texts:
            return []
        clamped = [t[:_RERANK_CLAMP] for t in texts]
        scores = [0.0] * len(texts)
        try:
            for start in range(0, len(clamped), _RERANK_BATCH):
                batch = clamped[start : start + _RERANK_BATCH]
                resp = await self._rerank.post(
                    "/rerank", json={"query": query, "texts": batch, "truncate": True}
                )
                resp.raise_for_status()
                for item in resp.json():
                    scores[start + item["index"]] = float(item["score"])
        except (httpx.HTTPError, ValueError) as exc:
            raise TEIError(f"rerank failed: {exc}") from exc
        return scores

    async def aclose(self) -> None:
        await self._embed.aclose()
        await self._rerank.aclose()
