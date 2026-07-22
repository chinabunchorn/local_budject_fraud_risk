# Runbook — Phase 3 dashboard demo & offline exit gate

The dashboard is **offline-first**: every view reads pre-computed,
guardrails-validated data from PostgreSQL. **LANTA is not involved** — no Slurm
job, no tunnel, no live inference. This runbook is the demo script and the
recorded exit-gate drill.

## Bring-up (app zone only)

```bash
docker compose up -d                       # postgres, redis, backend, …
cd infra/db  && DATABASE_URL=… uv run alembic upgrade head   # once per schema change
cd backend   && SEED_PASSWORD=… uv run python scripts/seed_users.py <user> AUDITOR --display-name "ชื่อ"
cd frontend  && npm run build && npm run start               # http://localhost:3001
```

Dev-Mac gotchas: reach the API on the published port `:8080` (the Traefik
docker provider does not work on the dev Mac — label routes 404; validate
Traefik routing on the amd64 app VM). Langfuse owns `:3000`; the dashboard runs
on `:3001`.

## Demo narrative — the วัดไทร story (one flow, ~5 minutes)

Star project: **โครงการก่อสร้างถนน คสล. หมู่ ๔ บ้านวัดไทร ปีงบประมาณ 2568**
(ตำบลหัวเขา, ฿7.794M).

1. **ภาพรวม** — point at the risk distribution (15 ปานกลาง / 4 ควรตรวจสอบเพิ่มเติม /
   1 ต่ำ) and the heatmap; the entire top-risk list is the วัดไทร cluster.
2. **โครงการ** — search "วัดไทร": the same road recurs in 2566, 2567, 2568,
   all flagged ควรตรวจสอบเพิ่มเติม.
3. **Drill-down FY2568** — the story lands on one page:
   - precheck **งบประมาณโครงการต่อเนื่องรายปี → พบข้อสังเกต (สูง)** with the
     factual Thai justification: recurring project 3 years, budget spike **748%**
     (2567→2568), same contractor (ส. พงษ์พัฒนา 27) won 2 years, ฿3.571M cumulative;
   - the model's **ความเบี่ยงเบนงบประมาณ / การกระจุกตัวของผู้รับจ้าง** reasoning
     chains (หลักฐาน → ข้อสังเกต → การตีความ) cite the same facts — click **อ้างอิง**
     to open the source passage from the real contract summary;
   - **ข้อกฎหมายที่เกี่ยวข้อง** → อ่านบทบัญญัติ opens พ.ร.บ.วินัยการเงินการคลังฯ มาตรา ๓๗;
   - verdict badge **ควรตรวจสอบเพิ่มเติม** — computed by code from factor scores +
     the HIGH-severity precheck, never the model's free choice;
   - record a note in **บันทึกของผู้ตรวจสอบ**.
4. **แนวโน้ม** — the budget line corroborates the spike (ตำบลหัวเขา **+852.7%**
   into FY2568) and the concentration bars show ส. พงษ์พัฒนา's repeat wins.
5. Close on the persistent disclaimer: the system flags; **the auditor decides**.

## Exit-gate drill (ROADMAP Phase 3: "demo with all Slurm jobs killed")

Procedure — run with the tunnel down and no LANTA job:

1. Verify no live-inference path: `lsof -nP -iTCP:8000 -sTCP:LISTEN` → empty;
   no `ssh -N` process.
2. Run the scripted tour (headless Chrome, playwright-core against system
   Chrome): login → overview → projects filter → star drill-down → regulation
   dialog → citation dialog → feedback post → trends table twin.
3. Gate: every page renders, **zero requests to port 8000, zero console/page
   errors**.

**Recorded result — 2026-07-17 (dev Mac):** tunnel down (0 listeners on :8000),
**17/17 checks passed**, including the two exit-gate assertions. The dashboard
is fully functional with LANTA completely offline — Phase 3 exit gate **met**.

## Open item before any external demo

**Pseudonymization decision (corpus decision, ROADMAP):** the dashboard shows
real sub-district, village, and contractor names attached to risk flags. The
documents are public-procurement records, but before demoing outside the team,
decide whether demo copy pseudonymizes entity names (a display-name mapping at
the API layer would be the clean insertion point). Not yet decided.
