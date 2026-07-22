#!/usr/bin/env python
"""Typhoon-OCR batch driver for LANTA — Tier-1 optimized merge (2026-07-13).

This file is the canonical version: the real-data-verified pieces of the
originally deployed script (extraction prompt, 200dpi+LANCZOS rendering,
chat-template invocation, max_new_tokens=2000) merged with the Tier-1
mechanics (page-level resume, explicit bf16+SDPA, torch.inference_mode,
atomic writes, per-page failure isolation, lazy per-page rendering).

Contract (unchanged): every *.pdf directly in documents/ →
ocr_results/<pdf-stem>/page_<n>.md (n = 1-based page number, UTF-8).
Runs in the `hf` mamba env on one A100 — plain transformers, NOT vLLM.
"""

import os
import sys
import time

os.environ["HF_HUB_OFFLINE"] = "1"  # compute nodes are air-gapped

import glob

import fitz  # PyMuPDF
import torch
from PIL import Image

model_path = "/project/tn999991-cstu/chin/models/typhoon-ocr1.5-2b"
input_dir = "/project/tn999991-cstu/chin/documents"
output_dir = "/project/tn999991-cstu/chin/ocr_results"
os.makedirs(output_dir, exist_ok=True)

# --- verified extraction prompt — DO NOT EDIT without re-running the
# --- acceptance test (thashang67.pdf) and reviewing output quality
prompt = """Extract all text from the image.

Instructions:
- Only return the clean Markdown.
- Do not include any explanation or extra text.
- You must include all information on the page.

Formatting Rules:
- Tables: Render tables using <table>...</table> in clean HTML format.
- Page Numbers: Wrap page numbers in <page_number>...</page_number>."""

MAX_NEW_TOKENS = 2000  # as deployed & verified; dense pages truncate here


def resize_if_needed(img, max_size=1800):
    width, height = img.size
    if width > 300 or height > 300:
        if width >= height:
            scale = max_size / float(width)
            new_size = (max_size, int(height * scale))
        else:
            scale = max_size / float(height)
            new_size = (int(width * scale), max_size)
        img = img.resize(new_size, Image.Resampling.LANCZOS)
    return img


def render_page(doc, page_index, dpi=200):
    """Render ONE page lazily (a 280-page book must not be rasterized into
    RAM upfront, and resumed runs must not render already-done pages)."""
    zoom = dpi / 72
    pix = doc[page_index].get_pixmap(matrix=fitz.Matrix(zoom, zoom))
    return Image.frombytes("RGB", [pix.width, pix.height], pix.samples)


def page_path(stem, page_no):
    return os.path.join(output_dir, stem, f"page_{page_no}.md")


def page_done(stem, page_no):
    """Tier 1: page-level resume — non-empty page_<n>.md counts as done."""
    path = page_path(stem, page_no)
    return os.path.isfile(path) and os.path.getsize(path) > 0


def pending_pages(pdf_path, stem):
    with fitz.open(pdf_path) as doc:
        n_pages = len(doc)
    return n_pages, [n for n in range(1, n_pages + 1) if not page_done(stem, n)]


def atomic_write(path, text):
    """Never leave a partial page_<n>.md a resumed run would wrongly skip."""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


# --- Figure out what actually needs work BEFORE loading the model ---
# (so a re-submit with nothing new exits fast without ever touching the GPU)
pdf_files = sorted(glob.glob(os.path.join(input_dir, "*.pdf")))
print(f"Found {len(pdf_files)} PDF(s) in {input_dir}")

to_process = []
for pdf_path in pdf_files:
    stem = os.path.splitext(os.path.basename(pdf_path))[0]
    n_pages, pending = pending_pages(pdf_path, stem)
    if not pending:
        print(f"SKIP {stem}: already has {n_pages}/{n_pages} pages, nothing to do")
    else:
        to_process.append((pdf_path, stem, n_pages, pending))

if not to_process:
    print("Nothing new to process. Exiting.")
    sys.exit(0)

total_pending = sum(len(p) for _, _, _, p in to_process)
print(f"{len(to_process)} document(s), {total_pending} page(s) need processing. Loading model...")

from transformers import AutoModelForImageTextToText, AutoProcessor

# Tier 1: explicit bf16 + SDPA (dtype="auto" resolved to bf16 anyway; pinned
# so a config change can never silently flip us to fp32)
model = AutoModelForImageTextToText.from_pretrained(
    model_path,
    torch_dtype=torch.bfloat16,
    attn_implementation="sdpa",
    device_map="auto",
).eval()
processor = AutoProcessor.from_pretrained(model_path)


def run_ocr(img):
    img = resize_if_needed(img.convert("RGB"))
    messages = [{"role": "user", "content": [{"type": "image", "image": img}, {"type": "text", "text": prompt}]}]
    inputs = processor.apply_chat_template(
        messages, tokenize=True, add_generation_prompt=True, return_dict=True, return_tensors="pt"
    ).to(model.device)
    generated_ids = model.generate(**inputs, max_new_tokens=MAX_NEW_TOKENS)
    trimmed = [out[len(inp):] for inp, out in zip(inputs.input_ids, generated_ids)]
    return processor.batch_decode(trimmed, skip_special_tokens=True)[0]


failures = []
with torch.inference_mode():  # Tier 1
    for pdf_path, stem, n_pages, pending in to_process:
        os.makedirs(os.path.join(output_dir, stem), exist_ok=True)
        print(f"Processing {stem}: {len(pending)}/{n_pages} page(s) pending...", flush=True)
        doc_failed = False
        with fitz.open(pdf_path) as doc:
            for page_no in pending:
                started = time.monotonic()
                try:
                    text = run_ocr(render_page(doc, page_no - 1))
                    atomic_write(page_path(stem, page_no), text)
                    print(
                        f"  [{stem}] page {page_no}/{n_pages} ok "
                        f"chars={len(text)} {time.monotonic() - started:.1f}s",
                        flush=True,
                    )
                except Exception as e:  # per-page isolation: keep going
                    doc_failed = True
                    print(
                        f"  [{stem}] page {page_no}/{n_pages} FAILED {type(e).__name__}: {e}",
                        file=sys.stderr,
                        flush=True,
                    )
        if doc_failed:
            failures.append(stem)
        else:
            print(f"  [{stem}] done.")

if failures:
    print(f"Batch OCR finished with {len(failures)} failure(s): {failures}", file=sys.stderr)
    sys.exit(1)

print("Batch OCR complete, all documents succeeded.")
