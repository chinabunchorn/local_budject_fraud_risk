"""vLLM client — request shape + response/reasoning handling, no network."""

import json

import httpx

from common.observability import Generation
from common.vllm import VLLMClient

_COMPLETION = {
    "choices": [
        {
            "message": {
                "content": '{"risk_level":"LOW"}',
                "reasoning_content": "ขั้นตอนการคิดภายใน",
            }
        }
    ],
    "usage": {"prompt_tokens": 120, "completion_tokens": 40, "total_tokens": 160},
}


def _mock_client(captured: dict) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=_COMPLETION)

    return httpx.Client(base_url="http://vllm.test/v1", transport=httpx.MockTransport(handler))


def test_generate_json_binds_schema_temperature_and_returns_content():
    captured: dict = {}
    client = VLLMClient("http://vllm.test/v1", "typhoon-test")
    client._client = _mock_client(captured)

    schema = {"type": "object", "properties": {"risk_level": {"type": "string"}}}
    messages = [{"role": "user", "content": "วิเคราะห์ความเสี่ยง"}]
    content = client.generate_json(messages, schema, name="risk_scoring")

    assert content == '{"risk_level":"LOW"}'
    assert captured["path"].endswith("/chat/completions")
    body = captured["body"]
    assert body["guided_json"] == schema
    # recent vLLM 400s on a request-level backend override — must not be sent
    assert "guided_decoding_backend" not in body
    assert body["temperature"] == 0.0
    assert body["model"] == "typhoon-test"
    assert body["messages"] == messages


def test_reasoning_and_usage_go_to_the_tracer_only():
    traced: list[Generation] = []
    client = VLLMClient("http://vllm.test/v1", "typhoon-test", tracer=traced.append)
    client._client = _mock_client({})

    content = client.generate_json([{"role": "user", "content": "x"}], {}, name="risk_scoring")

    # the reasoning trace is NEVER in the returned content — Langfuse only
    assert "ขั้นตอนการคิดภายใน" not in content
    assert len(traced) == 1
    gen = traced[0]
    assert gen.name == "risk_scoring"
    assert gen.output == '{"risk_level":"LOW"}'
    assert gen.reasoning == "ขั้นตอนการคิดภายใน"
    assert gen.usage["total_tokens"] == 160
