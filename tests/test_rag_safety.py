"""Offline regressions for cached vectors, evidence, and tool arguments."""

from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
from threading import Event
from types import SimpleNamespace
import time

import numpy as np
import pytest
from pydantic import ValidationError

from app.config import Settings, get_settings
from app.agent.budget import AgentBudgetExceeded, RunBudget, current_budget
from app.rag.embeddings import Embedder, _cache_key, load_or_build_embeddings
from app.rag.index import InMemoryIndex, Passage
from app.rag.loader import MAX_CHARS, Chunk, _raw_spans, get_section_chunks, list_drugs, load_corpus
from app.tools.base import citation_of, format_passages
from app.tools.glossary import GlossaryArgs, run as run_glossary
from app.tools.search import SearchArgs
from app.tools.search import run as run_search
from app.tools.sections import SectionArgs, run_list, run_section


CORPUS = load_corpus(get_settings().corpus_dir)


def test_low_relevance_hits_are_not_citable_evidence():
    corpus = SimpleNamespace(settings=SimpleNamespace(min_relevance=0.18),
        search_text=lambda *a, **k: [Passage(chunk=CORPUS[0], score=0.01)])
    result = run_search(corpus, "unrelated topic")
    assert result.passages == [] and result.citations == []
    assert "No passages met" in result.content


def test_search_keeps_relevant_evidence_without_weak_hits():
    corpus = SimpleNamespace(settings=SimpleNamespace(min_relevance=0.18),
        search_text=lambda *a, **k: [Passage(chunk=CORPUS[0], score=0.8), Passage(chunk=CORPUS[1], score=0.01)])
    result = run_search(corpus, "specific fact")
    assert len(result.passages) == 1 and result.citations[0].passage_id == CORPUS[0].id


def _settings(tmp_path):
    return SimpleNamespace(cache_dir=tmp_path, openai_embedding_model="offline-test", openai_base_url=None)


def _cache_path(settings, texts):
    key = _cache_key(settings.openai_embedding_model, settings.openai_base_url, texts)
    return settings.cache_dir / f"emb-{key}.npz"


class FakeEmbedder:
    def __init__(self):
        self.calls = 0

    def embed_documents(self, texts):
        self.calls += 1
        return np.tile(np.array([[1.0, 0.0]], dtype=np.float32), (len(texts), 1))


@pytest.mark.parametrize("bad", [
    np.array([1.0, 0.0]),
    np.array([[1.0, 0.0]]),
    np.array([[float("nan"), 0.0], [1.0, 0.0]]),
    np.array([[2.0, 0.0], [1.0, 0.0]]),
    np.array([[1.0, 0.0], [0.0, 0.0]]),
    np.ones((2, 0)),
])
def test_invalid_cache_is_rebuilt(tmp_path, bad):
    texts = ["one", "two"]
    settings = _settings(tmp_path)
    with _cache_path(settings, texts).open("wb") as handle:
        np.savez_compressed(handle, matrix=bad)
    embedder = FakeEmbedder()
    result = load_or_build_embeddings(texts, settings, embedder)
    assert result.shape == (2, 2)
    assert embedder.calls == 1


def test_cache_version_and_dimensions_are_part_of_key():
    assert _cache_key("model", "https://proxy", ["text"], "v1", 2) != _cache_key(
        "model", "https://proxy", ["text"], "v2", 2)
    assert _cache_key("model", "https://proxy", ["text"], "v1", 2) != _cache_key(
        "model", "https://proxy", ["text"], "v1", 3)


def test_configured_embedding_dimensions_reach_provider_client(monkeypatch):
    captured = {}

    def client(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr("app.rag.embeddings.OpenAIEmbeddings", client)
    Embedder(Settings(_env_file=None, embedding_dimensions=512))
    assert captured["dimensions"] == 512
    assert captured["max_retries"] == 0


def test_warm_cache_probe_rebuilds_when_provider_dimension_changed(tmp_path):
    settings = _settings(tmp_path)
    settings.has_llm = True
    texts = ["one", "two"]
    with _cache_path(settings, texts).open("wb") as handle:
        np.savez_compressed(handle, matrix=np.tile(np.array([[1.0, 0.0]]), (2, 1)))

    class ChangedEmbedder(FakeEmbedder):
        def embed_query(self, text):
            self.probes += 1
            return np.array([1.0, 0.0, 0.0])

        def embed_documents(self, texts):
            self.calls += 1
            return np.tile(np.array([[1.0, 0.0, 0.0]]), (len(texts), 1))

    embedder = ChangedEmbedder()
    embedder.probes = 0
    result = load_or_build_embeddings(texts, settings, embedder)
    assert result.shape == (2, 3)
    assert embedder.probes == 1 and embedder.calls == 1


def test_concurrent_cache_build_uses_unique_temp_paths(tmp_path):
    settings = _settings(tmp_path)
    texts = ["one", "two"]
    embedder = FakeEmbedder()
    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(lambda _: load_or_build_embeddings(texts, settings, embedder), range(16)))
    assert all(np.array_equal(result, results[0]) for result in results)
    assert embedder.calls == 1
    assert list(Path(tmp_path).glob("*.tmp")) == []
    with np.load(_cache_path(settings, texts)) as data:
        assert data["matrix"].shape == (2, 2)


def test_transient_windows_replace_lock_retries_without_reembedding(tmp_path, monkeypatch):
    settings = _settings(tmp_path)
    embedder = FakeEmbedder()
    original_replace = os.replace
    attempts = []

    def once_locked(src, dst):
        attempts.append((src, dst))
        if len(attempts) == 1:
            raise PermissionError("simulated Windows sharing violation")
        return original_replace(src, dst)

    monkeypatch.setattr("app.rag.embeddings.os.replace", once_locked)
    result = load_or_build_embeddings(["one", "two"], settings, embedder)
    assert result.shape == (2, 2)
    assert embedder.calls == 1
    assert len(attempts) == 2
    assert list(Path(tmp_path).glob("*.tmp")) == []


def test_transient_cache_read_lock_retries_without_reembedding(tmp_path, monkeypatch):
    settings = _settings(tmp_path)
    texts = ["one", "two"]
    expected = np.tile(np.array([[1.0, 0.0]], dtype=np.float32), (2, 1))
    with _cache_path(settings, texts).open("wb") as handle:
        np.savez_compressed(handle, matrix=expected)
    original_load = np.load
    calls = []

    def once_locked(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise PermissionError("simulated Windows sharing violation")
        return original_load(*args, **kwargs)

    monkeypatch.setattr("app.rag.embeddings.np.load", once_locked)
    embedder = FakeEmbedder()
    assert np.array_equal(load_or_build_embeddings(texts, settings, embedder), expected)
    assert len(calls) == 2
    assert embedder.calls == 0


def test_query_embedding_checks_request_deadline_before_and_after_call():
    event = Event()
    class Client:
        def __init__(self):
            self.calls = []

        def embed_query(self, text, **kwargs):
            self.calls.append(kwargs["timeout"])
            event.set()
            return [1.0, 0.0]

    embedder = Embedder.__new__(Embedder)
    embedder.request_timeout = 45.0
    embedder._client = Client()
    budget = RunBudget(time.monotonic() + 2, event, 3, 3)
    token = current_budget.set(budget)
    try:
        with pytest.raises(AgentBudgetExceeded):
            embedder.embed_query("query")
        assert len(embedder._client.calls) == 1
        assert 0 < embedder._client.calls[0] <= 2
        with pytest.raises(AgentBudgetExceeded):
            embedder.embed_query("query")
        assert len(embedder._client.calls) == 1
    finally:
        current_budget.reset(token)


def test_index_rejects_invalid_embedding_shapes_and_values():
    chunk = Chunk("c", "c.md", "x", "dailymed", None, "S", None, "text")
    with pytest.raises(ValueError):
        InMemoryIndex([chunk], np.array([1.0, 0.0]))
    with pytest.raises(ValueError):
        InMemoryIndex([chunk], np.array([[float("inf"), 0.0]]))
    with pytest.raises(ValueError):
        InMemoryIndex([chunk], np.array([[2.0, 0.0]]))
    index = InMemoryIndex([chunk], np.array([[1.0, 0.0]]))
    with pytest.raises(ValueError):
        index.search(np.array([1.0, 0.0, 0.0]), 1)
    with pytest.raises(ValueError):
        index.search(np.array([float("nan"), 0.0]), 1)


def test_search_evidence_is_not_truncated():
    text = "important evidence at the end: " + "x" * 1300 + " FINAL"
    chunk = Chunk("c", "c.md", "x", "dailymed", None, "S", None, text)
    assert "FINAL" in format_passages([Passage(chunk, 1.0)])
    assert "FINAL" in format_passages([Passage(chunk, 1.0)], max_chars=10)


@pytest.mark.parametrize("schema,values", [
    (SearchArgs, {"query": "   "}),
    (SearchArgs, {"query": "x" * 2001}),
    (SearchArgs, {"query": "valid", "drug": "  "}),
    (GlossaryArgs, {"term": "  "}),
    (GlossaryArgs, {"term": "x" * 121}),
    (SectionArgs, {"drug": " ", "section": "warnings"}),
    (SectionArgs, {"drug": "aspirin", "section": " "}),
    (SectionArgs, {"drug": "aspirin", "section": "x" * 121}),
])
def test_tool_arguments_reject_blank_or_oversized(schema, values):
    with pytest.raises(ValidationError):
        schema(**values)


def test_pregnancy_and_lactation_are_separate():
    pregnancy = get_section_chunks(CORPUS, "apixaban", "pregnancy")
    lactation = get_section_chunks(CORPUS, "apixaban", "lactation")
    assert pregnancy and lactation
    assert all("pregnancy" in (c.subsection or "").lower() for c in pregnancy)
    assert all("lactation" in (c.subsection or "").lower() for c in lactation)
    assert {c.id for c in pregnancy}.isdisjoint({c.id for c in lactation})


def test_albuterol_product_identity_is_in_metadata_and_display():
    daily = next(c for c in CORPUS if c.file == "dailymed-albuterol.md")
    consumer = next(c for c in CORPUS if c.file == "medlineplus-albuterol.md")
    assert "ipratropium" in daily.product
    assert "oral" in consumer.product
    assert "ipratropium" in format_passages([Passage(daily, 1.0)])
    assert citation_of(Passage(daily, 1.0)).product == daily.product


def test_raw_spans_reject_nonpositive_budget():
    for budget in (0, -1):
        with pytest.raises(ValueError, match="positive"):
            _raw_spans("evidence", budget)


def test_extremely_long_heading_keeps_exact_bounded_evidence(tmp_path):
    path = tmp_path / "dailymed-long.md"
    heading = "H" * (MAX_CHARS * 2)
    body = " ".join(["evidence"] * 1000)
    path.write_text(f"## {heading}\n{body}", encoding="utf-8")
    chunks = load_corpus(tmp_path)
    source = path.read_bytes().decode("utf-8")
    assert len(chunks) > 1
    assert all(c.section_title == heading and len(c.text) <= MAX_CHARS for c in chunks)
    assert all(c.raw_text == source[c.start_offset:c.end_offset] for c in chunks)
    assert "".join(c.raw_text for c in chunks) == body


def test_raw_source_spans_and_versioned_ids_are_exact():
    again = load_corpus(get_settings().corpus_dir)
    assert [c.id for c in CORPUS] == [c.id for c in again]
    for c in CORPUS:
        source_bytes = (get_settings().corpus_dir / c.file).read_bytes()
        raw = source_bytes.decode("utf-8")
        assert c.raw_text == raw[c.start_offset:c.end_offset]
        assert c.document_sha256 == __import__("hashlib").sha256(source_bytes).hexdigest()
        assert c.document_sha256[:12] in c.id
        citation = citation_of(Passage(c, 1.0))
        assert citation.excerpt == c.raw_text
        assert citation.passage_id == c.id
    assert "[passage_id=" in format_passages([Passage(CORPUS[0], 1.0)])


def test_glossary_entry_id_does_not_depend_on_query():
    corpus = SimpleNamespace(chunks=CORPUS)
    by_abbreviation = run_glossary(corpus, "INR")
    by_expansion = run_glossary(corpus, "International Normalized Ratio")
    common = {p.chunk.id for p in by_abbreviation.passages} & {p.chunk.id for p in by_expansion.passages}
    assert common
    assert all(p.chunk.raw_text == (get_settings().corpus_dir / p.chunk.file).read_bytes().decode("utf-8")[
        p.chunk.start_offset:p.chunk.end_offset] for p in by_abbreviation.passages)


def test_section_source_is_strict_and_labels_are_precise():
    assert get_section_chunks(CORPUS, "acetaminophen", "adverse_reactions", "dailymed") == []
    fallback = get_section_chunks(CORPUS, "acetaminophen", "adverse_reactions", "dailymed", allow_fallback=True)
    assert fallback and all(c.source == "medlineplus" for c in fallback)
    assert get_section_chunks(CORPUS, "acetaminophen", "boxed_warning", allow_fallback=True) == []
    overdose = get_section_chunks(CORPUS, "acetaminophen", "overdose", allow_fallback=True)
    assert overdose and all("overdose" in c.heading.lower() for c in overdose)
    for drug in ("albuterol", "ibuprofen"):
        lactation = get_section_chunks(CORPUS, drug, "lactation")
        assert lactation and all("nursing mothers" in c.heading.lower() for c in lactation)


def test_inventory_has_source_evidence_and_aspirin_fallback_is_qualified():
    corpus = SimpleNamespace(
        chunks=CORPUS,
        drugs=lambda: list_drugs(CORPUS),
        get_section_passages=lambda drug, section, source, product_id=None, allow_fallback=False: [
            Passage(c, 1.0) for c in get_section_chunks(CORPUS, drug, section, source, product_id, allow_fallback)
        ],
    )
    inventory = run_list(corpus)
    assert inventory.passages and inventory.citations
    assert "dailymed-aspirin.md" in inventory.content
    assert "ipratropium" in inventory.content
    evidence = {p.chunk.file: p.chunk.raw_text for p in inventory.passages}
    assert "Ipratropium Bromide and Albuterol Sulfate Inhalation Solution" in evidence["dailymed-albuterol.md"]
    assert "tablet" in evidence["medlineplus-albuterol.md"]
    assert "dissolve tablets" in evidence["dailymed-aspirin.md"]
    assert not run_section(corpus, "aspirin", "contraindications").passages
    result = run_section(corpus, "aspirin", "contraindications", allow_fallback=True)
    assert result.passages and result.citations
    assert "no dedicated contraindications section" in result.content
    assert "may not be exhaustive" in result.content
    assert all(c.heading.lower() == "warnings" for c in (p.chunk for p in result.passages))
    assert "product_id=ipratropium-albuterol-nebulized" in inventory.content
    assert not run_section(corpus, "albuterol", "dosage").passages
    assert "alias is not linked" in run_section(corpus, "Ventolin", "dosage").content
    assert not run_section(corpus, "Ventolin", "dosage", product_id="ipratropium-albuterol-nebulized").passages
    assert not run_section(corpus, "albuterol", "dosage", source="medlineplus", product_id="albuterol-oral").passages
    exact = run_section(corpus, "albuterol", "dosage", product_id="ipratropium-albuterol-nebulized")
    assert exact.passages and all(p.chunk.product_id == "ipratropium-albuterol-nebulized" for p in exact.passages)
