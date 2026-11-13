"""Explicit, limited corpus safety policies; these are not a clinical rules engine."""
import re
import unicodedata


def corpus_caveats(draft: str, retrieved: list) -> list[str]:
    """Regression guard for a clinically material exception in this fixed corpus.

    This supplements model review; it is not a general clinical rules engine.
    """
    flags = []
    lower = unicodedata.normalize("NFKD", draft.lower()).encode("ascii", "ignore").decode()
    warfarin_text = " ".join(p.chunk.text.lower() for p in retrieved if p.chunk.drug == "warfarin")
    if warfarin_text and re.search(r"pregnan\w*|grossess\w*|enceint\w*", lower) and "except" in warfarin_text and "mechanical heart valves" in warfarin_text:
        if not (re.search(r"\bexcept\w*\b|\bsauf\b", lower)
                and not re.search(r"\bno\s+exception\b|exception\s+does\s+not\s+apply|sans\s+exception|aucune\s+exception|including[^.\n]{0,70}mechanical", lower)
                and re.search(r"mechanical\s+(?:heart\s+)?valve|valves?\s+(?:cardiaques?\s+)?mecanique", lower)
                and re.search(r"(?:high|higher)[ -]+(?:thromboembolic[ -]+)?risk|(?:haut|eleve)\w*\s+risque|risque[^.\n]{0,45}eleve", lower)
                and "thromboembol" in lower):
            flags.append("Each warfarin pregnancy claim must include, within that SAME claim, the label's exception for mechanical heart valves at high thromboembolic risk. Combine incomplete pregnancy and exception claims into one qualified claim; preserve individualized benefit/risk qualifications from the evidence.")
    return flags

