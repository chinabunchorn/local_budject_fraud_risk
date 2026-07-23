"""Chat prompt assembly — versioned Thai templates, never inline strings.

The templates live beside the backend (`prompts/chat/<version>/`) because the
live chatbot is a backend feature, mirroring how the batch scorer keeps its
templates in `pipelines/prompts/`; both follow the same rule (CLAUDE.md) that
Thai prompt text is a versioned file, not a literal in code.

Retrieved passages are clamped before assembly: shorter context = fewer prefill
tokens = lower TTFT, one of the measured Phase-4 optimization levers.
"""

from __future__ import annotations

from pathlib import Path

from app.rag.retrieval import RetrievedContext

_PROMPTS = Path(__file__).resolve().parent / "prompts" / "chat"
CHAT_PROMPT_VERSION = "v1"

# Per-passage character clamp; the head of a chunk carries its retrieval signal.
_CONTEXT_CLAMP = 700


def _load(version: str, name: str) -> str:
    return (_PROMPTS / version / name).read_text(encoding="utf-8").strip()


def build_context_block(contexts: list[RetrievedContext]) -> str:
    """The labeled `[C#]` evidence block the model cites from."""
    blocks = []
    for c in contexts:
        body = c.text.strip()
        if len(body) > _CONTEXT_CLAMP:
            body = body[:_CONTEXT_CLAMP].rstrip() + "…"
        blocks.append(f"[C{c.label}] ({c.source_label_th})\n{body}")
    return "\n\n".join(blocks)


def build_messages(
    question: str,
    history: list[dict[str, str]],
    contexts: list[RetrievedContext],
    *,
    version: str = CHAT_PROMPT_VERSION,
) -> list[dict[str, str]]:
    """Assemble system + prior turns + the context-carrying user turn."""
    system = _load(version, "system.md")
    user_template = _load(version, "user.md")
    user = user_template.format(
        context=build_context_block(contexts) or "(ไม่มีบริบท)",
        question=question.strip(),
    )
    messages: list[dict[str, str]] = [{"role": "system", "content": system}]
    messages.extend(history)
    messages.append({"role": "user", "content": user})
    return messages
