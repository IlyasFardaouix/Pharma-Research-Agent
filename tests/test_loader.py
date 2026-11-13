"""Corpus loading and chunking are deterministic (no network)."""

from app.config import get_settings
from app.rag.loader import MAX_CHARS, list_drugs, load_corpus, parse_filename

CORPUS = get_settings().corpus_dir


def test_parse_filename():
    assert parse_filename("dailymed-warfarin.md") == ("dailymed", "warfarin")
    assert parse_filename("medlineplus-metformin.md") == ("medlineplus", "metformin")
    assert parse_filename("GLOSSARY.md") == ("glossary", None)


def test_load_corpus_metadata():
    chunks = load_corpus(CORPUS)
    assert len(chunks) > 50

    warfarin = [c for c in chunks if c.drug == "warfarin" and c.source == "dailymed"]
    assert warfarin, "expected warfarin DailyMed chunks"

    # The numbered CONTRAINDICATIONS section is parsed with its section number.
    contra = [c for c in warfarin if "contraindication" in c.section_title.lower()]
    assert contra
    assert contra[0].section_num == 4


def test_list_drugs_inventory():
    drugs = list_drugs(load_corpus(CORPUS))
    for expected in ["warfarin", "apixaban", "metformin", "sertraline"]:
        assert expected in drugs
        assert "dailymed" in drugs[expected]


def test_chunks_respect_max_size():
    # Regression (B5): breadcrumb budgeting keeps every chunk within MAX_CHARS.
    for c in load_corpus(CORPUS):
        assert len(c.text) <= MAX_CHARS, f"{c.id} too long: {len(c.text)}"


def test_corpus_order_matches_string_order_on_windows_and_linux():
    names = list(dict.fromkeys(c.file for c in load_corpus(CORPUS)))
    assert names == sorted(names)
    assert names[0] == "GLOSSARY.md"
