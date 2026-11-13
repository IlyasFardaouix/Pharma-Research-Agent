"""Section aliases must share product policies and strict source selection."""
from pathlib import Path

import pytest

from app.rag.index import CorpusIndex
from app.rag.loader import get_section_chunks, load_corpus, normalize_section
from app.tools.registry import build_tools


CHUNKS = load_corpus(Path(__file__).resolve().parents[1] / "corpus")
DOSAGE_ALIASES = [
    "dosage", "DOSAGE AND ADMINISTRATION", "administration", "directions",
    "How should this medicine be used?", "dosing", "2 DOSAGE AND ADMINISTRATION",
    "dosage_and_administration", "  DOSAGE-AND-ADMINISTRATION  ",
    "ＤＯＳＡＧＥ ＡＮＤ ＡＤＭＩＮＩＳＴＲＡＴＩＯＮ",
]


@pytest.fixture
def section_handler():
    # Exercise production corpus lookup and validated public handler without
    # constructing an embedder or connecting to any model provider.
    corpus = CorpusIndex.__new__(CorpusIndex)
    corpus.chunks = CHUNKS
    return build_tools(corpus)[1]["get_drug_section"]


@pytest.mark.parametrize("section", DOSAGE_ALIASES)
def test_all_dosage_aliases_share_brand_and_product_policies(section_handler, section):
    assert normalize_section(section) == "dosage"
    for args, expected in [
        ({"drug": "Ventolin"}, "alias is not linked"),
        ({"drug": "Ventolin", "product_id": "ipratropium-albuterol-nebulized"}, "alias is not linked"),
        ({"drug": "albuterol"}, "needs an exact product_id"),
        ({"drug": "albuterol", "source": "medlineplus", "product_id": "albuterol-oral"}, "multiple or unspecified"),
    ]:
        result = section_handler(section=section, **args)
        assert not result.passages and not result.citations
        assert expected in result.content


@pytest.mark.parametrize("section", DOSAGE_ALIASES)
def test_exact_product_remains_available_under_dosage_aliases(section_handler, section):
    result = section_handler(drug="albuterol", section=section,
        product_id="ipratropium-albuterol-nebulized")
    assert result.passages
    assert all(p.chunk.product_id == "ipratropium-albuterol-nebulized" for p in result.passages)
    assert any("one 3 mL vial" in p.chunk.raw_text for p in result.passages)


@pytest.mark.parametrize("section", ["DOS", "AND", "DOSAGE AND", "not a real section", "age", "use"])
def test_unknown_section_does_not_fall_back_to_substring_matching(section_handler, section):
    assert normalize_section(section) is None
    assert not get_section_chunks(CHUNKS, "albuterol", section, allow_fallback=True)
    result = section_handler(drug="Ventolin", section=section, allow_fallback=True)
    assert not result.passages and not result.citations
    assert "Unknown corpus section" in result.content


def test_source_strictness_and_explicit_fallback_survive_aliases(section_handler):
    strict = section_handler(drug="acetaminophen", section="side effects")
    assert not strict.passages
    fallback = section_handler(drug="acetaminophen", section="side effects", allow_fallback=True)
    assert fallback.passages and all(p.chunk.source == "medlineplus" for p in fallback.passages)
    assert "fallback" in fallback.content
    warnings = section_handler(drug="aspirin", section="contraindication", allow_fallback=True)
    assert warnings.passages
    assert "no dedicated contraindications section" in warnings.content
    assert "may not be exhaustive" in warnings.content


def test_loader_canonicalizes_known_titles_without_leaking_sections():
    assert get_section_chunks(CHUNKS, "warfarin", "DRUG INTERACTIONS")
    indications = get_section_chunks(CHUNKS, "apixaban", "1 INDICATIONS AND USAGE")
    assert indications and all(c.section_num == 1 for c in indications)
    assert not any("contraindication" in c.section_title.lower() for c in indications)


def test_inventory_exposes_exact_ids_and_complete_identity_evidence():
    corpus = CorpusIndex.__new__(CorpusIndex)
    corpus.chunks = CHUNKS
    result = build_tools(corpus)[1]["list_drugs"]()
    assert len(result.passages) == len({c.file for c in CHUNKS if c.drug})
    assert {p.chunk.id for p in result.passages} == {c.passage_id for c in result.citations}
    for passage in result.passages:
        chunk = passage.chunk
        assert f"[passage_id={chunk.id}]" in result.content
        assert chunk.raw_text in result.content
        citation = next(c for c in result.citations if c.passage_id == chunk.id)
        assert citation.excerpt == chunk.raw_text
        document = (Path(__file__).resolve().parents[1] / "corpus" / chunk.file).read_bytes().decode("utf-8")
        assert document[chunk.start_offset:chunk.end_offset] == chunk.raw_text
