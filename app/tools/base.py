"""Shared primitives for tools.

A tool returns a :class:`ToolResult`: a string for the LLM (the ``ToolMessage``
content) plus the structured passages/citations we keep in agent state so the
critic can check grounding and the final answer can cite sources.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.models import Citation
from app.rag.index import Passage

MAX_PASSAGE_CHARS = None


@dataclass
class ToolResult:
    content: str
    passages: list[Passage] = field(default_factory=list)
    citations: list[Citation] = field(default_factory=list)


def citation_of(passage: Passage) -> Citation:
    c = passage.chunk
    return Citation(file=c.file, drug=c.drug, source=c.source, section=c.heading,
                    passage_id=c.id, excerpt=c.raw_text if c.raw_text is not None else c.text,
                    product=c.product, product_id=c.product_id,
                    document_sha256=c.document_sha256,
                    start_offset=c.start_offset, end_offset=c.end_offset)


def format_passages(passages: list[Passage], max_chars: int | None = MAX_PASSAGE_CHARS) -> str:
    """Render complete evidence; retain the old argument for caller compatibility."""
    if not passages:
        return "No matching passages found."
    blocks = []
    for i, p in enumerate(passages, 1):
        c = p.chunk
        text = c.raw_text if c.raw_text is not None else c.text
        product = f" · {c.product}" if c.product else ""
        blocks.append(f"[passage_id={c.id}] ({c.file} · {c.heading}{product}) score={p.score:.2f}\n{text}")
    return "\n\n".join(blocks)
