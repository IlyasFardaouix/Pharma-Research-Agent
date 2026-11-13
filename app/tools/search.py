"""Semantic search tool: embedding similarity over the whole corpus."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from app.rag.index import CorpusIndex
from app.rag.context import DEFAULT_MAX_CONTEXT_CHARS, EvidenceContextError, expand_context_passages
from app.tools.base import ToolResult, citation_of, format_passages

DESCRIPTION = (
    "Semantic search over the pharmacology corpus. Use for open-ended questions, "
    "symptoms, mechanisms, or when you do not know which labelled section holds the "
    "answer. Optionally restrict to one drug. Returns the top matching passages with "
    "their source file and section."
)


class SearchArgs(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000, description="Natural-language search query.")
    k: int | None = Field(
        None, ge=1, le=12, description="Passages to return (defaults to the server's top_k)."
    )
    drug: str | None = Field(
        None, max_length=120, description="Optional drug name to restrict the search, e.g. 'warfarin'."
    )

    @field_validator("query", "drug")
    @classmethod
    def _nonblank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("search text must not be blank")
        return value


def run(corpus: CorpusIndex, query: str, k: int | None = None, drug: str | None = None) -> ToolResult:
    try:
        candidates = corpus.search_text(query, k=k, drug=drug)
    except EvidenceContextError as exc:
        return ToolResult(content=f"Complete source evidence unavailable: {exc} Choose another section or narrow the request.")
    passages = [p for p in candidates if p.score >= corpus.settings.min_relevance]
    if candidates and not passages:
        return ToolResult(content="No passages met the configured relevance threshold. "
            "No evidence or citations are available from this search. Try a narrower query or abstain.")
    # Production CorpusIndex already expands contexts. This also protects
    # corpus facades whose search method exposes original indexed fragments.
    if hasattr(corpus, "chunks"):
        try:
            passages = expand_context_passages(passages, corpus.chunks,
                max_context_chars=getattr(corpus.settings, "max_evidence_chars", DEFAULT_MAX_CONTEXT_CHARS))
        except EvidenceContextError as exc:
            return ToolResult(content=f"Complete source evidence unavailable: {exc} Choose another section or narrow the request.")
    content = format_passages(passages)
    return ToolResult(
        content=content,
        passages=passages,
        citations=[citation_of(p) for p in passages],
    )
