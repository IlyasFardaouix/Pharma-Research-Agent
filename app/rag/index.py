"""In-memory similarity index + the corpus "brain" the tools call into.

``InMemoryIndex`` is pure NumPy (no network, trivially unit-testable).
``CorpusIndex`` ties loader + embeddings + index together and exposes the three
operations the agent's tools need: semantic search, structured section lookup,
and a corpus inventory.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from app.config import Settings
from app.rag.context import DEFAULT_MAX_CONTEXT_CHARS, expand_context_passages
from app.rag.embeddings import Embedder, load_or_build_embeddings
from app.rag.loader import Chunk, get_section_chunks, list_drugs, load_corpus, normalize_drug


@dataclass
class Passage:
    """A search hit: a chunk plus its similarity score."""

    chunk: Chunk
    score: float


class InMemoryIndex:
    """Cosine-similarity search over a fixed matrix of normalised vectors."""

    def __init__(self, chunks: list[Chunk], matrix: np.ndarray):
        if matrix.ndim != 2 or matrix.shape[1] == 0:
            raise ValueError("matrix must be 2-D with nonzero embedding dimension")
        if len(chunks) != matrix.shape[0]:
            raise ValueError("chunks and matrix length mismatch")
        if not np.isfinite(matrix).all():
            raise ValueError("matrix contains non-finite values")
        if not np.allclose(np.linalg.norm(matrix, axis=1), 1.0, rtol=1e-4, atol=1e-4):
            raise ValueError("matrix vectors must have unit norm")
        self.chunks = chunks
        self.matrix = matrix

    def search(
        self,
        query_vector: np.ndarray,
        k: int,
        predicate: Callable[[Chunk], bool] | None = None,
    ) -> list[Passage]:
        if query_vector.ndim != 1 or query_vector.shape[0] != self.matrix.shape[1]:
            raise ValueError("query embedding dimension mismatch")
        if not np.isfinite(query_vector).all() or not np.isclose(np.linalg.norm(query_vector), 1.0, rtol=1e-4, atol=1e-4):
            raise ValueError("query vector must be finite and unit length")
        scores = self.matrix @ query_vector  # vectors are pre-normalised
        if predicate is not None:
            mask = np.array([predicate(c) for c in self.chunks], dtype=bool)
            if not mask.any():
                return []
            scores = np.where(mask, scores, -np.inf)
        k = min(k, int(np.isfinite(scores).sum()))
        if k <= 0:
            return []
        top = np.argpartition(-scores, k - 1)[:k]
        top = top[np.argsort(-scores[top])]
        return [Passage(chunk=self.chunks[i], score=float(scores[i])) for i in top]


class CorpusIndex:
    """Loaded corpus + embeddings, with the operations the tools expose."""

    def __init__(self, chunks: list[Chunk], matrix: np.ndarray, embedder: Embedder, settings: Settings):
        self.chunks = chunks
        self.index = InMemoryIndex(chunks, matrix)
        self.embedder = embedder
        self.settings = settings

    # -- construction -------------------------------------------------------
    @classmethod
    def build(cls, settings: Settings) -> "CorpusIndex":
        chunks = load_corpus(settings.corpus_dir)
        embedder = Embedder(settings)
        matrix = load_or_build_embeddings([c.text for c in chunks], settings, embedder)
        return cls(chunks, matrix, embedder, settings)

    # -- operations used by tools ------------------------------------------
    def search_text(
        self,
        query: str,
        k: int | None = None,
        drug: str | None = None,
        source: str | None = None,
    ) -> list[Passage]:
        k = max(1, min(k or self.settings.top_k, 12))
        qvec = self.embedder.embed_query(query)
        drug_n = normalize_drug(drug) if drug else None

        def predicate(c: Chunk) -> bool:
            if drug_n and c.drug != drug_n:
                return False
            if source and c.source != source:
                return False
            return True

        has_filter = bool(drug_n or source)
        hits = self.index.search(qvec, k, predicate if has_filter else None)
        return expand_context_passages(hits, self.chunks, max_context_chars=getattr(
            self.settings, "max_evidence_chars", DEFAULT_MAX_CONTEXT_CHARS))

    def get_section_passages(self, drug: str, section: str, source: str = "dailymed",
                             product_id: str | None = None, allow_fallback: bool = False) -> list[Passage]:
        chunks = get_section_chunks(self.chunks, drug, section, source, product_id, allow_fallback)
        return expand_context_passages([Passage(chunk=c, score=1.0) for c in chunks],
            self.chunks, max_context_chars=getattr(getattr(self, "settings", None),
                "max_evidence_chars", DEFAULT_MAX_CONTEXT_CHARS))

    def drugs(self) -> dict[str, list[str]]:
        return list_drugs(self.chunks)

    # -- introspection ------------------------------------------------------
    @property
    def num_chunks(self) -> int:
        return len(self.chunks)

    @property
    def num_files(self) -> int:
        return len({c.file for c in self.chunks})
