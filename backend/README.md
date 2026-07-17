# Mission 3 backend — Phase 3 read API

FastAPI service over pre-computed, guardrails-validated risk data in PostgreSQL.
**Offline-first:** every endpoint here reads the database only — no LLM call exists on
any code path in this app (the Phase 4 chatbot will be the only live-inference feature).

## Endpoints (all under `/api`, JWT bearer auth except login/health)

| Endpoint | Purpose |
|---|---|
| `POST /auth/login`, `GET /auth/me` | JWT login (roles: ADMIN / SENIOR_AUDITOR / AUDITOR) |
| `GET /dashboard/overview` | Portfolio totals, risk distribution, sub-district × year heatmap, top-risk list (Redis-cached) |
| `GET /dashboard/trends` | YoY budget by sub-district + contractor concentration — plain SQL window functions (Redis-cached) |
| `GET /projects` | Filter by `fiscal_year` / `sub_district_id` / `risk_level` / `q`; sorted severity-first |
| `GET /projects/{id}` | Drill-down: procurement facts, bids, all 8 precheck findings, full validated `RiskResult` |
| `GET/POST /projects/{id}/feedback` | Auditor feedback capture (sentiment filled later by the batch flow) |
| `GET /chunks/{chunk_id}` | Citation → source-passage resolution (one-click verify) |
| `GET /regulations/{code}` | Regulation section text (codes contain `/`) |

Every risk-bearing response carries `disclaimer_th` — flags, never conclusions; the
human auditor decides.

## Run locally (against the compose stack, from `backend/`)

```bash
uv sync
set -a; source ../.env; set +a
export DATABASE_URL="${DATABASE_URL/postgres:5432/localhost:5432}"
uv run uvicorn app.main:app --port 8080 --reload
```

Redis isn't published to the host, so local caching silently degrades to direct DB
reads — designed behavior. In compose (`docker compose up -d backend`, image built from
the repo root so `../shared` resolves) caching is active; on this dev Mac reach the API
on the published port `:8080` (the Traefik docker provider doesn't work here — see
memory/compose notes).

## Users

```bash
SEED_PASSWORD=... uv run python scripts/seed_users.py <username> <ROLE> --display-name "ชื่อ"
```

## Tests

House convention: DB-backed tests run against the live compose PostgreSQL with
throwaway rows and skip cleanly when the stack is down. Requires migration 0005.

```bash
uv run pytest -q
```
