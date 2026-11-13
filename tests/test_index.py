"""InMemoryIndex cosine search is correct with injected vectors (no network)."""

import numpy as np

from app.rag.index import InMemoryIndex
from app.rag.loader import Chunk


def _chunk(i: int, drug: str) -> Chunk:
    return Chunk(
        id=f"c{i}", file=f"{drug}.md", drug=drug, source="dailymed",
        section_num=None, section_title="S", subsection=None, text=f"text {i}",
    )


def _unit(vec) -> np.ndarray:
    v = np.asarray(vec, dtype=np.float32)
    return v / np.linalg.norm(v)


def test_search_ranks_by_cosine():
    chunks = [_chunk(0, "a"), _chunk(1, "b"), _chunk(2, "c")]
    matrix = np.stack([_unit([1, 0]), _unit([0, 1]), _unit([1, 1])])
    index = InMemoryIndex(chunks, matrix)

    hits = index.search(_unit([1, 0]), k=3)
    assert hits[0].chunk.id == "c0"           # exact match ranks first
    assert hits[0].score > hits[1].score      # sorted descending


def test_predicate_filter():
    chunks = [_chunk(0, "a"), _chunk(1, "b")]
    matrix = np.stack([_unit([1, 0]), _unit([1, 0])])
    index = InMemoryIndex(chunks, matrix)

    hits = index.search(_unit([1, 0]), k=5, predicate=lambda c: c.drug == "b")
    assert len(hits) == 1
    assert hits[0].chunk.drug == "b"


def test_k_larger_than_corpus():
    chunks = [_chunk(0, "a")]
    index = InMemoryIndex(chunks, np.stack([_unit([1, 0])]))
    assert len(index.search(_unit([1, 0]), k=50)) == 1


def test_predicate_matches_nothing():
    chunks = [_chunk(0, "a")]
    index = InMemoryIndex(chunks, np.stack([_unit([1, 0])]))
    assert index.search(_unit([1, 0]), k=5, predicate=lambda c: False) == []
