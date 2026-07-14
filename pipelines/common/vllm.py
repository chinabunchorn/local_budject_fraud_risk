"""vLLM client — OpenAI-compatible endpoint at the local end of the SSH tunnel.

THE single path for pipeline LLM calls (CLAUDE.md): binds `guided_json` so the
decoder can only emit the given schema (XGrammar), runs at temperature 0 for
reproducible batch scoring, and traces every call to Langfuse. When the tunnel
is down the request raises — batch scoring is an attended, walltime-windowed
runbook step, not an always-on dependency.

Returns the guided-JSON `content` string; the caller validates it against
`schemas.RiskAssessment` (and the guardrails stage). The model's separate
`reasoning_content` (<think>) is forwarded to Langfuse only — never returned to
a user surface.
"""

from __future__ import annotations

import time

import httpx

from common.observability import Generation, Tracer


class VLLMClient:
    def __init__(
        self,
        base_url: str,
        model: str,
        *,
        timeout: float = 180.0,
        tracer: Tracer | None = None,
        max_retries: int = 3,
        retry_backoff: float = 2.0,
    ) -> None:
        self._client = httpx.Client(base_url=base_url, timeout=timeout)
        self._model = model
        self._tracer = tracer
        self._max_retries = max_retries
        self._retry_backoff = retry_backoff

    def _post_with_retry(self, body: dict) -> dict:
        """POST, retrying transient transport errors (the plain-ssh tunnel drops
        under sustained batch load). A 4xx/5xx is NOT retried — it's a real
        request/server error, so it surfaces immediately."""
        last: Exception | None = None
        for attempt in range(self._max_retries):
            try:
                response = self._client.post("/chat/completions", json=body)
                response.raise_for_status()
                return response.json()
            except httpx.TransportError as exc:
                last = exc
                if attempt < self._max_retries - 1:
                    time.sleep(self._retry_backoff * (attempt + 1))
        assert last is not None
        raise last

    def generate_json(
        self,
        messages: list[dict[str, str]],
        schema: dict,
        *,
        name: str = "llm",
        temperature: float = 0.0,
        max_tokens: int | None = None,
        extra_body: dict | None = None,
        metadata: dict | None = None,
    ) -> str:
        """Return the guided-JSON content for `messages` bound to `schema`.

        `extra_body` carries extra sampling params (e.g. `repetition_penalty`) —
        used to fight the whitespace-loop degeneration this vLLM has under greedy
        guided decoding."""
        body: dict = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
            # vLLM structured-output extension. The backend is chosen server-side
            # (initialised as 'auto'); this vLLM 400s on a request-level backend
            # override, so we never send one. `guided_json` alone also suppresses
            # any <think> prefix — the grammar admits only schema tokens.
            "guided_json": schema,
            **(extra_body or {}),
        }
        if max_tokens is not None:
            # bound the intermittent whitespace-loop degeneration (the JSON
            # grammar permits unbounded whitespace, and greedy decoding sometimes
            # loops on it); a truncated result fails to parse and the caller
            # re-asks with a fresh generation.
            body["max_tokens"] = max_tokens

        data = self._post_with_retry(body)
        message = data["choices"][0]["message"]
        content = message.get("content") or ""
        reasoning = message.get("reasoning_content")

        if self._tracer is not None:
            self._tracer(
                Generation(
                    name=name,
                    model=self._model,
                    input=messages,
                    output=content,
                    reasoning=reasoning,
                    usage=data.get("usage"),
                    metadata=metadata or {},
                )
            )
        return content

    def close(self) -> None:
        self._client.close()
