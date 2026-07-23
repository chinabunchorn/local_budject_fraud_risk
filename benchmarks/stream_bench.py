"""Streaming optimization benchmark — the "how we optimized" presentation piece.

Replays the scripted Thai auditor questions against the live `/api/chat` SSE
endpoint under two named configs (baseline vs optimized), parses the per-request
`telemetry` events, aggregates p50/p95 for each metric, and renders a
self-contained baseline-vs-optimized comparison report (HTML: small-multiple
panels per metric + a table twin) plus the raw JSON.

The two levers A/B'd here are the ones the backend exposes per request
(`rerank_top_n`, `max_tokens`) — fewer reranked passages = fewer prefill tokens
= lower TTFT; a tighter `max_tokens` = shorter tail. Client-level levers
(keep-alive, streaming vs non-streaming) are measured separately and noted in
the runbook.

Usage:
  # against a live backend (needs a JWT):
  uv run --project ../backend python stream_bench.py \
      --base-url http://localhost:8080 --username admin --password ... --repeat 3

  # offline, synthetic data — just proves the report renders:
  uv run --project ../backend python stream_bench.py --selftest
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import httpx
import yaml

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"

# (telemetry key, Thai label, unit, direction) — direction says which way is good.
METRICS = [
    ("ttft_raw_ms", "TTFT (โมเดล+ทันเนล)", "ms", "lower"),
    ("ttft_display_ms", "TTFT (ที่ผู้ใช้เห็น)", "ms", "lower"),
    ("queue_wait_ms", "เวลารอคิว (vLLM)", "ms", "lower"),
    ("decode_tokens_per_sec", "ความเร็วสร้างคำตอบ", "tok/s", "higher"),
    ("e2e_ms", "เวลารวมทั้งคำขอ", "ms", "lower"),
]

# The two levers the backend exposes per request.
DEFAULT_CONFIGS = {
    "baseline": {"rerank_top_n": 12, "max_tokens": 1024},
    "optimized": {"rerank_top_n": 6, "max_tokens": 768},
}


@dataclass
class ConfigResult:
    name: str
    params: dict
    runs: list[dict] = field(default_factory=list)  # telemetry dicts

    def agg(self) -> dict[str, dict[str, float | None]]:
        out: dict[str, dict[str, float | None]] = {}
        for key, _, _, _ in METRICS:
            vals = [
                float(r[key])
                for r in self.runs
                if r.get(key) is not None
            ]
            out[key] = {
                "p50": round(statistics.median(vals), 1) if vals else None,
                "p95": round(_p95(vals), 1) if vals else None,
                "n": len(vals),
            }
        return out


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(0, min(len(ordered) - 1, round(0.95 * (len(ordered) - 1))))
    return ordered[rank]


# ---- live run -----------------------------------------------------------------


def login(base_url: str, username: str, password: str) -> str:
    resp = httpx.post(
        f"{base_url}/api/auth/login",
        json={"username": username, "password": password},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def ask(base_url: str, token: str, question: str, params: dict) -> dict | None:
    """POST one question; return its telemetry dict (with client e2e added)."""
    body = {"question": question, **params}
    started = time.perf_counter()
    telemetry: dict | None = None
    event = None
    with httpx.Client(timeout=180) as client:
        with client.stream(
            "POST",
            f"{base_url}/api/chat",
            json=body,
            headers={"Authorization": f"Bearer {token}"},
        ) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if line.startswith("event:"):
                    event = line[len("event:") :].strip()
                elif line.startswith("data:") and event == "telemetry":
                    telemetry = json.loads(line[len("data:") :].strip())
    if telemetry is not None:
        telemetry["client_e2e_ms"] = round((time.perf_counter() - started) * 1000, 1)
    return telemetry


def run_live(args) -> list[ConfigResult]:
    questions = yaml.safe_load((HERE / args.questions).read_text())["questions"]
    token = args.token or login(args.base_url, args.username, args.password)
    results = []
    for name, params in DEFAULT_CONFIGS.items():
        cfg = ConfigResult(name=name, params=params)
        for _ in range(args.repeat):
            for q in questions:
                tel = ask(args.base_url, token, q, params)
                if tel and not tel.get("degraded"):
                    cfg.runs.append(tel)
                    print(
                        f"[{name}] ttft={tel.get('ttft_raw_ms')}ms "
                        f"q={tel.get('queue_wait_ms')}ms "
                        f"tps={tel.get('decode_tokens_per_sec')}"
                    )
        results.append(cfg)
    return results


def run_selftest() -> list[ConfigResult]:
    """Synthetic telemetry so the report can be verified without a backend."""
    rng = random.Random(7)

    def sample(base: dict) -> dict:
        return {k: round(v * rng.uniform(0.85, 1.15), 1) for k, v in base.items()}

    baseline_mean = {
        "ttft_raw_ms": 520, "ttft_display_ms": 640, "queue_wait_ms": 95,
        "decode_tokens_per_sec": 41, "e2e_ms": 4200,
    }
    optimized_mean = {
        "ttft_raw_ms": 310, "ttft_display_ms": 380, "queue_wait_ms": 45,
        "decode_tokens_per_sec": 47, "e2e_ms": 2600,
    }
    out = []
    for name, mean in [("baseline", baseline_mean), ("optimized", optimized_mean)]:
        cfg = ConfigResult(name=name, params=DEFAULT_CONFIGS[name])
        cfg.runs = [sample(mean) for _ in range(30)]
        out.append(cfg)
    return out


# ---- report -------------------------------------------------------------------

# Okabe-Ito accessible pair (published CVD-safe): baseline blue / optimized orange.
_BASELINE = "#0072B2"
_OPTIMIZED = "#E69F00"


def _improvement(baseline: float | None, optimized: float | None, better: str) -> str:
    if not baseline or optimized is None:
        return "—"
    pct = (optimized - baseline) / baseline * 100
    gain = -pct if better == "lower" else pct
    arrow = "▲" if gain > 0 else "▼"
    return f"{arrow} {abs(gain):.0f}%"


def render_html(results: list[ConfigResult], meta: dict) -> str:
    aggs = {c.name: c.agg() for c in results}
    base_a = aggs.get("baseline", {})
    opt_a = aggs.get("optimized", {})

    panels = []
    for key, label, unit, better in METRICS:
        b = (base_a.get(key) or {}).get("p50")
        o = (opt_a.get(key) or {}).get("p50")
        vals = [v for v in (b, o) if v is not None] or [1]
        vmax = max(vals) * 1.15
        b_w = (b / vmax * 100) if b else 0
        o_w = (o / vmax * 100) if o else 0
        imp = _improvement(b, o, better)
        panels.append(f"""
      <div class="panel">
        <div class="phead"><span>{label}</span><span class="imp {('pos' if '▲' in imp else 'neg' if '▼' in imp else '')}">{imp}</span></div>
        <div class="bar"><div class="fill base" style="width:{b_w:.1f}%"></div>
          <span class="val">{'' if b is None else f'{b:g}'} <em>{unit}</em></span></div>
        <div class="bar"><div class="fill opt" style="width:{o_w:.1f}%"></div>
          <span class="val">{'' if o is None else f'{o:g}'} <em>{unit}</em></span></div>
        <div class="hint">{'สูงกว่าดีกว่า' if better=='higher' else 'ต่ำกว่าดีกว่า'} · แสดงค่ามัธยฐาน (p50)</div>
      </div>""")

    rows = []
    for key, label, unit, _ in METRICS:
        b = base_a.get(key) or {}
        o = opt_a.get(key) or {}
        rows.append(
            f"<tr><td>{label}</td>"
            f"<td>{_fmt(b.get('p50'))}</td><td>{_fmt(b.get('p95'))}</td>"
            f"<td>{_fmt(o.get('p50'))}</td><td>{_fmt(o.get('p95'))}</td>"
            f"<td><small>{unit}</small></td></tr>"
        )

    return _HTML_TEMPLATE.format(
        panels="".join(panels),
        rows="".join(rows),
        base_params=json.dumps(DEFAULT_CONFIGS["baseline"], ensure_ascii=False),
        opt_params=json.dumps(DEFAULT_CONFIGS["optimized"], ensure_ascii=False),
        n_base=len(results[0].runs) if results else 0,
        n_opt=len(results[1].runs) if len(results) > 1 else 0,
        generated=meta.get("generated", ""),
        source=meta.get("source", ""),
        base_color=_BASELINE,
        opt_color=_OPTIMIZED,
        data_json=json.dumps(
            {c.name: {"params": c.params, "agg": c.agg()} for c in results},
            ensure_ascii=False,
        ),
    )


def _fmt(v: float | None) -> str:
    return "—" if v is None else f"{v:g}"


_HTML_TEMPLATE = """<!doctype html>
<html lang="th"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Phase 4 — Streaming Optimization</title>
<style>
  :root {{ --bg:#ffffff; --surface:#f7f8fa; --ink:#1a1f2b; --muted:#5b6472;
           --line:#e4e7ec; --base:{base_color}; --opt:{opt_color}; }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --bg:#0f1420; --surface:#171d2b; --ink:#e8ecf3; --muted:#9aa4b5;
             --line:#28303f; }} }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--ink);
    font-family:"Sarabun","Segoe UI",system-ui,sans-serif; line-height:1.5; }}
  .wrap {{ max-width:980px; margin:0 auto; padding:32px 20px 64px; }}
  h1 {{ font-size:22px; margin:0 0 4px; }}
  .sub {{ color:var(--muted); font-size:13px; margin-bottom:20px; }}
  .legend {{ display:flex; gap:18px; align-items:center; margin:14px 0 24px;
    font-size:13px; color:var(--muted); }}
  .chip {{ display:inline-flex; align-items:center; gap:7px; }}
  .sw {{ width:12px; height:12px; border-radius:3px; display:inline-block; }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(280px,1fr));
    gap:14px; }}
  .panel {{ background:var(--surface); border:1px solid var(--line);
    border-radius:12px; padding:16px 16px 12px; }}
  .phead {{ display:flex; justify-content:space-between; align-items:baseline;
    font-weight:600; font-size:14px; margin-bottom:12px; }}
  .imp {{ font-size:13px; font-weight:700; }}
  .imp.pos {{ color:#2e8b57; }} .imp.neg {{ color:#c0392b; }}
  .bar {{ position:relative; height:26px; margin:5px 0; background:transparent; }}
  .fill {{ height:100%; border-radius:0 5px 5px 0; min-width:2px; }}
  .fill.base {{ background:var(--base); }} .fill.opt {{ background:var(--opt); }}
  .val {{ position:absolute; top:50%; transform:translateY(-50%); left:10px;
    font-size:12.5px; color:#fff; font-weight:600; text-shadow:0 1px 2px rgba(0,0,0,.35); }}
  .val em {{ font-style:normal; opacity:.85; font-weight:400; }}
  .hint {{ color:var(--muted); font-size:11.5px; margin-top:6px; }}
  table {{ width:100%; border-collapse:collapse; margin-top:28px; font-size:13px; }}
  th, td {{ text-align:right; padding:8px 10px; border-bottom:1px solid var(--line); }}
  th:first-child, td:first-child {{ text-align:left; }}
  thead th {{ color:var(--muted); font-weight:600; }}
  caption {{ text-align:left; color:var(--muted); font-size:12px; margin-bottom:8px; }}
  .note {{ color:var(--muted); font-size:12px; margin-top:22px; }}
</style></head>
<body><div class="wrap">
  <h1>Phase 4 — การเพิ่มประสิทธิภาพการสตรีมคำตอบ</h1>
  <div class="sub">เปรียบเทียบ baseline กับ optimized · สร้างเมื่อ {generated} · แหล่งข้อมูล: {source}</div>
  <div class="legend">
    <span class="chip"><span class="sw" style="background:var(--base)"></span>
      baseline <code>{base_params}</code> (n={n_base})</span>
    <span class="chip"><span class="sw" style="background:var(--opt)"></span>
      optimized <code>{opt_params}</code> (n={n_opt})</span>
  </div>
  <div class="grid">{panels}</div>
  <table>
    <caption>ตารางข้อมูล (p50 / p95 ต่อค่าเมตริก)</caption>
    <thead><tr><th>เมตริก</th>
      <th>base p50</th><th>base p95</th>
      <th>opt p50</th><th>opt p95</th><th>หน่วย</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
  <p class="note">TTFT (ที่ผู้ใช้เห็น) รวมเวลาบัฟเฟอร์ของการตรวจถ้อยคำทีละประโยค (sentence-gating)
    จึงสูงกว่า TTFT ดิบเสมอ — แสดงไว้อย่างตรงไปตรงมา ตัวเลขจริงมาจากช่วงสาธิตบน LANTA</p>
  <script type="application/json" id="bench-data">{data_json}</script>
</div></body></html>
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost:8080")
    ap.add_argument("--token", default=None)
    ap.add_argument("--username", default=None)
    ap.add_argument("--password", default=None)
    ap.add_argument("--questions", default="questions.yaml")
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        results = run_selftest()
        source = "selftest (synthetic)"
    else:
        results = run_live(args)
        source = args.base_url

    RESULTS.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    meta = {"generated": datetime.now().strftime("%Y-%m-%d %H:%M"), "source": source}

    (RESULTS / f"{stamp}.json").write_text(
        json.dumps(
            {c.name: {"params": c.params, "agg": c.agg(), "runs": c.runs}
             for c in results},
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )
    html_path = RESULTS / f"{stamp}.html"
    html_path.write_text(render_html(results, meta), encoding="utf-8")
    print(f"\nwrote {html_path}")


if __name__ == "__main__":
    main()
