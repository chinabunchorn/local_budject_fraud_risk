"""Thai-aware chunking for the pgvector `chunks` table.

Page text is packed line-by-line into chunks of roughly TARGET_CHARS, with a
one-line overlap between consecutive chunks of the same page for retrieval
continuity. Lines longer than MAX_CHARS (dense paragraphs) are split at
PyThaiNLP word boundaries — never mid-word, which would poison embeddings.

Chunks never span pages: `page` is citation metadata (`schemas.Citation`), and
a chunk crossing pages could not be cited precisely.
"""

from __future__ import annotations

from dataclasses import dataclass

from pythainlp.tokenize import word_tokenize

TARGET_CHARS = 800  # comfortable for BGE-M3; well under the TEI truncation cap
MAX_CHARS = 1200


@dataclass(frozen=True)
class ChunkDraft:
    """Pre-embedding chunk; `chunk_index` is assigned document-wide, 0-based."""

    chunk_index: int
    text: str
    page: int | None


def _split_long_line(line: str, limit: int) -> list[str]:
    pieces: list[str] = []
    current = ""
    for token in word_tokenize(line, engine="newmm", keep_whitespace=True):
        if current and len(current) + len(token) > limit:
            pieces.append(current)
            current = token.lstrip()
        else:
            current += token
    if current.strip():
        pieces.append(current)
    return [p for p in (piece.strip() for piece in pieces) if p]


def _pack_lines(lines: list[str], target: int, overlap_lines: int) -> list[str]:
    chunks: list[str] = []
    buffer: list[str] = []
    size = 0
    for line in lines:
        if buffer and size + len(line) > target:
            chunks.append("\n".join(buffer))
            buffer = buffer[-overlap_lines:] if overlap_lines else []
            size = sum(len(kept) for kept in buffer)
        buffer.append(line)
        size += len(line)
    if buffer:
        chunk = "\n".join(buffer)
        # avoid a tail chunk that is nothing but the overlap of the previous one
        if not chunks or chunk != "\n".join(chunks[-1].splitlines()[-len(buffer) :]):
            chunks.append(chunk)
    return chunks


def chunk_pages(
    pages: list[str],
    target_chars: int = TARGET_CHARS,
    max_chars: int = MAX_CHARS,
    overlap_lines: int = 1,
) -> list[ChunkDraft]:
    """`pages[i]` is the extracted text of 1-based page i+1; blank pages skip."""
    drafts: list[ChunkDraft] = []
    for page_no, page_text in enumerate(pages, start=1):
        lines: list[str] = []
        for raw in page_text.splitlines():
            line = raw.strip()
            if not line:
                continue
            if len(line) > max_chars:
                lines.extend(_split_long_line(line, target_chars))
            else:
                lines.append(line)
        for text in _pack_lines(lines, target_chars, overlap_lines):
            drafts.append(ChunkDraft(chunk_index=len(drafts), text=text, page=page_no))
    return drafts
