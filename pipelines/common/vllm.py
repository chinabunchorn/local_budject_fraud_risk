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
    ) -> None:
        self._client = httpx.Client(base_url=base_url, timeout=timeout)
        self._model = model
        self._tracer = tracer

    def generate_json(
        self,
        messages: list[dict[str, str]],
        schema: dict,
        *,
        name: str = "llm",
        temperature: float = 0.0,
        metadata: dict | None = None,
    ) -> str:
        """Return the guided-JSON content for `messages` bound to `schema`."""
        body = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
            # vLLM structured-output extension; XGrammar per the locked stack
            "guided_json": schema,
            "guided_decoding_backend": "xgrammar",
        }
        response = self._client.post("/chat/completions", json=body)
        response.raise_for_status()
        data = response.json()
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
