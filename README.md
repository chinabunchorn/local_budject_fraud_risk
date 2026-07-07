# Mission 3 — Local Budget Fraud Risk & Document Intelligence Assistant

Thai-language AI assistant for government auditors analyzing sub-district project budgets:
a pre-computed **risk dashboard**, risk factor & trend analysis, a **RAG document chatbot**
with citations, regulation linkage (State Fiscal and Financial Discipline Act B.E. 2561),
and auditor feedback sentiment. Prototype scale: 2–3 mock sub-districts, 10–20 projects.

> **Responsible AI — "flag, never accuse."** The system flags risk for human auditors; it
> never states fraud or corruption as a conclusion. Risk verdicts are a closed enum enforced
> at decode time and re-validated before any database write. The human auditor always makes
> the final decision.

## Architecture in one paragraph

The system runs in two planes. A permanently available **Application Zone** (Docker Compose
on a small VM) serves the dashboard from pre-computed, guardrails-validated JSON in
PostgreSQL — it works with **zero** running HPC jobs. An ephemeral **Inference Zone** on the
LANTA supercomputer runs vLLM inside Apptainer under Slurm (24–48 h walltime); offline batch
jobs pre-compute all risk analytics, and only the live chatbot calls real-time inference,
through an SSH tunnel during demonstration windows. When the tunnel is down the chatbot
degrades gracefully — that is designed behavior, not an error.

Full design: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) · build sequence:
[`docs/ROADMAP.md`](docs/ROADMAP.md) · diagrams: [`docs/diagrams/`](docs/diagrams/)

## Repository layout

| Path | Purpose |
|---|---|
| `shared/` | Installable package — **the** data contracts (enum-locked `RiskResult`, `Chunk`, `Citation`, `Feedback`) |
| `backend/` | FastAPI app: auth (JWT/RBAC), dashboard API, SSE chat, LangGraph RAG, guardrails |
| `frontend/` | Next.js 15 dashboard + chat UI (Thai-first) |
| `pipelines/` | Prefect 3 offline batch flows + versioned Thai prompt templates |
| `hpc/` | Everything that runs on LANTA: Apptainer def, Slurm scripts, tunnel/staging helpers |
| `infra/db/` | Alembic migrations + init SQL (pgvector extension) |
| `docs/` | Architecture, roadmap, diagrams, ops runbooks |
| `data/` | `regulations/` (versioned) and `mock_corpus/` (gitignored; canonical copy in MinIO) |

## Quick start (app zone)

```bash
# 1. Configure secrets
cp .env.example .env         # then edit every change-me value

# 2. Bring up the app-zone stack
docker compose up -d         # traefik, postgres+pgvector, redis, minio, clickhouse,
                             # langfuse v3, TEI (bge-m3 + reranker)
docker compose ps            # wait until services report healthy

# 3. Install the shared contracts package + run its tests
cd shared && uv sync && uv run pytest

# 4. Apply database migrations
cd ../infra/db && DATABASE_URL=postgresql+psycopg://mission3:...@localhost:5432/mission3 \
  uv run alembic upgrade head
```

First TEI start downloads model weights (~minutes); Langfuse needs ClickHouse healthy
before it reports ready.

## LANTA (inference zone)

See `hpc/` — Apptainer definition, Slurm job scripts, weight staging, and the autossh
tunnel script, with placeholders for your LANTA account/partition/paths. Phase 1 of the
roadmap executes these manually first; Prefect automation comes later. Compute nodes are
air-gapped: **all weights and packages are pre-staged to Lustre from the transfer node.**

## Ground rules (see `CLAUDE.md` for the full list)

- `shared/schemas` is the single source of truth for the risk-result contract.
- The only write path into `risk_results` is the guardrails validation stage.
- Every LLM call goes through the vLLM client service and is traced to Langfuse.
- Trend analytics are plain SQL — no LLM in that path.
- Thai is the primary language; UTF-8 everywhere; PyThaiNLP for segmentation.
- Secrets only via environment variables; model weights are never committed.
