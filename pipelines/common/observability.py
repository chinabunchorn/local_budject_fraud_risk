"""Langfuse tracing seam for pipeline LLM calls.

CLAUDE.md requires EVERY LLM call to be traced to Langfuse. The vLLM client
takes an optional `Tracer` (a `Callable[[Generation], None]`) and hands it one
`Generation` per call; `langfuse_tracer()` builds the real callable from env
creds, or returns None when Langfuse is not configured (tests / offline) so
tracing degrades to a no-op instead of breaking scoring.

Only the structured output and the raw reasoning trace are recorded here — the
reasoning goes to Langfuse for debug/audit ONLY and is never user-facing (the
displayed chain is the validated `reasoning_steps`, per CLAUDE.md).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field

from common.settings import langfuse_config

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Generation:
    name: str
    model: str
    input: object
    output: str
    reasoning: str | None = None
    usage: dict | None = None
    metadata: dict = field(default_factory=dict)


Tracer = Callable[[Generation], None]


def langfuse_tracer() -> Tracer | None:
    """A tracer that logs generations to Langfuse, or None when unconfigured.

    Import and client construction are lazy and defensive: a missing SDK or an
    unreachable Langfuse must never break a batch scoring run."""
    config = langfuse_config()
    if config is None:
        return None
    try:
        from langfuse import Langfuse
    except ImportError:
        logger.warning("langfuse not installed — LLM calls will not be traced")
        return None

    client = Langfuse(
        public_key=config["public_key"],
        secret_key=config["secret_key"],
        host=config["host"],
    )

    def trace(generation: Generation) -> None:
        try:
            span = client.start_observation(
                name=generation.name,
                as_type="generation",
                model=generation.model,
                input=generation.input,
                output=generation.output,
                metadata={**generation.metadata, "reasoning": generation.reasoning},
                usage_details=generation.usage or None,
            )
            span.end()
            client.flush()  # batch runs are short-lived — push the trace now
        except Exception as exc:  # tracing is best-effort — never fail the run
            logger.warning("langfuse trace failed: %s", exc)

    return trace
