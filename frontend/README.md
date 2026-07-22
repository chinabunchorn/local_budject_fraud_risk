# Mission 3 frontend — Phase 3 dashboard

Next.js 15 dashboard over the Phase 3 read API. **Offline-first**: every view reads
pre-computed, guardrails-validated data — no LLM call happens anywhere in this app.

Formal executive UI: white surfaces, corporate-blue accents (validated dataviz
palette in `lib/viz.ts`), Sarabun, hairline borders, no decorative animation.
Every risk-bearing view carries the persistent disclaimer — flags, never
conclusions; the human auditor decides.

## Pages

- `/login` — JWT login (users seeded via `backend/scripts/seed_users.py`)
- `/` — portfolio overview: KPI tiles, risk distribution (status colors + labels),
  sub-district × year heatmap (sequential blue), top-risk table
- `/projects` — filterable list (year / sub-district / risk level / search)
- `/projects/[id]` — drill-down: validated RiskResult verbatim, per-factor
  reasoning chain (evidence → observation → interpretation) with citation dialogs
  resolving to source passages, regulation viewer, 8 precheck findings, bids,
  documents, auditor feedback capture
- `/trends` — SQL-only analytics: YoY budget lines per sub-district, contractor
  concentration bars; every chart ships a table-view twin

## Run (against the compose backend on :8080)

```bash
npm install
npm run dev        # http://localhost:3001 (Langfuse holds :3000)
```

`NEXT_PUBLIC_API_BASE` overrides the API origin (default `http://localhost:8080/api`).

## Visual verification

`npm run build` must pass. For screenshots, drive the real app with headless
Chrome via playwright-core (dev dep, uses system Chrome — no browser download).
