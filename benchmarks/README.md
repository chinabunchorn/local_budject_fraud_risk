# Streaming optimization benchmark (Phase 4)

Measures the live RAG chat path and produces the baseline-vs-optimized
comparison report for the presentation.

## What it measures (per request)

| Metric | Meaning | Source |
|---|---|---|
| `ttft_raw_ms` | request-sent → first token | backend wall clock |
| `ttft_display_ms` | request-received → first sentence shown | backend (incl. sentence-gating buffer) |
| `queue_wait_ms` | vLLM scheduler queue time | vLLM `/metrics` histogram delta around the request |
| `decode_tokens_per_sec` | output tokens / generation time | usage chunk + token timings |
| `e2e_ms` | request-received → done | backend wall clock |

TTFT is reported **twice on purpose**: raw (pure model + tunnel) and display
(what the auditor perceives, including the per-sentence guardrail buffer). The
gap is the honest cost of "flag, never accuse" while streaming.

## Levers A/B'd

The backend exposes two optimization levers per request so configs can be
compared against **one** running backend (no restart):

- `rerank_top_n` — fewer reranked passages → fewer prefill tokens → lower TTFT
- `max_tokens` — tighter cap → shorter tail → lower e2e

Client-level levers (keep-alive connection reuse, streaming vs non-streaming)
are structural and measured/noted separately.

## Running

Offline, synthetic (proves the report renders — no backend needed):

```bash
uv run --project ../backend python stream_bench.py --selftest
```

Against a live backend (needs the full stack up + a LANTA window for real
numbers; use `stub_vllm.py` for a LANTA-free dry run):

```bash
# terminal 1 — stand in for the tunnel endpoint (dev/CI only)
STUB_TTFT_MS=200 STUB_TOKEN_MS=15 STUB_QUEUE_MS=60 \
  uv run --project ../backend python stub_vllm.py

# terminal 2 — replay the scripted questions under both configs
uv run --project ../backend python stream_bench.py \
  --base-url http://localhost:8080 --username admin --password '...' --repeat 3
```

Outputs land in `results/<timestamp>.{json,html}`. The HTML is a self-contained,
theme-aware report (small-multiple panel per metric + a table twin) — screenshot
it for slides, or open directly.

> The stub is a **dev/CI stand-in**, not the model. Real TTFT / queue-wait /
> tokens-sec figures for the presentation come from the attended LANTA window
> (see `docs/runbooks/` — added with the Phase-4 exit gate).
