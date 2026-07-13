#!/usr/bin/env python
"""Typhoon-OCR batch driver for LANTA — Tier-1 optimized (2026-07-13).

Contract (unchanged, see hpc/OCR_BATCH_BRIEF history + LANTA_CONFIG_NOTES.md):
    input : every *.pdf directly in  /project/tn999991-cstu/chin/documents/
    output: /project/tn999991-cstu/chin/ocr_results/<pdf-stem>/page_<n>.md
            (n = 1-based PDF page number, UTF-8 markdown)

Runs in the `hf` mamba env (Python 3.11) on one A100 — plain transformers,
NOT vLLM, NOT Apptainer (the real-data-verified path).

Tier-1 changes vs. the original:
  1. PAGE-level resume: a page whose page_<n>.md exists non-empty is skipped,
     so a walltime-killed job resumes where it died. The whole-stem fast path
     (skip complete documents BEFORE model load) is preserved.
  2. bf16 + SDPA attention at model load.
  3. All processing under torch.inference_mode().
  4. Atomic page writes (tmp file + os.replace) — a kill mid-write can never
     leave a corrupt/partial page_<n>.md that resume would wrongly skip.
"""

from __future__ import annotations

import io
import json
import re
import sys
import time
from pathlib import Path

import fitz  # PyMuPDF
import torch
from PIL import Image

BASE = Path("/project/tn999991-cstu/chin")
DOCUMENTS_DIR = BASE / "documents"
RESULTS_DIR = BASE / "ocr_results"
MODEL_PATH = BASE / "models" / "typhoon-ocr1.5-2b"

TARGET_LONG_EDGE = 1800  # matches the model's training resolution

# NOTE: deliberately NOT lowered per Tier-1 scope. If dense-table pages loop,
# the next knob is max_new_tokens≈3000 + repetition_penalty≈1.1 (plan Tier 1.2).
MAX_NEW_TOKENS = 16384

# ---------------------------------------------------------------------------
# KEEP-YOURS: this must be the EXACT extraction prompt from the deployed,
# real-data-verified batch_ocr.py — the model is task-specific and quality
# depends on it. The string below is the documented Typhoon-OCR default task
# prompt; diff against the working version before replacing anything.
# ---------------------------------------------------------------------------
PROMPT = (
    "Below is an image of a document page. Simply return the markdown "
    "representation of this document, presenting tables in markdown format "
    "as they naturally appear.\n"
    "If the document contains images, use a placeholder like dummy.png for "
    "each image.\n"
    "Your final output must be in JSON format with a single key `natural_text` "
    "containing the response.\n"
    "RETURN ONLY JSON. Do not explain."
)

_JSON_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def render_page(page: fitz.Page) -> Image.Image:
    """Render one PDF page to a PIL image, TARGET_LONG_EDGE px on the long side."""
    rect = page.rect
    zoom = TARGET_LONG_EDGE / max(rect.width, rect.height)
    pixmap = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
    return Image.open(io.BytesIO(pixmap.tobytes("png"))).convert("RGB")


def page_path(stem: str, page_no: int) -> Path:
    return RESULTS_DIR / stem / f"page_{page_no}.md"


def page_done(stem: str, page_no: int) -> bool:
    path = page_path(stem, page_no)
    return path.exists() and path.stat().st_size > 0


def pending_pages(pdf_path: Path) -> list[int]:
    """1-based page numbers still needing OCR (page-level resume)."""
    with fitz.open(pdf_path) as doc:
        total = doc.page_count
    return [n for n in range(1, total + 1) if not page_done(pdf_path.stem, n)]


def atomic_write(path: Path, text: str) -> None:
    """Never leave a partial page_<n>.md: write sibling tmp, then rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def parse_natural_text(raw: str) -> str:
    """The model answers JSON {"natural_text": ...}; fall back to raw output."""
    cleaned = _JSON_FENCE.sub("", raw.strip())
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict) and isinstance(parsed.get("natural_text"), str):
            return parsed["natural_text"]
    except json.JSONDecodeError:
        pass
    return raw.strip()


def load_model():
    """Tier 1: bf16 + SDPA. Loaded ONCE, and only when there is pending work."""
    from transformers import AutoModelForImageTextToText, AutoProcessor

    processor = AutoProcessor.from_pretrained(MODEL_PATH)
    model = AutoModelForImageTextToText.from_pretrained(
        MODEL_PATH,
        torch_dtype=torch.bfloat16,
        attn_implementation="sdpa",
        device_map="cuda",
    ).eval()
    return model, processor


def ocr_image(model, processor, image: Image.Image) -> str:
    # -----------------------------------------------------------------------
    # KEEP-YOURS: if the deployed script builds inputs / calls generate()
    # differently, keep the deployed invocation — it is the verified one.
    # Only the load-time kwargs (bf16/sdpa) and inference_mode are Tier 1.
    # -----------------------------------------------------------------------
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image", "image": image},
                {"type": "text", "text": PROMPT},
            ],
        }
    ]
    inputs = processor.apply_chat_template(
        messages,
        add_generation_prompt=True,
        tokenize=True,
        return_dict=True,
        return_tensors="pt",
    ).to(model.device)
    generated = model.generate(
        **inputs, max_new_tokens=MAX_NEW_TOKENS, do_sample=False
    )
    answer = generated[:, inputs["input_ids"].shape[1] :]
    return processor.batch_decode(answer, skip_special_tokens=True)[0]


def process_document(model, processor, pdf_path: Path, pages: list[int]) -> bool:
    """OCR the pending pages of one PDF. Returns True if every page succeeded."""
    stem = pdf_path.stem
    ok = True
    with fitz.open(pdf_path) as doc:
        total = doc.page_count
        for page_no in pages:
            started = time.monotonic()
            try:
                image = render_page(doc[page_no - 1])
                text = parse_natural_text(ocr_image(model, processor, image))
                atomic_write(page_path(stem, page_no), text)
                print(
                    f"[{stem}] page {page_no}/{total} ok "
                    f"chars={len(text)} {time.monotonic() - started:.1f}s",
                    flush=True,
                )
            except Exception as exc:  # noqa: BLE001 — isolate failures per page
                ok = False
                print(
                    f"[{stem}] page {page_no}/{total} FAILED "
                    f"{type(exc).__name__}: {exc}",
                    flush=True,
                )
    return ok


def main() -> int:
    pdfs = sorted(p for p in DOCUMENTS_DIR.glob("*.pdf") if p.is_file())
    if not pdfs:
        print("No PDFs in documents/. Exiting.")
        return 0

    # Whole-stem fast path + page-level resume, all BEFORE any model load:
    # a no-op run must exit in seconds without touching the GPU.
    work: list[tuple[Path, list[int]]] = []
    for pdf in pdfs:
        pages = pending_pages(pdf)
        if pages:
            work.append((pdf, pages))
        else:
            with fitz.open(pdf) as doc:
                total = doc.page_count
            print(f"SKIP {pdf.stem}: already has {total}/{total} pages, nothing to do")

    if not work:
        print("Nothing new to process. Exiting.")
        return 0

    total_pages = sum(len(pages) for _, pages in work)
    print(f"{len(work)} document(s), {total_pages} page(s) pending. Loading model...")
    model, processor = load_model()

    failed_docs: list[str] = []
    with torch.inference_mode():
        for pdf, pages in work:
            print(f"[{pdf.stem}] {len(pages)} pending page(s)", flush=True)
            if not process_document(model, processor, pdf, pages):
                failed_docs.append(pdf.name)

    if failed_docs:
        print(f"FAILED documents ({len(failed_docs)}): {failed_docs}")
        return 1
    print("All pending pages completed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
