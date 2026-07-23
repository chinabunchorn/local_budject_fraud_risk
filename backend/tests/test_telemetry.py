"""Streaming telemetry math — the numbers the optimization story reports."""

from __future__ import annotations

import time

from app.services.telemetry import StreamTelemetry
from app.services.vllm import parse_histogram_totals


def test_metrics_computed_from_marks():
    t = StreamTelemetry()
    with t.stage("embed"):
        time.sleep(0.01)
    t.mark_request_sent()
    time.sleep(0.005)
    t.mark_token()  # first token
    t.mark_first_display()
    time.sleep(0.01)
    t.mark_token()
    t.mark_token()
    t.output_tokens = 3
    t.queue_wait_ms = 20.0
    t.mark_done()

    m = t.as_dict()
    assert m["ttft_raw_ms"] > 0
    assert m["ttft_backend_ms"] >= m["ttft_raw_ms"]  # backend includes the stage
    assert m["decode_tokens_per_sec"] is not None
    assert m["output_tokens"] == 3
    assert m["queue_wait_ms"] == 20.0
    # prefill = ttft_raw - queue_wait
    assert m["prefill_ms"] == round(m["ttft_raw_ms"] - 20.0, 1)
    assert "embed" in m["stages_ms"]
    assert m["e2e_ms"] > 0
    assert m["degraded"] is False


def test_degraded_request_has_no_ttft():
    t = StreamTelemetry()
    t.mark_request_sent()
    t.degraded = True
    t.mark_done()
    m = t.as_dict()
    assert m["ttft_raw_ms"] is None
    assert m["decode_tokens_per_sec"] is None
    assert m["degraded"] is True


def test_tokens_per_sec_falls_back_to_chunk_count():
    t = StreamTelemetry()
    t.mark_request_sent()
    t.mark_token()
    time.sleep(0.02)
    t.mark_token()
    # no usage set -> uses chunk count (2)
    assert t.as_dict()["output_tokens"] == 2
    assert t.as_dict()["decode_tokens_per_sec"] is not None


def test_parse_histogram_totals():
    text = """
# HELP vllm:request_queue_time_seconds queue time
# TYPE vllm:request_queue_time_seconds histogram
vllm:request_queue_time_seconds_bucket{le="0.1",model_name="typhoon-chat"} 3
vllm:request_queue_time_seconds_sum{model_name="typhoon-chat"} 1.5
vllm:request_queue_time_seconds_count{model_name="typhoon-chat"} 4
""".strip()
    total = parse_histogram_totals(text, "vllm:request_queue_time_seconds")
    assert total == (1.5, 4)


def test_parse_histogram_totals_absent_returns_none():
    assert parse_histogram_totals("# nothing here\n", "vllm:missing") is None
