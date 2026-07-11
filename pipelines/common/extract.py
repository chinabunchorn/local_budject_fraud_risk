"""Born-digital PDF extraction seam (Docling per the locked stack).

Docling is an optional dependency group (`uv sync --group parsing`) because it
pulls torch. The flow injects this function, so tests can substitute a fake
extractor without importing Docling at all.
"""

from __future__ import annotations

from pathlib import Path


def extract_pdf_pages(pdf_path: Path) -> list[str]:
    """Extract text per page (index i = 1-based page i+1). Scanned pages come
    back empty/near-empty — the garble detector routes those to OCR."""
    try:
        from docling.datamodel.base_models import InputFormat
        from docling.document_converter import DocumentConverter
    except ImportError as exc:  # pragma: no cover - environment-dependent
        raise RuntimeError(
            "Docling is not installed. Run `uv sync --group parsing` in pipelines/ "
            "before running document ingestion."
        ) from exc

    converter = DocumentConverter(allowed_formats=[InputFormat.PDF])
    document = converter.convert(pdf_path).document

    page_numbers = sorted(document.pages.keys())
    pages: list[str] = []
    for page_no in range(1, (page_numbers[-1] if page_numbers else 0) + 1):
        pages.append(
            document.export_to_markdown(page_no=page_no) if page_no in document.pages else ""
        )
    return pages
