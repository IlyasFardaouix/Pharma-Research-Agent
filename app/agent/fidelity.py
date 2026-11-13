"""Conservative, deterministic fidelity checks over the selected source passages.

These detect specific evidence mismatches; they are NOT a general entailment
engine. A passing result does not establish that a paraphrase is true.
"""
from __future__ import annotations

import re
import unicodedata
from decimal import Decimal

from app.rag.loader import DRUG_ALIASES

_DRUGS = set(DRUG_ALIASES.values())
_NUMBER = re.compile(r"(?<![\w.])\d+(?:[.,]\d+)?(?![\d.])")
_UNITS = re.compile(r"(?<!\w)(?:mcg|[µμu]g|mg|kg|g|mL|ml|L|l|mmol|mEq|IU)(?!\w)")
_MULTI_SENTENCE = re.compile(r"[.!?]\s+(?=[A-ZÀ-ÖØ-Þ])")
_EXCLUSIVE_COMPARISON = re.compile(
    r"\bcontraindications?\s+(?:that\s+are\s+)?unique\s+to\b"
    r"|\b[\w-]+[- ]only\s+contraindications?\b"
    r"|\bno\s+contraindications?\s+(?:that\s+are\s+)?unique\b"
    r"|\bcontre[- ]indications?\s+(?:uniques?|exclusives?|propres?)\s+(?:a|au|aux)\b",
    re.I,
)


def _fold(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()


def _contains(text: str, word: str) -> bool:
    return bool(re.search(rf"(?<!\w){re.escape(word)}(?!\w)", text, re.I))


def _numbers(text: str) -> set[str]:
    return {str(Decimal(m.group().replace(",", ".")).normalize()) for m in _NUMBER.finditer(text)}


def _units(text: str) -> set[str]:
    aliases = {"ml": "mL", "l": "L", "μg": "mcg", "µg": "mcg", "ug": "mcg"}
    return {aliases.get(m.group(), m.group()) for m in _UNITS.finditer(text)}


def fidelity_issues(draft, retrieved: list, *, question: str = "") -> list[str]:
    """Check publication hazards without treating a word match as entailment.

    Question numbers are allowed as given inputs (e.g. eGFR=25); this does not
    validate an inference made from them. Units are case-sensitive (mL != L).
    No silent numerical conversions or clinical absence-by-omission are allowed.
    """
    known = {p.chunk.id: p for p in retrieved}
    flags = []
    for claim in draft.claims:
        passages = [known[pid] for pid in claim.passage_ids if pid in known]
        source = "\n".join(p.chunk.raw_text if p.chunk.raw_text is not None else p.chunk.text for p in passages)
        if not source:
            continue  # Missing IDs are rejected by the provenance validator.
        text = claim.text
        if _MULTI_SENTENCE.search(text):
            flags.append(f"Claim {claim.id} contains multiple sentences. Split substantive propositions into separate claims, each with its own evidence.")
        if _EXCLUSIVE_COMPARISON.search(_fold(text)):
            flags.append(f"Claim {claim.id} infers clinical exclusivity. Describe differences in the wording of the retrieved label sections; absence from an enumeration does not establish absence of a contraindication or risk.")
        extra_numbers = _numbers(text) - _numbers(source) - _numbers(question)
        if extra_numbers:
            flags.append(f"Claim {claim.id} uses a numerical value absent from its source passages and question. Preserve the source values and units; do not invent or silently convert them.")
        if _units(text) - _units(source + "\n" + question):
            flags.append(f"Claim {claim.id} changes a measurement unit. Preserve the literal source unit, including prefixes such as mL versus L.")
        source_drugs = {p.chunk.drug for p in passages}
        for drug in _DRUGS:
            if _contains(text, drug) and drug not in source_drugs:
                equivalents = [drug, *(alias for alias, canonical in DRUG_ALIASES.items() if canonical == drug)]
                if not any(_contains(source, name) for name in equivalents):
                    flags.append(f"Claim {claim.id} names a drug not identified by its own source passages.")
                    break
        for brand in DRUG_ALIASES:
            if _contains(text, brand) and not _contains(source, brand):
                flags.append(f"Claim {claim.id} uses a brand/alternate product name absent from its passages. Use the documented canonical ingredient and product identity instead of assuming brand equivalence.")
                break
    return list(dict.fromkeys(flags))
