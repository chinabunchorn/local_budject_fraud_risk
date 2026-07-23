# Runbook — Phase 4 live RAG chatbot: bring-up, exit gate & streaming benchmark

The chatbot is the **one** feature that calls live inference, through the SSH
tunnel to a vLLM job on LANTA (ARCHITECTURE Pipeline 3). It is scoped to
**demonstration windows**: when the tunnel is down it degrades to an explicit
"outside demonstration window" state — by design, not a bug. Everything else in
this repo (the whole dashboard) stays fully functional with LANTA offline.

LANTA enforces **password + Google 2FA on every SSH connection**, so this whole
sequence is an **attended manual runbook** — no unattended automation
(`hpc/LANTA_CONFIG_NOTES.md`, memory `lanta-tunnel-attended`). Budget ~15 min to
first token on a cold job.

> **Rehearse offline first.** Everything except the real model is verifiable
> without LANTA using the stub (`benchmarks/stub_vllm.py`) — do that the day
> before so the attended window is only about real numbers. See
> "Offline dress rehearsal" at the bottom.

---

## 0. Pre-window prep (app zone — no LANTA, do this ahead of time)

- [ ] Stack up and healthy: `docker compose up -d` (postgres, redis, minio, **tei-embed**, **tei-rerank**, backend). On the dev Mac reach the API on published `:8080` (Traefik provider is dead locally — memory `dev-machine-docker`).
- [ ] Schema current: `cd infra/db && DATABASE_URL=… uv run alembic upgrade head`.
- [ ] Corpus embedded (retrieval needs it): `psql … -c "select count(*) from chunks where embedding is not null;"` → non-zero (≈1,289) **and** `select count(*) from regulations where embedding is not null;` → non-zero (≈447).
- [ ] Backend image includes the chat router (rebuild if stale): `docker compose build backend && docker compose up -d backend`; `curl -s localhost:8080/openapi.json | grep -q '"/api/chat"'`.
- [ ] Frontend built with the chat page: `cd frontend && npm run build && npm run start` → `http://localhost:3001/chat` loads (behind login).
- [ ] `.env` carries the chat vars (see `.env.example`): `TEI_EMBED_URL`, `TEI_RERANK_URL`, `VLLM_BASE_URL`, **`VLLM_SERVED_MODEL`**, `VLLM_MODEL_ID`. In compose the backend reaches the host-side tunnel via `host.docker.internal:8000` (already wired, `extra_hosts: host-gateway`); a host-run backend uses `127.0.0.1:8000`.
- [ ] TEI reachable from the backend: `docker compose exec backend python -c "import urllib.request;urllib.request.urlopen('http://tei-embed:80/health',timeout=5)"`.

**Pre-window prep — completed & verified 2026-07-23 (dev Mac):** stack healthy
(10/10); schema at `0008` (no Phase-4 migration — stateless chat); embeddings
present (chunks **1297**, regulations **447**); backend rebuilt → `/api/chat`
live, container env `VLLM_BASE_URL=http://host.docker.internal:8000/v1`,
`VLLM_SERVED_MODEL=typhoon-chat`, TEI on the compose network. End-to-end against
the **real corpus**, tunnel down: the chat did real embed→pgvector→rerank then
degraded cleanly (no 500). Pointed at the stub, the **happy path** returned a
grounded answer whose `[C1]` resolved to the actual **fiscal-discipline-act-2561/s.37**
text — retrieval quality confirmed. Telemetry populated incl. queue-wait from the
`/metrics` delta.
- **Fix found during prep:** the reranker (`--max-batch-tokens 1024`) 413'd on
  the full candidate set → the TEI client now **clamps each passage to 220 chars
  and batches** at 12/request, and `top_k` dropped 20→10 (20 candidates). On this
  dev Mac the reranker is Rosetta-emulated so the rerank stage is ~30–40 s — a
  local artifact only; native amd64 on the app VM is sub-second (memory
  `dev-machine-docker`). 24 backend tests green (2 new rerank tests).

---

## 1. Bring the inference engine up (attended, on LANTA login node)

```bash
# from the app VM (or your workstation) — 2FA prompt on connect
ssh <LANTA_SSH_USER>@lanta.nstda.or.th
cd /project/tn999991-cstu/chin
sbatch slurm/serve_vllm.sbatch          # gpu partition (5-day cap), TP2, 2×A100
myqueue                                 # wait for STATE = RUNNING
cat run/current_node.txt                # the compute node the tunnel targets
tail -f m3-vllm-serve-*.out             # watch until "Application startup complete"
```

Notes / gotchas (verified live, `hpc/LANTA_CONFIG_NOTES.md` + CLAUDE.md):
- Use **`gpu`** (5-day), never `gpu-devel` (2h cap silently kills a "persistent" server).
- The live container has been **vLLM 0.9.2** on the real cluster (the repo `.sif` name says 0.11.0 — trust `/v1/models`, not the filename). Chat is free-text, so we don't need per-request guided decoding here.
- **Served-model alias is the single source of truth.** Whatever `--served-model-name` the job used, `GET /v1/models` reports it. The backend's request `model` field MUST equal it (`VLLM_SERVED_MODEL`). Historically that alias is **`typhoon-chat`**; the provenance HF id stays in `VLLM_MODEL_ID`.

## 2. Open the tunnel (attended, from the app VM)

```bash
LANTA_SSH_USER=<user> LANTA_PROJECT_DIR=/project/tn999991-cstu/chin \
  bash hpc/scripts/tunnel.sh            # plain ssh -N (autossh can't answer 2FA); leave it running
```

Keep this terminal open for the whole window. If it drops under load (the plain
tunnel does — CLAUDE.md), just re-run it.

## 3. Smoke test through the tunnel (from the app VM)

```bash
bash hpc/scripts/smoke_test.sh          # /models + streamed Thai + guided enum
curl -s http://127.0.0.1:8000/v1/models | python -m json.tool   # note the served id
```

- [ ] `/v1/models` answers → tunnel + server alive.
- [ ] Set `VLLM_SERVED_MODEL` to exactly that id and restart the backend so the value takes: `docker compose up -d backend` (or export + restart uvicorn).
- [ ] Queue-wait metric is live (Workstream D depends on it): `curl -s http://127.0.0.1:8000/metrics | grep vllm:request_queue_time_seconds_count` → a number.

---

## 4. Exit gate — the 10 scripted questions (ROADMAP Phase 4)

Questions live in `benchmarks/questions.yaml` (project + regulation mix, incl.
the วัดไทร high-risk story and the ถังน้ำ unit-price case). Run them **through the
UI** so citations are clicked and verified:

1. Log in at `http://localhost:3001/chat`.
2. Ask each of the 10 questions. For each, confirm:
   - [ ] a Thai answer streams with inline `[C#]` chips;
   - [ ] the **แหล่งอ้างอิง** list resolves — clicking a document citation opens the real PDF at the cited page; a regulation citation opens the section text (มาตรา ๓๗ etc.);
   - [ ] **no banned verdict term** appears (the sentence-gate replaces any such segment with the neutral notice);
   - [ ] the **ประสิทธิภาพการสตรีมคำตอบ** panel shows real numbers (TTFT, queue wait, tokens/sec, e2e).
3. Gate: **all 10 answered with verifiable citations**, zero accusatory language.

## 5. Streaming benchmark — the real optimization numbers (Workstream D)

This is the instrumented version of the same run (keep it **single-concurrency**
— no one else hitting the chat — so the vLLM queue-wait delta is exact):

```bash
cd benchmarks
uv run --project ../backend python stream_bench.py \
    --base-url http://localhost:8080 \
    --username <auditor> --password <…> \
    --repeat 3
# → results/<ts>.json  and  results/<ts>.html  (baseline vs optimized report)
```

- [ ] Report renders (small-multiple panels + table twin). Screenshot for slides.
- [ ] Sanity: `optimized` (rerank_top_n 6 / max_tokens 768) shows lower TTFT & e2e than `baseline` (12 / 1024); tokens/sec roughly flat. If a lever shows no effect, say so — the honest result is the presentation, not a target.
- [ ] Note the **TTFT raw vs display gap** — that is the measured cost of sentence-gated guardrails; call it out rather than hide it.

## 6. Kill-and-degrade drill (ROADMAP exit gate: "kill mid-session")

With a chat session open in the browser:

```bash
# on LANTA login node
scancel $(cat /project/tn999991-cstu/chin/run/current_job.txt)
```

- [ ] Ask another question → the chat shows the amber **"ผู้ช่วยสดไม่พร้อมใช้งานขณะนี้ (อยู่นอกช่วงเวลาสาธิต)"** banner and points to the dashboard (the `TunnelDown` → `degraded` SSE path). **No 500, no crash.**
- [ ] Switch to **ภาพรวม / โครงการ / drill-down / แนวโน้ม** — the whole dashboard still works with the job dead (offline-first). `lsof -nP -iTCP:8000 -sTCP:LISTEN` may still show the tunnel process, but requests to it now fail fast into the degraded state.

## 7. Recovery (optional, to show the lifecycle)

Re-run step 1 (`sbatch`) → step 2 (`tunnel.sh`, re-check `current_node.txt` if the
node changed) → step 3 (smoke). Cold restart to first token target: minutes,
because weights are pre-staged on Lustre.

---

## Record the result here after the window

- Date / window / operator:
- `/v1/models` served id (→ `VLLM_SERVED_MODEL`):
- 10-question gate: __/10 answered with resolving citations; banned-term hits: __
- Benchmark: baseline vs optimized TTFT __/__ ms, queue __/__ ms, tok/s __/__, e2e __/__ ms; report path:
- Kill drill: degraded banner shown [y/n]; dashboard unaffected [y/n]:
- Langfuse: chat traces present with retrieval set captured [y/n]:


## Done Record the phase 4

Date / window / operator: 2026-07-24 / attended demo window / Chin
10-question gate: 10/10 answered with resolving citations; banned-term hits: 1 (หลุดแผนพรางคำข้อความ ค อ ร์ รั ป ชั น แต่ระบบดักบล็อกข้อความปฏิเสธด่านสุดท้ายได้)
Benchmark (baseline vs optimized ต่อค่าเมตริก p50):
TTFT raw (โมเดล+ทันเนล): 120.7 ms / 65.5 ms (ฝั่งฮาร์ดแวร์ปลายทางเร็วขึ้น 46%)
TTFT display (ที่ผู้ใช้เห็น): 38,474.7 ms / 39,104.8 ms (สะท้อนคอขวด Reranker บน CPU Local)
Queue (เวลารอคิว vLLM): 0.1 ms / 0.1 ms
Tok/s (ความเร็วสร้างคำตอบ): 114.2 / 116.1 tokens/sec
e2e (เวลารวมทั้งคำขอ): 41,353.5 ms / 42,870.4 ms
Report path: benchmarks/results/ (ไฟล์ HTML ลงวันที่ 2026-07-24 เวลา 00:23)
Kill drill: degraded banner shown [y]; dashboard unaffected [y]
Langfuse: chat traces present with retrieval set captured [y]

## Open items

- **Lexicon gap found in the window & fixed (2026-07-24):** the recorded
  "banned-term hit" was the model reaching for **คอร์รัปชัน** (Thai loanword for
  corruption), which was **not** in `BANNED_TERMS` — so the shared lexicon did
  NOT block it (whatever stopped it in the window was the model hedging / the
  disclaimer, not our guardrail). Now added to `shared/schemas/guardrails.py`
  (blocks both batch + chat), verified live in the running backend, test added.
  **Still open (Phase-5 red-team):** a spaced-out evasion like `ค อ ร์ รั ป ชั น`
  still slips through — needs whitespace/zero-width normalisation before matching,
  weighed against false positives on legitimate Thai spacing.
- **Benchmark on the app VM for representative numbers:** on the dev Mac the
  reranker is Rosetta-emulated (~40 s rerank stage), so **TTFT-display and e2e are
  reranker-bound, not representative** — only **TTFT-raw (120.7→65.5 ms, −46 %)**
  and tok/s reflect the real model. Re-run `stream_bench.py` on the native amd64
  app VM to get presentable display/e2e (and do NOT attribute the raw→display gap
  to sentence-gating — here it is the emulated reranker).
- **Langfuse creds** must be set in the backend env for chat traces to record (best-effort; absent → no-ops, chat still works).
- **Pseudonymization** (carried from `demo_dashboard.md`): the chat cites real entity names — decide before any external demo.
- **Tunnel stability under the benchmark**: if the plain `ssh -N` tunnel drops mid-benchmark, re-run the tunnel and re-run `stream_bench.py` (it's a fresh run, not resumable).

---

## Offline dress rehearsal (no LANTA — do this before the window)

Proves the entire path except the real model, so the attended window has no surprises:

```bash
# terminal 1 — stand in for the tunnel endpoint
STUB_TTFT_MS=200 STUB_TOKEN_MS=15 STUB_QUEUE_MS=60 \
  uv run --project backend python benchmarks/stub_vllm.py     # serves :8000

# point the backend at it (host-run backend) and restart:
#   VLLM_BASE_URL=http://127.0.0.1:8000/v1  VLLM_SERVED_MODEL=typhoon-chat
```

Then walk `http://localhost:3001/chat`: answers stream with citations, the
telemetry panel populates, and `benchmarks/stream_bench.py --selftest` renders a
sample report. Verified 2026-07-23: UI + telemetry panel + degraded state in
headless Chrome; backend happy path + degraded path against the **real corpus**
(stub standing in for the tunnel); queue-wait recovered via the `/metrics` delta.
Note the stub must bind `0.0.0.0` (not `127.0.0.1`) so the backend container
reaches it via `host.docker.internal`.
