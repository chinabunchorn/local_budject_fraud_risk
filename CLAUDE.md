# CLAUDE.md — Mission 3: Local Budget Fraud Risk & Document Intelligence Assistant

Thai-language AI assistant for government auditors analyzing sub-district project budgets.
Features: pre-computed risk dashboard, risk factor & trend analysis, RAG document chatbot with
citations, regulation linkage (State Fiscal and Financial Discipline Act B.E. 2561), auditor
feedback sentiment. Prototype scale: 2–3 sub-districts, 10–20 projects, curated from REAL
gathered documents (decision July 2026 — real data over mock; see ROADMAP corpus decision).
Sensitivity-check before ingest; synthetic anomaly projects added only if the real sample
doesn't exercise the risk factors.

Full design: `docs/ARCHITECTURE.md`. Build sequence: `docs/ROADMAP.md`. Diagrams: `docs/diagrams/`.
Read all three before scaffolding or making architectural decisions.

## Non-negotiable constraints

1. **LANTA HPC lifecycle.** All LLM inference runs in vLLM inside an Apptainer container under
   Slurm on the LANTA supercomputer. Compute nodes are air-gapped (no internet) and jobs die at
   partition walltime (verified: `gpu` caps at 5 days; `gpu-devel` at 2 h — never use it for
   serving). Never write code that assumes a permanent endpoint inside LANTA, and never fetch
   models/packages at runtime on compute nodes — everything is pre-staged to Lustre from the
   transfer node (the only node with outbound internet). `scrontab` is DISABLED on LANTA; job
   resubmission runs from the app VM. LANTA enforces password + Google 2FA on EVERY SSH
   connection — unattended automation (tunnel keepalive, cron resubmission, Prefect sbatch) is
   blocked until ThaiSC confirms a deploy-key exemption, so treat those as manual runbook steps.
   Hands-on verified facts and gotchas: `hpc/LANTA_CONFIG_NOTES.md` — read it before touching `hpc/`.
2. **Offline-first.** The dashboard must be fully functional with ZERO running Slurm jobs — it
   reads only pre-computed, guardrails-validated JSON from PostgreSQL. The chatbot is the ONLY
   feature allowed to call live inference, through an SSH tunnel
   (app VM → LANTA login node → compute node :8000, OpenAI-compatible API). When the tunnel is
   down, the chatbot must degrade gracefully with an explicit "outside demonstration window"
   state — this is designed behavior, not an error.
3. **Responsible AI — "flag, never accuse."** Risk verdicts are a closed enum
   `{LOW, MEDIUM, HIGH, REQUIRES_INVESTIGATION}` enforced at decode time (vLLM `guided_json` /
   XGrammar) and re-validated post-hoc (Guardrails AI: schema, score ranges 0–100,
   citation-existence, non-accusation lexicon). Never generate prompts, code, or UI copy that
   states fraud/corruption as a conclusion — ทุจริต / โกง / ฉ้อโกง / "fraud" / "corruption" as
   verdicts are banned (allowed only inside quoted regulation titles). Every surface states that
   the human auditor makes the final decision. Model reasoning shown in the UI ("how the model
   got the answer") is ONLY the structured `reasoning_steps` chain (evidence → observation →
   interpretation) emitted inside guided_json — grammar-constrained and lexicon-validated like
   all free text. The raw `<think>` trace is NEVER user-facing: Langfuse only (debug/audit).
4. **Primary language is Thai** for documents, prompts, chat, and UI. Use PyThaiNLP for
   segmentation. Always UTF-8. Test parsing against legacy-font (TH Sarabun era) and scanned
   PDFs; route garbled or scanned pages to Typhoon-OCR.

## Locked tech stack (do not substitute)

- **Frontend:** Next.js 15 + TypeScript, Tailwind CSS + shadcn/ui, Apache ECharts, SSE for chat
- **Backend:** FastAPI + Pydantic v2; JWT auth with simple RBAC roles (Admin / Senior Auditor /
  Auditor). Keycloak is a documented upgrade path — do NOT add it now.
- **Agent/RAG:** LangGraph; retrieval on pgvector; BGE-M3 embeddings + BGE-reranker-v2-m3 served
  via Text-Embeddings-Inference (TEI) on the app VM
- **Data:** PostgreSQL 16 + pgvector + JSONB (single unified store), Redis 7, MinIO; Alembic
  migrations
- **Batch:** Prefect 3 flows on the app VM; they drive `sbatch` / `squeue` / SFTP over SSH to the
  LANTA login node
- **Parsing:** Docling (born-digital) + Typhoon-OCR 1.5 (scanned/garbled; the LANTA batch job
  runs it via plain transformers in the `hf` mamba env — the verified path; vLLM-offline
  migration only after re-passing the OCR acceptance test) + PyThaiNLP
- **Models:** `scb10x/typhoon2.5-qwen3-30b-a3b` (primary, all roles initially — staged, verified
  serving with TP2 + `--max-model-len 8192`); `Qwen/Qwen3-32B` AWQ-INT4 (batch analyst — NOT
  staged; download ONLY if Phase-2 quality evals justify it); `scb10x/typhoon-ocr1.5-2b` (OCR —
  staged, verified on real scanned Thai documents). A100 40GB = Ampere: use BF16 or AWQ/GPTQ-INT4,
  never FP8/GGUF. LANTA's GPU driver supports CUDA ≤ 12.7: use the verified container image
  `vllm/vllm-openai:v0.11.0` (first tag with Qwen3-VL for the OCR model) — never `latest`.
- **Observability:** Langfuse v3 (self-hosted) traces EVERY LLM call (batch and chat);
  Prometheus + Grafana for vLLM/API metrics
- **Rejected — do not reintroduce:** Marker (weights license), ApeRAG, Elasticsearch, Qdrant,
  Neo4j, Kubernetes, model fine-tuning.

## Repository layout (create exactly this)

```
mission3/
├── CLAUDE.md
├── README.md
├── docker-compose.yml          # app-zone stack: traefik, postgres+pgvector, redis, minio, langfuse, tei
├── .env.example                # all secrets/config templated; never commit .env
├── docs/
│   ├── ARCHITECTURE.md         # full system design (source of truth)
│   ├── ROADMAP.md              # phased execution plan (source of truth for sequencing)
│   ├── diagrams/               # mermaid sources
│   └── runbooks/               # demo-window checklist, tunnel recovery, job resubmission
├── shared/                     # installable package: THE data contracts
│   └── schemas/                # Pydantic: RiskResult (enum-locked), Chunk, Citation, Feedback
├── backend/                    # FastAPI application
│   ├── app/
│   │   ├── api/                # routers: auth, dashboard, projects, chat (SSE), admin
│   │   ├── core/               # settings, security/JWT, dependencies
│   │   ├── db/                 # SQLAlchemy models, session, queries
│   │   ├── rag/                # LangGraph graph, retrieval, rerank, prompt assembly
│   │   ├── guardrails/         # output validators: schema, lexicon, citation existence
│   │   └── services/           # vllm client (tunnel endpoint), tei client, langfuse
│   └── tests/
├── frontend/                   # Next.js app (dashboard + chat)
├── pipelines/                  # Prefect flows (offline batch)
│   ├── flows/                  # ingest_documents, build_embeddings, score_risk, feedback_sentiment
│   ├── prompts/                # versioned Thai prompt templates — never inline strings in code
│   └── hpc_io/                 # sbatch submit, squeue poll, sftp staging helpers
├── hpc/                        # everything that runs on LANTA (not locally)
│   ├── apptainer/              # vllm.def + build notes
│   ├── slurm/                  # serve_vllm.sbatch, batch_infer.sbatch, scrontab entry
│   └── scripts/                # stage_weights.sh, tunnel.sh (autossh), smoke_test.sh
├── infra/
│   └── db/                     # alembic migrations, init SQL (pgvector extension)
└── data/
    ├── corpus/                 # real documents; gitignored — canonical copy lives in MinIO
    └── regulations/            # fiscal-discipline act sections (text)
```

## Architectural rules (enforce in every change)

- `shared/schemas` is the single source of truth for the risk-result contract. Backend,
  pipelines, and guardrails all import it. Never duplicate a schema definition.
- The ONLY write path into the `risk_results` table is the guardrails validation stage.
- Every LLM call goes through the vLLM client service and is traced to Langfuse — no ad-hoc
  OpenAI client instantiation scattered in code.
- Time-series/trend analytics are SQL (window functions / materialized views) — no LLM in that path.
- Secrets only via environment variables; LANTA access uses a dedicated SSH deploy key.
- Model weights are never committed and never downloaded in application code.
- Python 3.11+, fully type-hinted, ruff + pytest; TypeScript strict mode. Thai prompt templates
  live in `pipelines/prompts/` as versioned files.

## Current status & next tasks (see docs/ROADMAP.md — Phases 0–3 DONE incl. exit gates; next: Phase 4 live RAG chatbot)

**Where we are (2026-07-22):** Phase 2 (ingestion + structured extraction + real
Typhoon-2.5 risk scoring, 22 projects) and Phase 3 (offline-first dashboard: FastAPI
read API + Next.js UI, exit gate met with LANTA fully offline) are COMPLETE, plus two
post-Phase-3 rounds driven by mentor feedback: the evidence-first citation viewer
(inline excerpts → real source PDFs opened at the cited page, every project guaranteed
a PDF entry point) and item-level anomaly detection (`/budget-items` — unit-price YoY
spikes, vendor locks, curated standard-price comparison; MVP: the หัวเขา 2,000L water
tanks, +51.1%/unit, same single-bidder shop 2 years). Everything user-facing reads
pre-computed, document-cited data — no LLM call anywhere in the dashboard path.
**Next:** Phase 4 (LangGraph RAG chatbot through the tunnel, needs a LANTA demo
window) + re-run `score_risk` at that window so the 2 new tank projects get their
guardrails-validated risk results (flow resumes over unscored projects). Details of
every phase below.

**Done (July 2026).** Repo scaffolded and merged (PR #2); app-zone `docker-compose` verified
healthy end-to-end (all 9 services, Thai embedding + rerank probes pass); `shared/schemas`
enum-locked contract merged with 33 tests; Alembic initial migration applied. Phases 0–1
executed by hand on LANTA and verified: weights staged (Typhoon 2.5 + Typhoon-OCR), vLLM
serving with streaming + guided-choice enum lock reached through the SSH tunnel end-to-end,
OCR batch validated on a real 33-page scanned Thai financial report, kill-and-recovery
behavior confirmed. All accounts/partitions/paths/gotchas: `hpc/LANTA_CONFIG_NOTES.md`.

**Open blockers:**
- 2FA on every LANTA SSH blocks unattended automation — question pending with
  thaisc-support@nstda.or.th. Until resolved, demo-window bring-up (submit → tunnel → smoke
  test) is a manual runbook, and Prefect flows must treat LANTA I/O as manually-triggered steps.
- Qwen3-32B AWQ deliberately NOT staged (roadmap "one model until forced otherwise").

**Phase 2 progress (July 2026):**
1. DONE — real corpus (20 projects, 2 sub-districts, FY2565–2568, 60 PDFs) normalized,
   uploaded to MinIO with generated manifest; regulation index ingested (447 sections:
   Fiscal Discipline Act + Procurement Act + MoF Regulation — ข้อ ๒๐ is the
   threshold-splitting citation). Migration 0003: document scopes, procurement fields, bids.
2. DONE — ingestion flow ran on the real corpus: 32 docs COMPLETED (352 chunks embedded,
   retrieval spot-checks precise); 28 docs / 649 pages in the OCR outbox with sha-prefixed
   names (181 project+budget pages; 481 reference-book pages — the เอกสารกลาง are all scans).
3. DONE — quality gate caught & fixed: legacy-font Thai→Latin layers (LOW_THAI_RATIO rule),
   Docling RapidOCR disabled (Chinese/English model), image-placeholder stripping.
4. DONE — prompts v1 (`pipelines/prompts/risk_scoring/v1/`, per-factor, reasoning steps,
   banned words never in templates) + guardrails stage (`common/guardrails_stage.py`) as the
   ONLY write path into `risk_results` (schema → regulation refs → lexicon → citations).
5. DONE — LANTA OCR pass 2 closed the ingestion loop: all 42 project docs + 8 budget
   reports COMPLETED (1,289 chunks, 688 recovered via Typhoon-OCR); retrieval on
   previously-invisible scanned TORs/บก forms verified. The เอกสารกลาง reference books
   (10 docs incl. the 280-page table book) stay NEEDS_OCR by decision — deferred.
6. DONE — structured extraction (Phase F), 100% deterministic, no LLM
   (`flows/extract_structured.py` + `common/{thai_num,structured_extract,prechecks}.py`,
   53 tests). All 20 projects: budget_total / reference_price / contract_price /
   procurement_method + 51 `bids` rows (20 winners) + `precheck_results` (migration 0004),
   8 checks per project. Decisions from the real data: **bids come from the contract-summary
   §6/§7 tables** (born-digital, bidders WITH amounts + winner) — บก.๐๖ §5 lists
   price-reference SOURCES, not competitive bidders, so it can't fill `bid_amount`;
   บก.01/บก.๐๖ ราคากลาง is a cross-check (agrees with the contract summary on all 7 forms).
   **BOQ = stated grand total only** (budget_lines per-line deferred — OCR'd BOQ tables are
   too noisy for exact arithmetic; the digit total is often only in Thai words, so
   `boq_vs_bk01` reports NA rather than fabricate). Labor-rate / Factor-F prechecks deferred
   (need the เอกสารกลาง reference tables, still NEEDS_OCR).
   The 8th check `yoy_budget_anomaly` is a cross-project, cross-year pass over the curated
   `projects`/`bids` (NOT budget-report PDFs, by decision): recurring same-location projects
   (work-type + บ้าน/หมู่ match) whose budget grows ≥100% YoY (a full doubling) are FLAGged,
   and when the same
   contractor won the recurring project in ≥2 of its years it escalates to `severity: HIGH`
   with a factual `[ระดับความเสี่ยง: สูง]` justification (repetitions, years, cumulative
   award). On the real corpus this flags the ตำบลหัวเขา หมู่ ๔ บ้านวัดไทร road (2566–2568,
   919k→7.79M spike, ส. พงษ์พัฒนา won 2 yrs / ฿3.571M). `severity` stays inside the check —
   the {LOW,MEDIUM,HIGH,REQUIRES_INVESTIGATION} risk *verdict* enum remains reserved for the
   guardrails-validated Phase-G LLM path.
7. DONE (Phase G) — real Typhoon-2.5 run complete: all 20 projects scored, 0 rejected, 68
   citations all resolve, 0 banned terms across every output; 19/20 with full 5 factors (one
   project dropped 2 factors after retries → weights renormalized). Distribution 15 MEDIUM /
   4 REQUIRES_INVESTIGATION / 1 LOW; the ตำบลหัวเขา วัดไทร cluster (2566–2568) all landed
   REQUIRES_INVESTIGATION off the Phase-F YoY HIGH-severity pre-check, and the model's
   BUDGET_DEVIATION reasoning cited the 748% spike — the demo's high-risk story works
   end-to-end. ~22 min for 20 (`model_id=scb10x/typhoon2.5-qwen3-30b-a3b`, prompt_version
   risk_scoring/v2). score_risk flow
   (`flows/score_risk.py` + `common/{vllm,observability,scoring_evidence,aggregation}.py`,
   16 tests). Per project: `assemble_evidence` builds prompt context from committed data only
   — Phase-F financial facts + all 8 `precheck_results` findings (the model reasons over the
   settled arithmetic, never recomputes), real `chunk_id`-labelled excerpts (diverse doc_types
   so `Citation`s resolve), and the cited regulation sections. **PER-FACTOR scoring (prompts
   risk_scoring/v2), forced by the fixed 8192 window:** a full 5-factor `RiskAssessment` output
   is ~3.8k tokens and, with the ~2.5k-token factor definitions, cannot fit meaningful evidence
   in one call (measured live — it truncated). So each factor is scored in its own call
   (`guided_json` → `FactorAssessment`, tunnel, Langfuse-traced), then DETERMINISTIC
   aggregation (`common/aggregation.py`) combines them: weighted `overall_score` (equal weights
   until calibration), banded `risk_level` with a HIGH-severity pre-check forcing
   REQUIRES_INVESTIGATION (verdict is code, not the LLM's free choice), templated non-accusatory
   `summary_th`. Model citations/regulation refs are filtered to what was actually offered
   (hallucinations dropped, not rejected) → guardrails stage (sole write path). Verified againstz
   a stub end-to-end + live per-factor calls (parse, token budget ~5.1k+0.8k/8192, citations).
   **Live serving realities (verified, differ from repo assumptions):** the container is vLLM
   **0.9.2** (not 0.11.0); served alias is `typhoon-chat` (decoupled from provenance `model_id`
   `scb10x/…` via `/v1/models` root); request-level `guided_decoding_backend` is rejected (400)
   and there is no per-request whitespace control, so under pure greedy (temp 0) guided decoding
   **whitespace-loops** on indentation before a constrained token until it truncates (invalid
   JSON). Fixed with **temperature 0.5 + repetition_penalty 1.1** (lets it escape the loop;
   guided_json still constrains the tokens and the verdict is aggregated deterministically) +
   `max_tokens` for fast-fail + up to 5 fresh per-factor retries — yielded 98/100 factor calls
   valid on the real run. The plain-`ssh -N` tunnel drops under load, so the flow is
   **resumable** (client retries transient drops; skips already-scored projects; stops cleanly
   on tunnel death; re-run continues). **Model decision (July 2026): Typhoon 2.5
   confirmed as the sole LLM** — the Phase-2 eval decision point is closed; Qwen3-32B
   AWQ stays unstaged.

**Phase 3 progress (July 2026):**
1. DONE (Workstream A) — FastAPI read layer over the pre-computed data, verified live
   against the real corpus (20 projects served; distribution 15 MEDIUM / 4 REQ_INV /
   1 LOW matches Phase G; วัดไทร drill-down, citation→contract_summary.pdf passage,
   มาตรา ๓๗ text, and trend spikes incl. ตำบลหัวเขา +852.7% FY2568 all resolve).
   Migration 0005 `users` (bcrypt + JWT, roles ADMIN/SENIOR_AUDITOR/AUDITOR;
   `backend/scripts/seed_users.py`). Routers: auth; dashboard overview+trends
   (SQL window functions only, best-effort Redis cache that silently degrades to DB —
   offline-first); projects list (severity-first sort, filters) + drill-down serving
   the guardrails-validated `RiskResult` verbatim via the shared contract, plus bids,
   all 8 precheck findings, documents; feedback capture (sentiment stays NULL for the
   batch flow); `/chunks/{id}` + `/regulations/{code}` citation resolution. Every
   risk-bearing response carries `disclaimer_th` (auditor decides). 19 tests
   (house convention: throwaway rows on live PG, skip when down). Compose `backend`
   service (Dockerfile builds from repo root for ../shared; root `.dockerignore` keeps
   corpus/venvs out of the context) — healthy in-stack, Redis caching confirmed there.
   Gotcha: the Traefik docker provider is dead on the dev Mac (label routes 404 —
   pre-existing, Langfuse's route too); use published port :8080 locally, validate
   Traefik routing on the amd64 app VM.
2. DONE (Workstream B) — Next.js dashboard (`frontend/`, Next 15 pinned — create-next-app
   now defaults to 16 — port 3001; Langfuse holds 3000), verified end-to-end against the
   real corpus with headless system Chrome (login → overview → drill-down → citation
   dialog → trends, zero console errors; screenshots reviewed). Formal executive UI per
   design brief: white surfaces, corporate-blue accents, Sarabun, hairline borders, no
   decorative animation. Dataviz method applied (palette validated on white via
   validate_palette.js): KPI tiles + status-colored risk distribution (labels always
   beside color) + sequential-blue heatmap; drill-down shows the validated RiskResult
   verbatim — per-factor reasoning chains (หลักฐาน→ข้อสังเกต→การตีความ chips) with
   citation dialogs resolving chunk text, regulation viewer, 8 prechecks, bids,
   feedback capture; trends = 2-series line (fixed categorical slots) + single-hue
   contractor bars; every chart has a table-view twin + tooltips; persistent
   disclaimer strip on every view. Auth: JWT in localStorage, 401 → /login.
   Known polish item: Phase-F precheck `detail` strings are half-English (pipeline
   data, not UI) — largely mitigated in Workstream C (UI prefers `values.justification`,
   which is Thai, for the findings that matter); remaining English details are the
   simple cross-check rows.
3. DONE (Workstream C) — **Phase 3 exit gate MET** (2026-07-17): with the tunnel down
   (0 listeners on :8000, no ssh -N) a scripted headless-Chrome tour (login → overview
   → projects → star drill-down → regulation dialog → citation dialog → feedback post
   → trends) passed 17/17 assertions incl. zero requests to the inference port and
   zero console errors — the dashboard is fully functional with LANTA offline.
   Demo-story dry run: star project = วัดไทร **FY2568** (฿7.794M,
   id dcaf3f14-…); its page carries the whole narrative — yoy precheck FLAG(สูง) with
   Thai justification (748% spike 2567→2568, ส. พงษ์พัฒนา won 2 yrs, ฿3.571M
   cumulative), model reasoning citing the same facts, มาตรา ๓๗ link,
   REQUIRES_INVESTIGATION verdict; trends corroborate (หัวเขา +852.7% FY2568).
   Fix found by the drill: severity/justification live in precheck `values` (pipeline
   convention) — detail page now reads `values.severity` for the (สูง) marker and
   prefers the Thai `values.justification` over the English `detail`. Runbook:
   `docs/runbooks/demo_dashboard.md` (bring-up, 5-min demo script, drill procedure +
   recorded result, open pseudonymization decision). Phase 3 COMPLETE → Phase 4
   (live RAG chatbot through the tunnel).
4. DONE (post-Phase-3 mentor-feedback round, 2026-07-22) — the drill-down's evidence
   display went through two more rounds driven by real feedback, both verified live
   against the real corpus, not just built:
   - **Inline evidence, not blind citations.** Mentor feedback: an auditor had to
     click a generic "อ้างอิง N" button per citation before learning which document or
     what it said — too slow for checking a budget figure. Checked the real data
     first: all 68 real citations across the corpus sit on `RiskFactor.citations`,
     never on individual `reasoning_steps` (verified 0 step-level citations across
     all 20 projects × 5 factors × 3 steps), so the fix landed at the factor level —
     each factor's reasoning now ends with a "หลักฐานเอกสารประกอบปัจจัยนี้" block
     showing the source filename, page, doc type, and a clamped inline excerpt with
     zero clicks required.
   - **Real PDF citation viewer, jumped to the cited page.** Follow-up ask: show the
     actual source PDF, not extracted text. New `GET /api/documents/{id}/file`
     (`backend/app/api/documents.py` + `app/services/storage.py`) streams the object
     straight from MinIO through the app — verified the real bucket stores every
     object as `application/octet-stream` (fput_object's default), so the endpoint
     forces `media_type="application/pdf"` rather than trust stored metadata. MinIO
     stays fully internal; the frontend fetches with the JWT (a plain `<iframe src>`
     can't carry an Authorization header), turns the response into a `blob:` URL, and
     opens it with a `#page=N` fragment — the open-parameter convention Chromium/
     Firefox/Safari's built-in PDF viewers already honor, so no PDF-rendering library
     was needed. `docker-compose.yml` backend service now depends on `minio`
     (service_healthy) and gets `BACKEND_MINIO_ENDPOINT` (bare host:port, mirrors
     `pipelines/common/settings.py`'s `PIPELINES_MINIO_ENDPOINT` convention) +
     `MINIO_ROOT_USER`/`MINIO_ROOT_PASSWORD`/`MINIO_BUCKET_CORPUS`. 3 new backend
     tests incl. a fixture that uploads a real tiny PDF to the corpus bucket and
     round-trips it through the endpoint.
   - **Dialog width bug, not a preference.** "Modal feels small" turned out to be a
     real bug, not a sizing choice: shadcn's base `DialogContent` ships a default
     `sm:max-w-sm` (24rem) that silently beat a plain `max-w-6xl` override in the CSS
     cascade at any viewport ≥640px (`tailwind-merge` only dedupes within the same
     responsive-variant group, so an unprefixed override never collides with the
     base's `sm:`-prefixed one — both ship, and the `sm:` rule wins the cascade).
     Measured with Playwright before/after: 384px → 1152px on a 1440×1100 viewport.
     Fix is to always override with the matching `sm:` prefix; the regulation-text
     dialog had the identical latent bug and got the same fix.
   - **Every project needs a PDF entry point, even with zero citations.** Reported
     against จ้างเหมาซ่อมแซมถนนลูกรัง หมู่ ๑ บ้านเขาคีรี showing no evidence at all.
     Root cause verified against live data: 5 of the 20 real projects have zero
     citations across every factor (the guardrails stage drops any citation the
     model offered that didn't resolve to a real chunk — real Phase-G output, not a
     frontend bug) — but all 20 projects have ≥1 real document attached, and that
     document list wasn't clickable anywhere. Fix: the "เอกสารประกอบ" list is now
     clickable on every project (opens the real PDF, defaults to page 1), and any
     factor with zero citations ends with a labeled fallback pointing at the
     project's real documents instead of showing nothing. Never fabricates a
     citation or a page — only ever opens documents genuinely attached to the
     project. Swept all 20 real projects headlessly after the fix: every one has
     ≥1 clickable PDF entry point, zero console errors project-wide; the star demo
     project's real citations are unaffected (still 7/7 on the original check).
   Commits (branch `feat/phase3-dashboard`): `f5dc363` (inline evidence), `ddf17d7`
   (PDF viewer), `3a350f5` (dialog sizing), `fde8dac` (universal PDF entry point).
   22/22 backend tests, frontend build clean throughout.
5. DONE (item-level anomaly detection, 2026-07-22) — end-to-end unit-price-spike +
   vendor-lock tracking, MVP case: ตำบลหัวเขา 2,000L water tanks (FY67 5 ใบ ฿22,500 →
   FY68 5 ใบ ฿34,000 = **+51.1%/unit, same shop ร้านวีระพร พลาสติก, single bidder both
   years, เฉพาะเจาะจง**; standard ฿7,000/unit → 64.3%→97.1% of ceiling).
   **Evidence chain is 100% documented, nothing invented:** totals/vendor from the two
   born-digital contract summaries (new projects, ingested via the standard flow);
   **quantities (จำนวน ๕ ใบ) from the budget reports** — FY67 รายงานงบ 67 p.12 (OCR'd)
   and FY68 รายงานงบ68 p.10 (born-digital), both already-ingested docs; the ฿7,000
   standard is a **CURATED row** (`pipelines/curated/standard_prices.yaml`, provenance
   recorded, decision: the ราคามาตรฐานครุภัณฑ์ extract is a pure 2-page scan —
   ingested as REFERENCE/NEEDS_OCR per the standing เอกสารกลาง deferral, and the
   curated row cites it at p.2 so the auditor verifies the number in the PDF viewer).
   Pieces: migration **0006** (`project_items` with DB-generated `unit_price` +
   `standard_prices` with provenance CURATED|EXTRACTED); `common/item_extract.py`
   (explicit TRACKED_ITEMS catalog, pipe-table row parsing both digit systems,
   project matching by year+sub-district+exact amount+name pattern — ambiguity is
   skipped, never guessed); `common/item_prechecks.py` (3 findings:
   `unit_price_yoy_spike` ≥30% threshold w/ HIGH escalation on repeat vendor,
   `item_vendor_lock`, `unit_price_vs_standard`; same non-accusatory contract as
   prechecks.py) merged into `extract_structured`'s single idempotent run (item pass
   seeds standards + upserts items + appends findings via the one precheck write
   path; dedup guards against overlapping-chunk double counting — caught live:
   cumulative ฿90,500 from a repeated FY68 line); backend `GET
   /api/dashboard/budget-items` (SQL-window YoY, standards+citations, findings);
   frontend `/budget-items` "สรุปการจัดซื้อ" page (KPI tiles, unit-price columns vs
   dashed standard threshold line, findings list, per-year evidence table whose
   source buttons open the actual PDFs at the cited pages). Bug fixed en route:
   Content-Disposition with a Thai filename 500'd (headers are latin-1) → RFC 5987
   `filename*=UTF-8''…` + ASCII fallback, regression-tested with a Thai filename.
   Corpus layout note: the loose tank PDFs were moved into proper project folders
   (`…/ปี 67 /ซื้อถังน้ำพลาสติก ขนาดความจุ ๒,๐๐๐ ลิตร/ข้อมูลสาระสำคัญในสัญญา.pdf`) so
   walk_corpus classifies them (22 projects now). 13 new pipeline tests (130 total
   pass), 23 backend tests, 17/17 + 7/7 live headless-Chrome checks. NOTE: the two
   tank projects have **no Phase-G risk result yet** (needs a LANTA window; score_risk
   skips already-scored projects, so a plain re-run picks them up) — their pages
   honestly show ยังไม่ผ่านการวิเคราะห์ while all item findings are already visible.
