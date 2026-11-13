"""Compute an explicitly conditional numerical observation from literal data.

This small recognizer does not infer medication eligibility or prescribe care.
If the source/question pattern is not explicit, no observation is produced.
"""
from decimal import Decimal
import re

from app.answer import NumericComparison

_VALUE = r"(\d+(?:[.,]\d+)?)"
_UNIT = r"((?:mL|ml|L|l)\s*/\s*min(?:ute)?(?:\s*/\s*1[.,]73\s*m\s*(?:\^?\s*2|²))?)(?![\w²^]|[ \t]*(?:/|\bper\b))"
_GIVEN = re.compile(r"\beGFR\s*(?:of|=|:)?\s*" + _VALUE + r"\s*" + _UNIT, re.I)
_CUTOFF = re.compile(r"\beGFR\s*\)?\s*(?:below|less\s+than|<)\s*" + _VALUE + r"\s*" + _UNIT, re.I)


def numerical_observations(question: str, passages: list) -> list[NumericComparison]:
    given = list(_GIVEN.finditer(question))
    # Multiple distinct inputs are ambiguous; do not choose one silently.
    if len({(m[1], m[2]) for m in given}) != 1:
        return []
    question_value, question_unit = given[0][1], given[0][2]
    left = Decimal(question_value.replace(",", "."))
    out, seen = [], set()
    for passage in passages:
        raw = passage.chunk.raw_text if passage.chunk.raw_text is not None else passage.chunk.text
        for cutoff in _CUTOFF.finditer(raw):
            value, unit = cutoff[1], cutoff[2]
            # Deduplicate spelling variants within one ingredient, retaining the
            # first literal unit and its source. This is no unit conversion.
            unit_key = re.sub(r"\s+", "", re.sub("minute", "min", unit, flags=re.I)).replace(",", ".").replace("²", "2").replace("^2", "2")
            key = (passage.chunk.drug, Decimal(value.replace(",", ".")), unit_key)
            if key in seen:
                continue
            seen.add(key)
            right = Decimal(value.replace(",", "."))
            out.append(NumericComparison(question_value=question_value, source_threshold=value,
                relation="below" if left < right else "above" if left > right else "equal",
                question_unit=question_unit, source_unit=unit, passage_id=passage.chunk.id))
    return out
