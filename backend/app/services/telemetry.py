"""Streaming telemetry — the Phase-4 optimization measurement surface.

Captures, per chat request, the numbers the presentation is built on:

  * TTFT (raw)      — request-sent → first token; pure model + tunnel latency
  * TTFT (backend)  — request-received → first token; includes the RAG pipeline
  * TTFT (display)  — request-received → first sentence shown; includes the
                      sentence-gating guardrail buffer (honest perceived latency)
  * queue wait      — vLLM scheduler queue time, from its /metrics histogram
                      delta around this request (single-concurrency demo)
  * decode tok/s    — output tokens / generation duration
  * inter-token p50/p95, end-to-end latency, and per-stage durations

Everything here is measurement only — no LLM, no product logic. The same dict
feeds the live in-UI panel (SSE `telemetry` event), the Langfuse trace
metadata, and the offline benchmark harness (`benchmarks/stream_bench.py`).
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field


def _percentile(values: list[float], pct: float) -> float | None:
    """Nearest-rank percentile (no numpy dep). `pct` in [0, 100]."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(0, min(len(ordered) - 1, round(pct / 100 * (len(ordered) - 1))))
    return ordered[rank]


def _ms(seconds: float | None) -> float | None:
    return round(seconds * 1000, 1) if seconds is not None else None


@dataclass
class StreamTelemetry:
    """One instance per chat request. Wall-clock via `perf_counter` (monotonic,
    high-resolution); all outputs are milliseconds unless named otherwise."""

    created: float = field(default_factory=time.perf_counter)
    stages: dict[str, float] = field(default_factory=dict)  # name -> seconds
    request_sent_at: float | None = None
    first_token_at: float | None = None
    last_token_at: float | None = None
    first_display_at: float | None = None
    done_at: float | None = None
    token_times: list[float] = field(default_factory=list)
    output_tokens: int | None = None
    queue_wait_ms: float | None = None
    degraded: bool = False

    @contextmanager
    def stage(self, name: str) -> Iterator[None]:
        """Time a named RAG stage (embed / retrieve / rerank / assemble)."""
        start = time.perf_counter()
        try:
            yield
        finally:
            self.stages[name] = self.stages.get(name, 0.0) + (
                time.perf_counter() - start
            )

    def mark_request_sent(self) -> None:
        self.request_sent_at = time.perf_counter()

    def mark_token(self) -> None:
        now = time.perf_counter()
        if self.first_token_at is None:
            self.first_token_at = now
        self.last_token_at = now
        self.token_times.append(now)

    def mark_first_display(self) -> None:
        if self.first_display_at is None:
            self.first_display_at = time.perf_counter()

    def mark_done(self) -> None:
        self.done_at = time.perf_counter()

    def _decode_tokens_per_sec(self) -> float | None:
        if self.first_token_at is None or self.last_token_at is None:
            return None
        duration = self.last_token_at - self.first_token_at
        if duration <= 0:
            return None
        # Prefer the model's own output-token count (usage); fall back to the
        # number of streamed chunks when usage is unavailable.
        count = self.output_tokens if self.output_tokens else len(self.token_times)
        return round(count / duration, 1)

    def _inter_token_ms(self) -> list[float]:
        return [
            (b - a) * 1000
            for a, b in zip(self.token_times, self.token_times[1:], strict=False)
        ]

    def as_dict(self) -> dict[str, object]:
        """Presentation-ready metric bundle for the SSE event / Langfuse / bench."""
        ttft_raw = (
            self.first_token_at - self.request_sent_at
            if self.first_token_at is not None and self.request_sent_at is not None
            else None
        )
        ttft_backend = (
            self.first_token_at - self.created
            if self.first_token_at is not None
            else None
        )
        ttft_display = (
            self.first_display_at - self.created
            if self.first_display_at is not None
            else None
        )
        e2e = self.done_at - self.created if self.done_at is not None else None
        gaps = self._inter_token_ms()
        prefill = (
            _ms(ttft_raw) - self.queue_wait_ms
            if ttft_raw is not None and self.queue_wait_ms is not None
            else None
        )
        return {
            "ttft_raw_ms": _ms(ttft_raw),
            "ttft_backend_ms": _ms(ttft_backend),
            "ttft_display_ms": _ms(ttft_display),
            "queue_wait_ms": (
                round(self.queue_wait_ms, 1) if self.queue_wait_ms is not None else None
            ),
            "prefill_ms": round(prefill, 1) if prefill is not None else None,
            "decode_tokens_per_sec": self._decode_tokens_per_sec(),
            "inter_token_p50_ms": _percentile(gaps, 50),
            "inter_token_p95_ms": _percentile(gaps, 95),
            "output_tokens": self.output_tokens or len(self.token_times) or None,
            "e2e_ms": _ms(e2e),
            "stages_ms": {k: round(v * 1000, 1) for k, v in self.stages.items()},
            "degraded": self.degraded,
        }
