"""Glossary tool: continuation lines joined, hits returned as evidence (no network)."""

import numpy as np
import hashlib
from pathlib import Path

from app.config import get_settings
from app.rag.index import CorpusIndex
from app.rag.loader import load_corpus
from app.tools import glossary


def _corpus() -> CorpusIndex:
    s = get_settings()
    chunks = load_corpus(s.corpus_dir)
    return CorpusIndex(chunks, np.ones((len(chunks), 1), dtype="float32"), None, s)


def test_definition_joins_continuation_lines():
    r = glossary.run(_corpus(), "serotonin syndrome")
    assert r.passages, "glossary hit should be returned as evidence"
    # The definition wraps across two lines; the continuation must be joined.
    assert "triptans" in r.passages[0].chunk.text.lower()


def test_hits_are_evidence_passages():
    r = glossary.run(_corpus(), "INR")
    assert r.passages and r.citations
    assert all(p.chunk.source == "glossary" for p in r.passages)


def test_short_term_rejected():
    assert glossary.run(_corpus(), "a").content.lower().startswith("provide")


def test_glossary_ids_quotes_and_offsets_match_original_document():
    corpus = _corpus()
    for citation in glossary.run(corpus, "INR").citations:
        raw = (corpus.settings.corpus_dir / citation.file).read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        start, end = citation.start_offset, citation.end_offset
        assert citation.document_sha256 == digest
        assert citation.passage_id == f"{Path(citation.file).stem}@{digest[:12]}:{start}-{end}"
        assert raw.decode("utf-8")[start:end] == citation.excerpt
