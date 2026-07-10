# CLAUDE.md — Mission 3: Local Budget Fraud Risk & Document Intelligence Assistant

Thai-language AI assistant for government auditors analyzing sub-district project budgets.
Features: pre-computed risk dashboard, risk factor & trend analysis, RAG document chatbot with
citations, regulation linkage (State Fiscal and Financial Discipline Act B.E. 2561), auditor
feedback sentiment. Prototype scale: 2–3 mock sub-districts, 10–20 projects.

Full design: `docs/ARCHITECTURE.md`. Build sequence: `docs/ROADMAP.md`. Diagrams: `docs/diagrams/`.
Read all three before scaffolding or making architectural decisions.

## Non-negotiable constraints

1. **LANTA HPC lifecycle.** All LLM inference runs in vLLM inside an Apptainer container under
   Slurm on the LANTA supercomputer. Compute nodes are air-gapped (no internet) and jobs are
   killed at 24–48 h walltime. Never write code that assumes a permanent endpoint inside LANTA,
   and never fetch models/packages at runtime on compute nodes — everything is pre-staged to
   Lustre from the transfer node.
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
   the human auditor makes the final decision.
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
- **Parsing:** Docling (born-digital) + Typhoon-OCR 1.5 via vLLM (scanned/garbled) + PyThaiNLP
- **Models:** `scb10x/typhoon2.5-qwen3-30b-a3b` (primary, all roles initially);
  `Qwen/Qwen3-32B` AWQ-INT4 (batch analyst — add ONLY if Phase-2 quality evals justify it);
  `scb10x/typhoon-ocr1.5-2b` (OCR). A100 40GB = Ampere: use BF16 or AWQ/GPTQ-INT4, never FP8/GGUF.
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
    ├── mock_corpus/            # gitignored; canonical copy lives in MinIO
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

## Current status & first tasks (see docs/ROADMAP.md — we are at Phase 0 → 1)

1. Scaffold the repository layout above; init git; write `.env.example` and `README.md`.
2. `docker-compose.yml` for the app zone (traefik, postgres+pgvector, redis, minio, langfuse,
   tei with BGE-M3) with healthchecks; verify `docker compose up -d` comes up clean.
3. Implement `shared/schemas` — the enum-locked `RiskResult` Pydantic contract — WITH tests.
   This contract gates everything downstream; do it before any pipeline code.
4. Alembic setup + initial migration: sub_districts, projects, budget_lines, documents, chunks
   (vector), regulations, risk_results (JSONB), auditor_feedback.
5. `hpc/` skeleton: `vllm.def`, `serve_vllm.sbatch`, `batch_infer.sbatch`, `stage_weights.sh`,
   `tunnel.sh` — with clearly marked placeholders for LANTA account/partition/paths (Phase 1 is
   executed manually on LANTA first, then automated via Prefect).
6. Do not start Phase 2 pipeline flows until items 3–4 are merged and tested.
