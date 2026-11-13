"""Literal word overlap, deliberately not clinical category inference."""
import re

_WORDS = re.compile(r"\b[a-z][a-z-]{4,}\b", re.I)
# Formatting/document glue, not a disease/drug-specific answer catalogue.
_STOP = set("about above after again against also among because before below between both could daily during each either following further given however including information label labeling labels medicine medication other patient patients prescribing product products refer references section sections should sodium tablet tablets their these those through under using versus warning warnings where which while would contraindicated contraindications".split())


def common_literal_terms(passages: list) -> list[str]:
    per_drug: dict[str, set[str]] = {}
    for passage in passages:
        if not passage.chunk.drug:
            continue
        text = passage.chunk.raw_text if passage.chunk.raw_text is not None else passage.chunk.text
        per_drug.setdefault(passage.chunk.drug, set()).update(w.lower() for w in _WORDS.findall(text))
    if len(per_drug) < 2:
        return []
    shared = set.intersection(*per_drug.values()) - _STOP - set(per_drug)
    return sorted(shared)[:24]


def overlap_note(terms: list[str]) -> str:
    return "Shared literal terms: " + ", ".join(terms) + ". Word overlap does not establish clinical equivalence."
