"""Text-Embeddings-Inference client (BGE-M3 on the app VM).

Requests are sent one text at a time: the dev-machine TEI runs with
`--max-batch-tokens 1024`, and a long regulation section can approach that on
its own. `truncate=True` mirrors the server's --auto-truncate; at prototype
scale the head of a section carries its retrieval signal.
"""

from __future__ import annotations

import httpx
from schemas import EMBEDDING_DIM


class TEIEmbedClient:
    def __init__(self, base_url: str, timeout: float = 120.0) -> None:
        self._client = httpx.Client(base_url=base_url, timeout=timeout)

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            resp = self._client.post("/embed", json={"inputs": text, "truncate": True})
            resp.raise_for_status()
            (vector,) = resp.json()
            if len(vector) != EMBEDDING_DIM:
                raise ValueError(
                    f"TEI returned {len(vector)}-dim vector, expected {EMBEDDING_DIM}"
                )
            vectors.append(vector)
        return vectors

    def close(self) -> None:
        self._client.close()
