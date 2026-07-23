"""Langfuse tracing seam for the live chat path.

CLAUDE.md requires EVERY LLM call to be traced to Langfuse — and the exit gate
wants the retrieval set captured alongside the generation so citation failures
are debuggable. This records the assembled prompt, the final answer, the
retrieved context labels, and the streaming telemetry as one generation.

Best-effort and lazy: a missing SDK or an unreachable Langfuse must never break
a chat response (offline-first). When creds are unset it no-ops.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def _config() -> dict[str, str] | None:
    public_key = os.environ.get("LANGFUSE_PUBLIC_KEY")
    secret_key = os.environ.get("LANGFUSE_SECRET_KEY")
    if not (public_key and secret_key):
        return None
    host = os.environ.get("LANGFUSE_HOST")
    if not host:
        host = os.environ.get("LANGFUSE_URL", "http://localhost:3000").replace(
            "langfuse-web", "localhost"
        )
    return {"public_key": public_key, "secret_key": secret_key, "host": host}


def trace_chat(
    *,
    model: str,
    messages: list[dict[str, str]],
    answer: str,
    metadata: dict[str, Any],
    usage: dict[str, Any] | None = None,
) -> None:
    """Record one chat generation. Never raises."""
    config = _config()
    if config is None:
        return
    try:
        from langfuse import Langfuse

        client = Langfuse(**config)
        span = client.start_observation(
            name="chat_rag",
            as_type="generation",
            model=model,
            input=messages,
            output=answer,
            metadata=metadata,
            usage_details=usage or None,
        )
        span.end()
        client.flush()
    except Exception as exc:  # tracing is best-effort — never fail a response
        logger.warning("langfuse chat trace failed: %s", exc)
