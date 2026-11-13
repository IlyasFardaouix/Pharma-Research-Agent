"""Complete evidence contexts: real clinical cut, provenance and failure cases."""
from dataclasses import replace
import hashlib
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from app.rag.context import EvidenceContextError, expand_context_passages
from app.rag.index import CorpusIndex, Passage
from app.rag.loader import load_corpus
from app.tools import glossary, search, sections


CORPUS_DIR = Path(__file__).resolve().parents[1] / "corpus"
CHUNKS = load_corpus(CORPUS_DIR)
ATORVASTATIN = next(c for c in CHUNKS if c.file == "dailymed-atorvastatin.md"
                   and c.start_offset == 25611)
PREGNANCY_PARTS = [c for c in CHUNKS if c.file == ATORVASTATIN.file
                   and c.context_start_offset == ATORVASTATIN.context_start_offset
                   and c.context_end_offset == ATORVASTATIN.context_end_offset]


def _corpus(chunks=CHUNKS, *, limit=60000):
    corpus = CorpusIndex.__new__(CorpusIndex)
    corpus.chunks = chunks
    corpus.settings = SimpleNamespace(top_k=5, min_relevance=0.18, max_evidence_chars=limit)
    return corpus


def test_real_atorvastatin_risk_sentence_is_not_served_at_its_embedding_cut():
    assert ATORVASTATIN.end_offset == 27535
    assert ATORVASTATIN.raw_text.endswith("is 2 ")
    assert PREGNANCY_PARTS[1].raw_text.startswith("to 4% and 15 to 20%")
    original = [(c.id, c.text, c.raw_text) for c in CHUNKS]
    expanded = expand_context_passages([Passage(ATORVASTATIN, 0.91)], CHUNKS)
    assert len(expanded) == 1 and expanded[0].score == 0.91
    context = expanded[0].chunk
    assert context.start_offset == 25611 and context.end_offset == 30345
    assert "is 2 to 4% and 15 to 20%, respectively." in context.raw_text
    source_bytes = (CORPUS_DIR / context.file).read_bytes()
    assert context.raw_text == source_bytes.decode("utf-8")[25611:30345]
    digest = hashlib.sha256(source_bytes).hexdigest()
    assert context.document_sha256 == digest
    assert context.id == f"dailymed-atorvastatin@{digest[:12]}:25611-30345"
    assert context.heading == ATORVASTATIN.heading
    assert len(CHUNKS) == 556
    assert [(c.id, c.text, c.raw_text) for c in CHUNKS] == original


def test_production_section_method_and_tool_publish_only_complete_context_ids():
    corpus = _corpus()
    passages = corpus.get_section_passages("atorvastatin", "pregnancy")
    result = sections.run_section(corpus, "atorvastatin", "pregnancy")
    assert len(passages) == len(result.passages) == 1
    assert result.passages[0].chunk.raw_text == passages[0].chunk.raw_text
    assert "is 2 to 4% and 15 to 20%, respectively." in result.content
    assert f"[passage_id={passages[0].chunk.id}]" in result.content
    assert f"[passage_id={ATORVASTATIN.id}]" not in result.content
    assert result.citations[0].passage_id == passages[0].chunk.id


def test_production_search_expands_and_deduplicates_before_tools_see_ids():
    other = next(c for c in CHUNKS if c.file == ATORVASTATIN.file
                 and c.context_start_offset != ATORVASTATIN.context_start_offset)
    hits = [Passage(PREGNANCY_PARTS[1], 0.7), Passage(other, 0.8),
            Passage(ATORVASTATIN, 0.95), Passage(PREGNANCY_PARTS[2], 0.9)]
    corpus = _corpus()
    calls = []
    corpus.embedder = SimpleNamespace(embed_query=lambda query: calls.append(query) or np.array([1.0]))
    corpus.index = SimpleNamespace(search=lambda vector, k, predicate: [p for p in hits if predicate(p.chunk)])
    result = search.run(corpus, "atorvastatin pregnancy risk", drug="atorvastatin", k=4)
    assert calls == ["atorvastatin pregnancy risk"]
    assert len(result.passages) == 2
    assert [p.score for p in result.passages] == [0.95, 0.8]
    assert result.passages[0].chunk.end_offset == 30345
    assert all(f"[passage_id={p.chunk.id}]" in result.content for p in result.passages)
    assert result.citations[0].excerpt == result.passages[0].chunk.raw_text


def test_context_reassembly_preserves_unicode_crlf_and_canonical_file_span(tmp_path):
    document = "# source\r\n\r\n## 8.1 Pregnancy\r\n\r\n" + ("Été β 👶: risk 2 to 4%.\r\n" * 230) + "Fin précise.\r\n"
    source_bytes = document.encode("utf-8")
    (tmp_path / "dailymed-example.md").write_bytes(source_bytes)
    chunks = load_corpus(tmp_path)
    parts = [c for c in chunks if c.section_num == 8]
    assert len(parts) > 1
    result = expand_context_passages([Passage(parts[-1], 1.0)], chunks)[0].chunk
    assert result.raw_text == document[result.start_offset:result.end_offset]
    assert result.raw_text == "".join(c.raw_text for c in parts)
    assert "\r\n" in result.raw_text and "👶" in result.raw_text
    digest = hashlib.sha256(source_bytes).hexdigest()
    assert result.document_sha256 == digest
    assert result.id == f"dailymed-example@{digest[:12]}:{result.start_offset}-{result.end_offset}"


@pytest.mark.parametrize("missing_index", [0, 1, 2])
def test_missing_first_middle_or_last_fragment_rejects_the_context(missing_index):
    incomplete = [c for c in CHUNKS if c is not PREGNANCY_PARTS[missing_index]]
    with pytest.raises(EvidenceContextError, match="missing|overlapping"):
        expand_context_passages([Passage(ATORVASTATIN, 1.0)], incomplete)


@pytest.mark.parametrize("change,expected", [
    ({"document_sha256": "0" * 64}, "SHA-256"),
    ({"product_id": "wrong-product"}, "source, heading or product"),
    ({"raw_text": "tampered"}, "bounds or exact text"),
    ({"id": "invented-id"}, "fragment ID"),
])
def test_inconsistent_source_fragment_is_rejected(change, expected):
    changed = [replace(c, **change) if c is PREGNANCY_PARTS[1] else c for c in CHUNKS]
    with pytest.raises(EvidenceContextError, match=expected):
        expand_context_passages([Passage(ATORVASTATIN, 1.0)], changed)


def test_overlapping_fragments_are_rejected_instead_of_joined_twice():
    with pytest.raises(EvidenceContextError, match="overlapping"):
        expand_context_passages([Passage(ATORVASTATIN, 1.0)], CHUNKS + [PREGNANCY_PARTS[1]])


def test_retrieved_hit_cannot_substitute_text_into_a_trusted_context():
    modified = replace(ATORVASTATIN, raw_text="X" * len(ATORVASTATIN.raw_text))
    with pytest.raises(EvidenceContextError, match="does not match"):
        expand_context_passages([Passage(modified, 1.0)], CHUNKS)


def test_context_limit_accepts_whole_unit_or_refuses_it_without_truncation():
    size = ATORVASTATIN.context_end_offset - ATORVASTATIN.context_start_offset
    full = expand_context_passages([Passage(ATORVASTATIN, 1.0)], CHUNKS, max_context_chars=size)
    assert len(full[0].chunk.raw_text) == size
    with pytest.raises(EvidenceContextError, match="exceeding.*no partial context"):
        expand_context_passages([Passage(ATORVASTATIN, 1.0)], CHUNKS, max_context_chars=size - 1)
    result = sections.run_section(_corpus(limit=size - 1), "atorvastatin", "pregnancy")
    assert not result.passages and not result.citations
    assert "Complete source evidence unavailable" in result.content
    assert "no partial context was returned" in result.content


@pytest.mark.parametrize("tool", ["search", "section"])
def test_corpus_facades_also_expose_explicit_errors_without_partial_evidence(tool):
    incomplete = [c for c in CHUNKS if c is not PREGNANCY_PARTS[1]]
    corpus = SimpleNamespace(chunks=incomplete, settings=SimpleNamespace(min_relevance=0.18),
        search_text=lambda *a, **k: [Passage(ATORVASTATIN, 1.0)],
        get_section_passages=lambda *a, **k: [Passage(ATORVASTATIN, 1.0)])
    result = (search.run(corpus, "atorvastatin pregnancy") if tool == "search"
              else sections.run_section(corpus, "atorvastatin", "pregnancy"))
    assert not result.passages and not result.citations
    assert "missing or overlapping fragment" in result.content
    assert "no partial context was returned" in result.content


def test_partial_context_metadata_is_rejected_but_complete_glossary_entries_stay_small():
    partial = replace(ATORVASTATIN, context_end_offset=None)
    with pytest.raises(EvidenceContextError, match="bounds"):
        expand_context_passages([Passage(partial, 1.0)], CHUNKS)
    result = glossary.run(_corpus(), "INR")
    assert result.passages
    expanded = expand_context_passages(result.passages, CHUNKS)
    assert len(expanded) == len(result.passages)
    for before, after in zip(result.passages, expanded):
        assert after.chunk is before.chunk
        assert after.chunk.context_start_offset is None
        assert len(after.chunk.raw_text) < 1000


def test_all_expanded_contexts_remain_exact_source_spans_with_product_metadata():
    expanded = expand_context_passages([Passage(c, 1.0) for c in CHUNKS], CHUNKS)
    assert len(expanded) < len(CHUNKS)
    assert len({p.chunk.id for p in expanded}) == len(expanded)
    documents = {c.file: (CORPUS_DIR / c.file).read_bytes() for c in CHUNKS}
    for passage in expanded:
        context = passage.chunk
        source_bytes = documents[context.file]
        assert context.raw_text == source_bytes.decode("utf-8")[context.start_offset:context.end_offset]
        assert context.document_sha256 == hashlib.sha256(source_bytes).hexdigest()
        original = next(c for c in CHUNKS if c.file == context.file
                        and c.context_start_offset == context.start_offset
                        and c.context_end_offset == context.end_offset)
        assert (context.drug, context.source, context.product, context.product_id) == (
            original.drug, original.source, original.product, original.product_id)
