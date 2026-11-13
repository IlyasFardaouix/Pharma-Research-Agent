"""Glossary lookup tool: plain-language definitions of corpus terminology.

Keyword-based (no embeddings), so it is deterministic and works offline. The
GLOSSARY ships with the corpus specifically so terminology is not a barrier; the
agent uses this to ground terms like INR, DOAC, half-life, or 'contraindication'.
Hits are returned as evidence passages so the critic counts a glossary-only answer
as grounded.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from pydantic import BaseModel, Field, field_validator

from app.rag.index import CorpusIndex, Passage
from app.rag.loader import Chunk
from app.tools.base import ToolResult, citation_of, format_passages

DESCRIPTION = (
    "Look up the plain-language definition of a pharmacology term from the glossary "
    "(e.g. 'INR', 'contraindication', 'DOAC', 'half-life'). Use to clarify terminology "
    "before reasoning about it."
)
MIN_TERM_LEN = 2
MAX_HITS = 4


class GlossaryArgs(BaseModel):
    term: str = Field(..., min_length=MIN_TERM_LEN, max_length=120, description="The term to define, e.g. 'INR'.")

    @field_validator("term")
    @classmethod
    def _nonblank(cls, value: str) -> str:
        value = value.strip()
        if len(value) < MIN_TERM_LEN:
            raise ValueError("term must contain at least two non-whitespace characters")
        return value


def _glossary_entries(corpus: CorpusIndex) -> list[tuple[str, Chunk, int | None, int | None, str]]:
    """Return searchable entries with their literal source spans."""
    out: list[tuple[str, Chunk, int | None, int | None, str]] = []
    for c in corpus.chunks:
        if c.source != "glossary":
            continue
        raw_text = c.raw_text if c.raw_text is not None else c.text
        cur: list[str] = []
        start: int | None = None

        def close(end: int) -> None:
            nonlocal cur, start
            if start is None:
                return
            span = raw_text[start:end].rstrip()
            absolute_start = c.start_offset + start if c.start_offset is not None else None
            absolute_end = absolute_start + len(span) if absolute_start is not None else None
            out.append((" ".join(cur), c, absolute_start, absolute_end, span))
            cur, start = [], None

        offset = 0
        for line in raw_text.splitlines(keepends=True):
            line_start = offset
            offset += len(line)
            s = line.strip()
            if s[:2] in ("- ", "* "):
                close(line_start)
                start = line_start + len(line) - len(line.lstrip())
                cur = [s[2:].strip()]
            elif start is not None and s and not s.startswith("#"):
                cur.append(s)
            elif not s or s.startswith("#"):
                close(line_start)
        close(len(raw_text))
    return out


def run(corpus: CorpusIndex, term: str) -> ToolResult:
    needle = (term or "").strip().lower()
    if len(needle) < MIN_TERM_LEN:
        return ToolResult(content="Provide a term of at least 2 characters.")

    matches = [item for item in _glossary_entries(corpus) if needle in item[0].lower()]
    if not matches:
        return ToolResult(content=f"No glossary entry found for '{term}'.")

    # Prefer entries whose bolded headword matches, then shorter entries.
    matches.sort(key=lambda m: (not m[0].lower().startswith(f"**{needle}"), len(m[0])))
    matches = matches[:MAX_HITS]

    passages: list[Passage] = []
    for entry, source_chunk, start, end, raw in matches:
        stable = (f"{Path(source_chunk.file).stem}@{source_chunk.document_sha256[:12]}:{start}-{end}"
                  if source_chunk.document_sha256 and start is not None and end is not None
                  else f"glossary@{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]}")
        chunk = Chunk(
            id=stable,
            file=source_chunk.file,
            drug=None,
            source="glossary",
            section_num=None,
            section_title="Glossary",
            subsection=None,
            text=entry,
            raw_text=raw,
            start_offset=start,
            end_offset=end,
            document_sha256=source_chunk.document_sha256,
        )
        passages.append(Passage(chunk=chunk, score=1.0))

    content = "Glossary:\n" + format_passages(passages)
    citations = [citation_of(p) for p in passages]
    return ToolResult(content=content, passages=passages, citations=citations)
