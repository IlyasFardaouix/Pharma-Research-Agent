"""The structured section tool returns the right, exact text (no network)."""

from app.config import get_settings
from app.rag.loader import get_section_chunks, get_section_text, load_corpus

CHUNKS = load_corpus(get_settings().corpus_dir)


def test_metformin_contraindication_threshold():
    text = get_section_text(CHUNKS, "metformin", "contraindications").lower()
    assert text, "expected a contraindications section for metformin"
    # The key fact for the eGFR=25 question: contraindicated below 30 mL/min.
    assert "below 30" in text
    assert "egfr" in text


def test_warfarin_contraindications_mention_pregnancy():
    text = get_section_text(CHUNKS, "warfarin", "contraindications").lower()
    assert "pregnancy" in text


def test_section_aliases_resolve():
    # 'interactions' alias should find warfarin's DRUG INTERACTIONS section.
    chunks = get_section_chunks(CHUNKS, "warfarin", "interactions")
    assert chunks
    assert any("interaction" in c.section_title.lower() for c in chunks)


def test_indications_do_not_leak_contraindications():
    # Regression: "indication" must not match inside "contraindications".
    chunks = get_section_chunks(CHUNKS, "apixaban", "indications")
    assert chunks, "expected an indications section for apixaban"
    assert all(c.section_num == 1 for c in chunks)
    assert all("contraindication" not in c.section_title.lower() for c in chunks)


def test_mechanism_resolves_to_subsection():
    chunks = get_section_chunks(CHUNKS, "warfarin", "mechanism")
    assert chunks
    assert any("mechanism of action" in (c.subsection or "").lower() for c in chunks)


def test_pregnancy_resolves_to_subsection():
    chunks = get_section_chunks(CHUNKS, "warfarin", "pregnancy")
    assert any("pregnancy" in (c.subsection or "").lower() for c in chunks)


def test_apixaban_pregnancy_not_mislabeled_as_lactation():
    # Regression (B4): deep headings (#### Risk Summary) must not hide 8.1 Pregnancy.
    chunks = get_section_chunks(CHUNKS, "apixaban", "pregnancy")
    assert chunks
    assert any("pregnancy" in (c.subsection or "").lower() for c in chunks)


def test_albuterol_mechanism_found():
    # Regression (B4): '### Mechanism of Action' followed by '#### ...' must still match.
    assert get_section_chunks(CHUNKS, "albuterol", "mechanism")


def test_unnumbered_labels_indications_do_not_leak_contraindications():
    for drug in ["ibuprofen", "albuterol"]:
        for c in get_section_chunks(CHUNKS, drug, "indications"):
            hay = f"{c.section_title} {c.subsection or ''}".lower()
            assert "contraindication" not in hay


def test_brand_name_alias_resolves():
    # 'Eliquis' -> apixaban
    assert get_section_chunks(CHUNKS, "Eliquis", "contraindications")


def test_unknown_section_returns_empty():
    assert get_section_text(CHUNKS, "warfarin", "nonexistent-section") == ""
