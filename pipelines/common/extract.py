"""Born-digital PDF extraction seam (Docling per the locked stack).

Docling is an optional dependency group (`uv sync --group parsing`) because it
pulls torch. The flow injects this function, so tests can substitute a fake
extractor without importing Docling at all.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

# Docling emits "<!-- image -->" placeholders for bitmap regions; they are
# markup, not text — an image-only page must read as EMPTY so the garble
# detector routes it to OCR (NO_TEXT_LAYER) instead of "clean".
_MD_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)


@lru_cache(maxsize=1)
def _converter():
    """One converter per process — model loading costs ~20s per instance."""
    try:
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling.document_converter import DocumentConverter, PdfFormatOption
    except ImportError as exc:  # pragma: no cover - environment-dependent
        raise RuntimeError(
            "Docling is not installed. Run `uv sync --group parsing` in pipelines/ "
            "before running document ingestion."
        ) from exc

    # do_ocr=False: Docling's built-in RapidOCR is a Chinese/English model —
    # useless for Thai. Scanned pages must come back EMPTY so the garble
    # detector routes them to Typhoon-OCR on LANTA (the verified Thai path).
    pipeline = PdfPipelineOptions(do_ocr=False)
    return DocumentConverter(
        allowed_formats=[InputFormat.PDF],
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline)},
    )


def extract_pdf_pages(pdf_path: Path) -> list[str]:
    """Extract text per page (index i = 1-based page i+1). Scanned pages come
    back empty/near-empty — the garble detector routes those to OCR."""
    document = _converter().convert(pdf_path).document

    page_numbers = sorted(document.pages.keys())
    pages: list[str] = []
    for page_no in range(1, (page_numbers[-1] if page_numbers else 0) + 1):
        markdown = (
            document.export_to_markdown(page_no=page_no) if page_no in document.pages else ""
        )
        pages.append(_MD_COMMENT.sub("", markdown).strip())
    return pages
