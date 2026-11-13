"""Structured tools that exploit the labelled structure of DailyMed documents.

``get_drug_section`` is a deterministic, high-precision lookup (no embedding noise)
that is ideal for comparisons and threshold questions, e.g. fetching the exact
CONTRAINDICATIONS section of two drugs and diffing them. ``list_drugs`` lets the
agent scope or disambiguate.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from app.rag.index import CorpusIndex, Passage
from app.rag.context import DEFAULT_MAX_CONTEXT_CHARS, EvidenceContextError, expand_context_passages
from app.rag.loader import DRUG_ALIASES, normalize_drug, normalize_section
from app.tools.base import ToolResult, citation_of, format_passages

_UNSPECIFIED_DOSAGE_PRODUCTS = {
    "albuterol-oral",  # one monograph spans tablets, extended-release tablets, syrup
    "aspirin-consumer-monograph",  # no particular marketed formulation
}

_PRODUCT_EVIDENCE_HEADINGS = {
    "dailymed-albuterol.md": "INDICATIONS AND USAGE",
    "medlineplus-albuterol.md": "How should this medicine be used?",
    "dailymed-aspirin.md": "Directions",
}

KNOWN_SECTIONS = (
    "contraindications, indications, dosage, warnings, interactions, "
    "adverse_reactions, mechanism, overdose, pregnancy, lactation, clinical_pharmacology, "
    "specific_populations"
)

SECTION_DESCRIPTION = (
    "Fetch the exact text of a labelled section for one drug. Prefer this over search "
    "for precise, structured facts (contraindications, drug interactions, dosage "
    "thresholds, mechanism of action). Deterministic and high-precision. "
    f"Valid sections: {KNOWN_SECTIONS}. Source defaults to the FDA label ('dailymed') "
    "and is strict unless allow_fallback=true. For ambiguous product dosing, "
    "list_drugs first and pass the exact product_id."
)

LIST_DESCRIPTION = (
    "List the drugs available in the corpus and which sources exist for each "
    "('dailymed' = FDA label, 'medlineplus' = consumer monograph). Use to scope a "
    "question or check spelling before other tools."
)


class SectionArgs(BaseModel):
    drug: str = Field(..., min_length=1, max_length=120, description="Drug name, e.g. 'warfarin'.")
    section: str = Field(..., min_length=1, max_length=120, description=f"One of: {KNOWN_SECTIONS}.")
    source: str = Field("dailymed", min_length=1, max_length=30, description="'dailymed' or 'medlineplus'.")
    product_id: str | None = Field(None, min_length=1, max_length=120,
                                   description="Exact corpus product identifier from list_drugs.")
    allow_fallback: bool = Field(False, description="Explicitly allow another source or labelled aspirin warnings when the requested section is absent.")

    @field_validator("drug", "section", "source", "product_id")
    @classmethod
    def _nonblank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("section arguments must not be blank")
        return value


class ListDrugsArgs(BaseModel):
    pass


def run_section(corpus: CorpusIndex, drug: str, section: str, source: str = "dailymed",
                product_id: str | None = None, allow_fallback: bool = False) -> ToolResult:
    canonical_section = normalize_section(section)
    if canonical_section is None:
        return ToolResult(content=f"Unknown corpus section '{section}'. Use one of: {KNOWN_SECTIONS}.")
    canonical = normalize_drug(drug)
    is_dosage = canonical_section == "dosage"
    products = sorted({c.product_id for c in corpus.chunks if c.drug == canonical and c.product_id})
    if is_dosage and drug.strip().lower() in DRUG_ALIASES:
        return ToolResult(content=(
            f"Cannot select dosage for brand/alternate name '{drug}' from this corpus: "
            "the alias is not linked to an exact labelled product. Use list_drugs and "
            "the document's canonical ingredient name plus exact product_id."
        ))
    if product_id is not None and product_id not in products:
        return ToolResult(content=f"Unknown product_id '{product_id}' for '{drug}'. Use list_drugs for exact product identities.")
    if is_dosage and product_id in _UNSPECIFIED_DOSAGE_PRODUCTS:
        return ToolResult(content=f"Product '{product_id}' covers multiple or unspecified formulations; no single dosage can be selected. Choose an exact label product.")
    if is_dosage and product_id is None and len(products) > 1:
        return ToolResult(content=(
            f"Dosage for '{drug}' needs an exact product_id; ingredient or brand aliases can refer "
            f"to different formulations. Available IDs: {', '.join(products) or 'none documented'}. "
            "Use list_drugs and specify the product and source."
        ))
    try:
        if product_id is None and not allow_fallback:
            passages = corpus.get_section_passages(drug, canonical_section, source)
        else:
            passages = corpus.get_section_passages(drug, canonical_section, source, product_id, allow_fallback)
    except EvidenceContextError as exc:
        return ToolResult(content=f"Complete source evidence unavailable: {exc} Choose another section or narrow the request.")
    if not passages:
        return ToolResult(
            content=(
                f"No '{section}' section found for '{drug}'. "
                "Try list_drugs to check the name, choose another source, or explicitly set allow_fallback=true."
            )
        )
    header = f"{drug} — {section} ({passages[0].chunk.source})"
    if passages[0].chunk.source != source.strip().lower():
        header += f" — requested {source}, but this is a {passages[0].chunk.source} fallback; verify its population and formulation"
    if canonical == "aspirin" and canonical_section == "contraindications" and all(
        "contraindication" not in p.chunk.heading.lower() and "do not use" not in p.chunk.heading.lower()
        for p in passages
    ):
        header += " — explicit fallback: no dedicated contraindications section; Warnings are relevant evidence and may not be exhaustive"
    try:
        passages = expand_context_passages(passages, corpus.chunks,
            max_context_chars=getattr(getattr(corpus, "settings", None),
                "max_evidence_chars", DEFAULT_MAX_CONTEXT_CHARS))
    except EvidenceContextError as exc:
        return ToolResult(content=f"Complete source evidence unavailable: {exc} Choose another section or narrow the request.")
    return ToolResult(
        content=f"{header}\n\n{format_passages(passages, max_chars=None)}",  # exact text, no truncation
        passages=passages,
        citations=[citation_of(p) for p in passages],
    )


def run_list(corpus: CorpusIndex) -> ToolResult:
    drugs = corpus.drugs()
    lines = []
    passages: list[Passage] = []
    for drug, sources in drugs.items():
        source_labels = []
        for source in sources:
            candidates = [c for c in corpus.chunks if c.drug == drug and c.source == source]
            preferred = _PRODUCT_EVIDENCE_HEADINGS.get(candidates[0].file) if candidates else None
            chunk = next((c for c in candidates if c.section_title == preferred), None) if preferred else None
            chunk = chunk or (candidates[0] if candidates else None)
            if chunk is not None:
                passages.append(Passage(chunk=chunk, score=1.0))
                product = f"; product_id={chunk.product_id}; {chunk.product}" if chunk.product else ""
                source_labels.append(f"{source} ({chunk.file}{product})")
        lines.append(f"- {drug}: {', '.join(source_labels)}")
    try:
        passages = expand_context_passages(passages, corpus.chunks,
            max_context_chars=getattr(getattr(corpus, "settings", None),
                "max_evidence_chars", DEFAULT_MAX_CONTEXT_CHARS))
    except EvidenceContextError as exc:
        return ToolResult(content=f"Complete source identity evidence unavailable: {exc}")
    return ToolResult(
        content=("Available drugs (each source backed by a corpus passage):\n" + "\n".join(lines)
                 + "\n\nIdentity evidence (one complete source passage per drug document):\n"
                 + format_passages(passages)),
        passages=passages,
        citations=[citation_of(p) for p in passages],
    )
