"""Embeddings via an OpenAI-compatible endpoint, with an on-disk cache.

Embedding the whole corpus on every container start would be slow and burn tokens.
We cache the matrix by model, endpoint, corpus, version and requested dimensions.
A warm cache avoids re-embedding the corpus; when dimensions are not configured,
one short provider probe checks compatibility before accepting cached vectors.
Vectors are L2-normalised so cosine similarity reduces to a dot product.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
import threading
import time
from pathlib import Path

import numpy as np
from langchain_openai import OpenAIEmbeddings

from app.execution import current_budget
from app.config import Settings

_BATCH = 128
_CACHE_LOCKS: dict[Path, threading.Lock] = {}
_CACHE_LOCKS_GUARD = threading.Lock()
_CACHE_RETRIES = 8
_CACHE_RETRY_DELAY = 0.05


def _l2_normalize(matrix: np.ndarray) -> np.ndarray:
    if matrix.ndim != 2 or not matrix.shape[0] or not matrix.shape[1]:
        raise ValueError("embedding matrix must be a nonempty 2-D array")
    if not np.isfinite(matrix).all():
        raise ValueError("embedding matrix contains non-finite values")
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    if not np.isfinite(norms).all() or np.any(norms == 0):
        raise ValueError("embedding matrix contains zero or invalid vectors")
    return matrix / norms


def _valid_matrix(matrix: np.ndarray, rows: int, dimensions: int | None = None) -> bool:
    if matrix.ndim != 2 or matrix.shape[0] != rows or matrix.shape[1] == 0:
        return False
    if dimensions is not None and matrix.shape[1] != dimensions:
        return False
    if not np.issubdtype(matrix.dtype, np.floating) or not np.isfinite(matrix).all():
        return False
    return bool(np.allclose(np.linalg.norm(matrix, axis=1), 1.0, rtol=1e-4, atol=1e-4))


def _cache_lock(path: Path) -> threading.Lock:
    with _CACHE_LOCKS_GUARD:
        return _CACHE_LOCKS.setdefault(path, threading.Lock())


def _read_cache(path: Path, rows: int, dimensions: int | None = None) -> np.ndarray | None:
    """Read atomically published cache, retrying transient Windows sharing locks."""
    for attempt in range(_CACHE_RETRIES):
        try:
            with np.load(path) as data:
                matrix = data["matrix"]
            return matrix if _valid_matrix(matrix, rows, dimensions) else None
        except FileNotFoundError:
            return None
        except PermissionError:
            if attempt == _CACHE_RETRIES - 1:
                raise
            time.sleep(_CACHE_RETRY_DELAY)
        except Exception:
            # A corrupt or incompatible cache is rebuilt from the corpus.
            return None
    return None


class Embedder:
    """Thin wrapper over ``OpenAIEmbeddings`` returning normalised numpy arrays."""

    def __init__(self, settings: Settings):
        self.model = settings.openai_embedding_model
        self.request_timeout = settings.request_timeout
        self._client = OpenAIEmbeddings(
            model=settings.openai_embedding_model,
            api_key=settings.openai_api_key or "missing",
            base_url=settings.openai_base_url or None,
            timeout=settings.request_timeout,
            max_retries=0,
            dimensions=settings.embedding_dimensions,
            # Send raw strings (not tiktoken token-ID arrays). Avoids a tiktoken
            # download at runtime (keeps the image self-contained / offline-safe) and
            # avoids proxies that reject token arrays.
            check_embedding_ctx_length=False,
        )

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), _BATCH):
            batch = texts[start:start + _BATCH]
            budget = current_budget.get()
            timeout = min(self.request_timeout, budget.check()) if budget else self.request_timeout
            vectors.extend(self._client.embed_documents(batch, timeout=timeout))
            if budget:
                budget.check()
        return _l2_normalize(np.asarray(vectors, dtype=np.float32))

    def embed_query(self, text: str) -> np.ndarray:
        budget = current_budget.get()
        timeout = min(self.request_timeout, budget.check()) if budget else self.request_timeout
        vec = np.asarray(self._client.embed_query(text, timeout=timeout), dtype=np.float32)
        if budget:
            budget.check()
        return _l2_normalize(vec[None, :])[0]


def _cache_key(model: str, base_url: str | None, texts: list[str],
               version: str = "v1", dimensions: int | None = None) -> str:
    h = hashlib.sha256()
    h.update(version.encode("utf-8"))
    h.update(b"\x00")
    h.update(str(dimensions).encode("ascii"))
    h.update(b"\x00")
    h.update(model.encode("utf-8"))
    h.update(b"\x00")
    h.update((base_url or "").encode("utf-8"))
    h.update(b"\x00")
    for t in texts:
        h.update(t.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()[:16]


def load_or_build_embeddings(
    texts: list[str],
    settings: Settings,
    embedder: Embedder,
) -> np.ndarray:
    """Return the (N, D) normalised embedding matrix, from cache when possible."""
    settings.cache_dir.mkdir(parents=True, exist_ok=True)
    version = getattr(settings, "embedding_cache_version", "v1")
    configured_dimensions = getattr(settings, "embedding_dimensions", None)
    key = _cache_key(settings.openai_embedding_model, settings.openai_base_url, texts,
                     version, configured_dimensions)
    cache_path = settings.cache_dir / f"emb-{key}.npz"

    with _cache_lock(cache_path):
        try:
            cached = _read_cache(cache_path, len(texts), configured_dimensions)
        except PermissionError:
            # Another process may be replacing the file. Do not pay to embed
            # again when an existing cache simply cannot be read yet.
            raise
        if cached is not None:
            if configured_dimensions is None and getattr(settings, "has_llm", False):
                # A model alias at the same endpoint can change dimensions.
                # One bounded query on a warm cache avoids a late runtime error.
                probe_dimensions = len(embedder.embed_query("embedding dimension check"))
                if cached.shape[1] == probe_dimensions:
                    return cached
                configured_dimensions = probe_dimensions
            else:
                return cached

        matrix = embedder.embed_documents(texts)
        if not _valid_matrix(matrix, len(texts), configured_dimensions):
            raise ValueError("embedder returned an invalid or unnormalized matrix")

        # Another process may have completed the same corpus during embedding.
        try:
            cached = _read_cache(cache_path, len(texts), matrix.shape[1])
        except PermissionError:
            cached = None
        if cached is not None:
            return cached

        # Atomic publication; unique temp files and bounded Windows retries.
        fd, tmp = tempfile.mkstemp(prefix=cache_path.name + ".", suffix=".tmp", dir=cache_path.parent)
        try:
            with os.fdopen(fd, "wb") as f:
                np.savez_compressed(f, matrix=matrix)
            for attempt in range(_CACHE_RETRIES):
                try:
                    os.replace(tmp, cache_path)
                    break
                except PermissionError:
                    # If another writer already published a valid cache, this
                    # request can use its completed matrix without replacing it.
                    try:
                        cached = _read_cache(cache_path, len(texts), matrix.shape[1])
                    except PermissionError:
                        cached = None
                    if cached is not None:
                        return cached
                    if attempt == _CACHE_RETRIES - 1:
                        # Embeddings are valid; a cache sharing lock must not
                        # turn the current request into a failure or retry API work.
                        return matrix
                    time.sleep(_CACHE_RETRY_DELAY)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
        return matrix
