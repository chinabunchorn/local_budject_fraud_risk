# OCR Throughput Plan — fixing `batch_ocr.py` on LANTA (July 2026)

> Context: pass 1 of ingestion queued **28 PDFs / 649 pages** (18 project+budget
> docs = 168 pages; 10 เอกสารกลาง reference books = 481 pages, one ~280 pages of
> dense tables). The deployed driver (plain `transformers`
> `AutoModelForImageTextToText`, sequential pages, `hf` mamba env, 1× A100) is
> stuck on the dense-table book. `slurm/ocr_batch.sbatch` walltime is 10:30 h.
> App-side contract is unchanged: `documents/*.pdf` in →
> `ocr_results/<pdf-stem>/page_<n>.md` out (stems are now sha-prefixed, e.g.
> `a1b2c3d4e5f6_TOR.pdf` — the driver needs no change for that).

## Why it's slow (do the math before optimizing)

- HF `generate()` = batch size 1, one page at a time. A dense table page emits
  2,000–4,000 markdown tokens → ~1.5–3 min/page on transformers.
- 649 pages × 1.5–3 min ≈ **16–32 h > 10:30 walltime** → the job dies mid-book,
  and stem-level resume restarts big books from page 1 → they can never finish.
- Dense tables are the model's degenerate case: repetition loops burn tokens.
  If `max_new_tokens` is large/unset, one page can run for a very long time —
  that is the "stuck" symptom. Verify: Slurm log's last page + `nvidia-smi`
  (steady util = looping, not hung).

## Step 0 — triage NOW, no code (do this before anything else)

1. `scancel` the wedged job.
2. Move the 10 reference books out of `documents/` (e.g. `documents/deferred/`
   — the driver only globs `*.pdf` at the top level). Resubmit so the
   **18 project/budget docs (168 pages) finish first** — they are the product;
   the books are Phase-F reference material. Even at current speed 168 pages
   fits the walltime.
3. Fetch those results (`hpc_io.ocr_batch fetch`) so app-side pass 2 can run —
   the demo path unblocks today, independent of the big books.

## Tier 1 — same stack, ~1 hour of edits to `batch_ocr.py` (do these regardless)

Ordered by impact:

1. **Page-level resume**: before OCRing page n, skip if
   `ocr_results/<stem>/page_<n>.md` exists and is non-empty. Killed jobs then
   resume where they died — walltime stops being fatal. (Keep the existing
   whole-stem fast-path.)
2. **Cap generation**: `max_new_tokens≈3000`, `repetition_penalty≈1.1` (or the
   values the Typhoon-OCR docs recommend), `do_sample=False`. A degenerate page
   now costs a bounded ~2 min, writes whatever it got, and is flagged (see 5).
3. **bf16 + fast attention**: load with `torch_dtype=torch.bfloat16` and
   `attn_implementation="sdpa"`, wrap the loop in `torch.inference_mode()`.
   (If the current load is fp32 default, this alone is ~2×.)
4. **Smallest-first ordering**: sort PDFs by page count ascending — many small
   docs complete and land before any big book starts (mirrors the app-side fix).
5. **Per-page failure sidecar**: on cap-hit or exception, still write the page
   (possibly truncated) plus a `page_<n>.FLAGGED` marker line in the Slurm log
   and a `flagged.json` in the stem dir — pass 2 ingests the text; humans see
   the flag list.
6. Optional if VRAM allows (2B model on 40 GB — it will): **micro-batch 4–8
   page images per `generate()` call** → roughly linear speedup. Watch padded
   batch shapes; keep it simple (chunk pages of one document).

Expected effect: ~10–25 s/page → 649 pages ≈ 2.5–4.5 h → fits one walltime.

## Tier 2 — vLLM offline batch (the real fix; the recorded trigger has fired)

`hpc/LANTA_CONFIG_NOTES.md` recorded: keep transformers "until OCR throughput
or env maintenance forces a change" — throughput now has. vLLM's continuous
batching on the A100 turns this into ~2–5 s/page (well under 1 h for 649 pages).

Design that avoids dependency surgery (PyMuPDF is NOT in the vLLM container;
compute nodes can't pip install):

- **Stage 1 (hf mamba env):** render every pending page to
  `render_cache/<stem>/page_<n>.png` (~1800px long edge, existing fitz code).
- **Stage 2 (Apptainer `vllm-v0110.sif`, the three required flags:**
  `--cleanenv --env PYTHONNOUSERSITE=1 --bind /project/tn999991-cstu/chin:...`**):**
  one Python script using `vllm.LLM(model=.../typhoon-ocr1.5-2b,
  dtype="bfloat16", max_model_len=<per docs>, limit_mm_per_prompt={"image": 1})`
  and `llm.chat([...])` over ALL pending pages with
  `SamplingParams(temperature=0, max_tokens≈3000, repetition_penalty≈1.1)`;
  write each result to `ocr_results/<stem>/page_<n>.md`.
- Both stages in one sbatch; page-level resume applies to both (skip rendered
  PNGs / existing MDs).

**Gate (non-negotiable, per the verified-reality rule):** this combination
(vLLM offline + Qwen3-VL + rendered pages) has never been tested here. Before
trusting it, re-run the acceptance checklist from the OCR brief — especially
`thashang67.pdf` (33-page scan) with output diffed against the transformers
version for quality parity (tables, baht figures). If quality regresses, stay
on Tier 1.

## Reference books — do they even need full OCR now?

The 481 book pages serve (a) Phase-F rate lookups — which need only specific
tables (labor rates, Factor F, unit prices), and (b) nice-to-have RAG context.
Option: keep them in `documents/deferred/` until Tier 2 lands, or OCR only the
books actually used by the prechecks (บัญชีค่าแรงงาน, อัตราราคางานต่อหน่วย)
first. Nothing downstream blocks on them today.

## Measure, don't guess

Add one log line per page: `stem page n/N tokens=X seconds=Y`. Benchmark any
change against the same 33-page thashang67 before/after. Target: full 649-page
backlog inside a single 10:30 walltime (Tier 1) / inside ~1 h (Tier 2).

## After it works

Copy the updated `batch_ocr.py` (and any Tier-2 script) back into `hpc/slurm/`
in the repo, and update `hpc/LANTA_CONFIG_NOTES.md` — including flipping the
transformers-vs-vLLM decision record if Tier 2 is adopted.
