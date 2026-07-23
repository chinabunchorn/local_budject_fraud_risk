"""Async streaming vLLM client — the tunnel-facing chat generation path.

THE single live-inference seam for the backend (CLAUDE.md: every LLM call goes
through the vLLM client service). OpenAI-compatible `/chat/completions` with
`stream=true`, reached through the SSH tunnel's local port. Two designed
behaviors baked in:

  * Graceful degradation — when the tunnel/job is down the connection refuses
    *before the first token*; that raises `TunnelDown`, which the chat endpoint
    turns into the "outside demonstration window" state, never a 500. A drop
    *mid-stream* (the plain `ssh -N` tunnel buckles under load — see
    LANTA_CONFIG_NOTES) ends the stream cleanly with the partial answer.
  * Whitespace-loop mitigation — this served vLLM (0.9.2) loops on indentation
    under pure greedy decoding, so we run temperature 0.5 + repetition_penalty
    1.1, exactly as the batch scoring path settled on.

The keep-alive client reuses one pooled connection across requests (saving the
per-request TCP setup through the tunnel is a measured TTFT lever).
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator

import httpx

from app.services.telemetry import StreamTelemetry

logger = logging.getLogger(__name__)

QUEUE_METRIC = "vllm:request_queue_time_seconds"


class TunnelDown(RuntimeError):
    """The inference tunnel is unreachable — degrade to the demonstration-window
    state. Distinct from a real server error so the endpoint can tell them apart."""


class VLLMError(RuntimeError):
    """vLLM answered with a 4xx/5xx (e.g. wrong served-model alias) — a genuine
    request/server fault, surfaced rather than masked as degradation."""


def parse_histogram_totals(metrics_text: str, metric: str) -> tuple[float, int] | None:
    """Pull (`_sum`, `_count`) for a Prometheus histogram family, summed across
    label sets. Returns None if the family is absent (queue wait then reports as
    unknown — honest, not zero)."""
    total_sum = 0.0
    total_count = 0
    seen = False
    for line in metrics_text.splitlines():
        if line.startswith("#") or not line.strip():
            continue
        name = line.split("{", 1)[0].split(" ", 1)[0]
        try:
            value = float(line.rsplit(" ", 1)[1])
        except (IndexError, ValueError):
            continue
        if name == f"{metric}_sum":
            total_sum += value
            seen = True
        elif name == f"{metric}_count":
            total_count += int(value)
            seen = True
    return (total_sum, total_count) if seen else None


class VLLMChatClient:
    def __init__(
        self,
        base_url: str,
        model: str,
        metrics_url: str,
        *,
        timeout: float = 120.0,
        max_tokens: int = 768,
        temperature: float = 0.5,
        repetition_penalty: float = 1.1,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        # One pooled keep-alive connection reused across requests. `transport` is
        # injected only by tests (httpx.MockTransport) to simulate the tunnel.
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=httpx.Timeout(timeout, connect=5.0),
            transport=transport,
        )
        self._metrics_url = metrics_url
        self._model = model
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._repetition_penalty = repetition_penalty

    async def queue_time_totals(self) -> tuple[float, int] | None:
        """Current (sum, count) of vLLM's queue-time histogram. The caller reads
        this before and after a request; the delta is that request's queue wait
        (exact under the single-concurrency demo)."""
        try:
            resp = await self._client.get(self._metrics_url)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.debug("vllm /metrics unavailable: %s", exc)
            return None
        return parse_histogram_totals(resp.text, QUEUE_METRIC)

    async def stream(
        self,
        messages: list[dict[str, str]],
        telemetry: StreamTelemetry,
    ) -> AsyncIterator[str]:
        """Yield content deltas for `messages`, recording token timings and the
        final usage count into `telemetry`. Raises `TunnelDown` if the first
        token never arrives; a mid-stream drop stops cleanly."""
        body = {
            "model": self._model,
            "messages": messages,
            "stream": True,
            "temperature": self._temperature,
            "repetition_penalty": self._repetition_penalty,
            "max_tokens": self._max_tokens,
            # vLLM emits a trailing usage-only chunk so we get exact output
            # tokens for the tokens/sec metric instead of counting SSE chunks.
            "stream_options": {"include_usage": True},
        }
        telemetry.mark_request_sent()
        try:
            async with self._client.stream(
                "POST", "/chat/completions", json=body
            ) as resp:
                if resp.status_code >= 400:
                    detail = (await resp.aread()).decode("utf-8", "replace")[:500]
                    raise VLLMError(f"vLLM {resp.status_code}: {detail}")
                async for chunk in self._iter_content(resp, telemetry):
                    yield chunk
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            raise TunnelDown(str(exc)) from exc
        except httpx.TransportError as exc:
            # Read/network error: degradation only if nothing streamed yet;
            # otherwise the partial answer stands and we stop quietly.
            if telemetry.first_token_at is None:
                raise TunnelDown(str(exc)) from exc
            logger.warning("vllm stream dropped mid-answer: %s", exc)

    async def _iter_content(
        self, resp: httpx.Response, telemetry: StreamTelemetry
    ) -> AsyncIterator[str]:
        async for line in resp.aiter_lines():
            if not line.startswith("data:"):
                continue
            payload = line[len("data:") :].strip()
            if payload == "[DONE]":
                break
            try:
                data = json.loads(payload)
            except json.JSONDecodeError:
                continue
            if usage := data.get("usage"):
                telemetry.output_tokens = usage.get("completion_tokens")
            for choice in data.get("choices") or []:
                content = (choice.get("delta") or {}).get("content")
                if content:
                    telemetry.mark_token()
                    yield content

    async def aclose(self) -> None:
        await self._client.aclose()
