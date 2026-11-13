"""Reassemble complete source contexts for evidence, leaving indexed chunks intact.

Embedding-sized fragments are retrieval locators, not safe quotation boundaries.
Only contiguous, matching fragments from the trusted loaded corpus can form a
context. No separators, normalization, truncation or new embeddings are used.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import re
from typing import TYPE_CHECKING

from app.rag.loader import Chunk

if TYPE_CHECKING:
    from app.rag.index import Passage


DEFAULT_MAX_CONTEXT_CHARS = 60000


class EvidenceContextError(ValueError):
    """A complete source context cannot safely be returned as evidence."""


def _context_key(chunk: Chunk) -> tuple[str, int, int] | None:
    start = getattr(chunk, "context_start_offset", None)
    end = getattr(chunk, "context_end_offset", None)
    if start is None and end is None:
        return None
    if type(start) is not int or type(end) is not int or start < 0 or end <= start:
        raise EvidenceContextError(f"Invalid complete-context bounds in {chunk.file}.")
    return chunk.file, start, end


def _identity(chunk: Chunk) -> tuple:
    return (chunk.drug, chunk.source, chunk.section_num, chunk.section_title,
            chunk.subsection, chunk.product, chunk.product_id)


def _assemble(selected: Chunk, fragments: list[Chunk], bounds: tuple[str, int, int],
              max_context_chars: int) -> Chunk:
    file, start, end = bounds
    if end - start > max_context_chars:
        raise EvidenceContextError(
            f"Complete context in {file} has {end - start} characters, exceeding the "
            f"{max_context_chars}-character evidence limit; no partial context was returned.")
    if not fragments:
        raise EvidenceContextError(f"Complete context is missing from the loaded corpus: {file}.")
    digest = selected.document_sha256
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise EvidenceContextError(f"Complete context has no valid document SHA-256: {file}.")
    identity = _identity(selected)
    for fragment in fragments:
        if fragment.document_sha256 != digest:
            raise EvidenceContextError(f"Conflicting document SHA-256 values in complete context: {file}.")
        if _identity(fragment) != identity:
            raise EvidenceContextError(f"Conflicting source, heading or product in complete context: {file}.")
        a, b = fragment.start_offset, fragment.end_offset
        raw = fragment.raw_text
        if (type(a) is not int or type(b) is not int or a < start or b > end or b <= a
                or not isinstance(raw, str) or len(raw) != b - a):
            raise EvidenceContextError(f"Invalid source fragment bounds or exact text in {file}.")
        expected_id = f"{Path(file).stem}@{digest[:12]}:{a}-{b}"
        if fragment.id != expected_id:
            raise EvidenceContextError(f"Source fragment ID does not match its SHA-256 and offsets in {file}.")
    fragments = sorted(fragments, key=lambda c: c.start_offset)
    cursor = start
    parts = []
    for fragment in fragments:
        if fragment.start_offset != cursor:
            raise EvidenceContextError(
                f"Complete context in {file} has a missing or overlapping fragment at offset {cursor}; "
                "no partial context was returned.")
        parts.append(fragment.raw_text)
        cursor = fragment.end_offset
    if cursor != end:
        raise EvidenceContextError(
            f"Complete context in {file} is missing its final fragment at offset {cursor}; "
            "no partial context was returned.")
    raw = "".join(parts)
    stable_id = f"{Path(file).stem}@{digest[:12]}:{start}-{end}"
    # Accept an original indexed fragment or a previously expanded context only
    # when its text and canonical provenance match the trusted source fragments.
    a, b = selected.start_offset, selected.end_offset
    if (type(a) is not int or type(b) is not int or a < start or b > end or b <= a
            or selected.raw_text != raw[a - start:b - start]
            or selected.id != f"{Path(file).stem}@{digest[:12]}:{a}-{b}"):
        raise EvidenceContextError(f"Retrieved evidence does not match its complete source context in {file}.")
    first = fragments[0]
    prefix = first.text[:-len(first.raw_text)] if first.text.endswith(first.raw_text) else ""
    return replace(first, id=stable_id, text=prefix + raw, raw_text=raw,
                   start_offset=start, end_offset=end)


def expand_context_passages(passages: list[Passage], corpus_chunks: list[Chunk], *,
                            max_context_chars: int = DEFAULT_MAX_CONTEXT_CHARS) -> list[Passage]:
    """Return deduplicated complete contexts, ranked by their best hit score.

    Chunks without context bounds are already complete evidence (e.g. glossary
    lookup entries or legacy test fixtures) and retain their exact identity/text.
    A failure rejects the entire batch rather than exposing a partial batch.
    """
    from app.rag.index import Passage

    if type(max_context_chars) is not int or max_context_chars <= 0:
        raise EvidenceContextError("The complete-context evidence limit must be a positive integer.")
    if not passages:
        return []
    requested = {_context_key(p.chunk) for p in passages}
    requested.discard(None)
    groups: dict[tuple, list[Chunk]] = {key: [] for key in requested}
    for chunk in corpus_chunks:
        # Only examine the contexts actually requested; a corrupt unrelated
        # context must not interfere with a valid independent lookup.
        key = (chunk.file, getattr(chunk, "context_start_offset", None),
               getattr(chunk, "context_end_offset", None))
        if key in groups:
            groups[key].append(chunk)
    best: dict[tuple, tuple[int, Passage]] = {}
    assembled: dict[tuple, Chunk] = {}
    for position, passage in enumerate(passages):
        key = _context_key(passage.chunk)
        if key is None:
            identity = ("complete", passage.chunk.file, passage.chunk.id)
            if len(passage.chunk.raw_text or passage.chunk.text) > max_context_chars:
                raise EvidenceContextError(
                    f"Complete evidence in {passage.chunk.file} exceeds the {max_context_chars}-character "
                    "evidence limit; no partial context was returned.")
            chunk = passage.chunk
        else:
            identity = ("context", *key)
            # Validate every hit, including duplicate-context hits, against the
            # trusted fragments. Reuse only the resulting immutable source text.
            chunk = _assemble(passage.chunk, groups[key], key, max_context_chars)
            assembled.setdefault(key, chunk)
            chunk = assembled[key]
        previous = best.get(identity)
        if previous is None:
            best[identity] = position, Passage(chunk=chunk, score=passage.score)
        elif passage.score > previous[1].score:
            best[identity] = previous[0], Passage(chunk=chunk, score=passage.score)
    return [p for _, p in sorted(best.values(), key=lambda item: (-item[1].score, item[0]))]
