"""Corpus loading and heading-aware chunking.

The corpus mixes two document shapes:

* **DailyMed** FDA labels with *numbered* sections (``## 4 CONTRAINDICATIONS``,
  ``### 7.3 Drugs that Increase Bleeding Risk``).
* **MedlinePlus** consumer monographs with *narrative* headings
  (``## What special precautions should I follow?``).
* ``GLOSSARY.md``.

We split on Markdown headings, keep the section breadcrumb as metadata, and sub-split
long sections so each chunk stays embedding-friendly. The structured section tool
(:func:`get_section_text`) reconstructs a full section from these chunks.
"""

from __future__ import annotations

import re
import hashlib
import unicodedata
from dataclasses import dataclass
from pathlib import Path

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
SECTION_NUM_RE = re.compile(r"^(\d+)\b")
MAX_CHARS = 2000

# Canonical section -> how to identify it in a document.
#   num:   DailyMed/SPL section number — precise match for numbered FDA labels.
#   title: word-boundary needles for the heading, used for MedlinePlus (unnumbered)
#          and for sections that live in a subsection (mechanism, pregnancy).
# Using the section NUMBER for DailyMed avoids substring collisions such as
# "indication" matching inside "contraindications".
SECTION_SPEC: dict[str, dict] = {
    # "uses"/"directions" cover the OTC Drug Facts format (aspirin, acetaminophen).
    "indications": {"num": 1, "title": ["indication", "uses", "why is this medication prescribed"]},
    "dosage": {"num": 2, "title": ["dosage", "administration", "directions", "how should this medicine be used"]},
    "contraindications": {"num": 4, "title": ["contraindication", "do not use"]},
    "warnings": {"num": 5, "title": ["warning", "precaution", "special precautions"]},
    "boxed_warning": {"num": None, "title": ["boxed warning", "warning:"]},
    "adverse_reactions": {"num": 6, "title": ["adverse", "side effect"]},
    "interactions": {"num": 7, "title": ["interaction"]},
    "specific_populations": {"num": 8, "title": ["specific population"]},
    "overdose": {"num": 10, "title": ["overdose", "overdosage", "in case of emergency/overdose"]},
    "clinical_pharmacology": {"num": 12, "title": ["clinical pharmacology"]},
    "mechanism": {"num": None, "title": ["mechanism of action"]},
    "pregnancy": {"num": None, "title": ["pregnancy"]},
    "lactation": {"num": None, "title": ["lactation", "breastfeeding", "nursing mothers"]},
}


# Accept only known section identities. Free-form substring matching here would
# let a dosage heading evade the tool's product/brand checks under another name.
_SECTION_ALIASES: dict[str, str] = {
    **{key.replace("_", " "): key for key in SECTION_SPEC},
    "indication": "indications",
    "indications and usage": "indications",
    "uses": "indications",
    "why is this medication prescribed": "indications",
    "dose": "dosage",
    "doses": "dosage",
    "dosing": "dosage",
    "posology": "dosage",
    "posologie": "dosage",
    "dosage and administration": "dosage",
    "dose and administration": "dosage",
    "administration": "dosage",
    "directions": "dosage",
    "how should this medicine be used": "dosage",
    "contraindication": "contraindications",
    "do not use": "contraindications",
    "warning": "warnings",
    "warnings and precautions": "warnings",
    "precaution": "warnings",
    "precautions": "warnings",
    "special precautions": "warnings",
    "what special precautions should i follow": "warnings",
    "boxed warnings": "boxed_warning",
    "adverse reaction": "adverse_reactions",
    "side effect": "adverse_reactions",
    "side effects": "adverse_reactions",
    "what side effects can this medication cause": "adverse_reactions",
    "drug interactions": "interactions",
    "use in specific populations": "specific_populations",
    "overdosage": "overdose",
    "in case of emergency/overdose": "overdose",
    "mechanism of action": "mechanism",
    "breastfeeding": "lactation",
    "nursing mothers": "lactation",
}


def normalize_section(section: str) -> str | None:
    """Return one whitelisted section key, or None for an unknown heading.

    The tool and loader share this exact normalization before applying policies
    or selecting evidence. Numbered headings and known label titles resolve to
    the same key; arbitrary source-text queries belong to semantic search.
    """
    value = unicodedata.normalize("NFKC", section).strip().casefold()
    value = re.sub(r"^\d+(?:\.\d+)*[.)]?\s+", "", value)
    value = re.sub(r"[_-]+", " ", value)
    value = re.sub(r"\s+", " ", value).strip(" ?:.")
    return _SECTION_ALIASES.get(value)

# This is document identity, not a claim that every name for an ingredient is
# interchangeable with every product containing it. Keep uncertain OTC details
# explicit rather than guessing active ingredients absent from the source file.
PRODUCT_REGISTRY: dict[str, tuple[str, str]] = {
    "dailymed-albuterol.md": (
        "ipratropium-albuterol-nebulized",
        "ipratropium bromide + albuterol sulfate inhalation solution (nebulized combination)",
    ),
    "medlineplus-albuterol.md": (
        "albuterol-oral",
        "albuterol oral tablets, extended-release tablets, and syrup",
    ),
    "dailymed-aspirin.md": (
        "aspirin-effervescent-otc-label",
        "aspirin-containing effervescent tablets; label covers pain with heartburn",
    ),
    "medlineplus-aspirin.md": (
        "aspirin-consumer-monograph",
        "aspirin consumer monograph; formulation not specified",
    ),
}

# Common brand / alternate names -> corpus drug key (robustness for user spelling).
DRUG_ALIASES: dict[str, str] = {
    "coumadin": "warfarin", "jantoven": "warfarin",
    "eliquis": "apixaban",
    "glucophage": "metformin", "fortamet": "metformin", "glumetza": "metformin",
    "zoloft": "sertraline",
    "lipitor": "atorvastatin",
    "tylenol": "acetaminophen", "paracetamol": "acetaminophen",
    "advil": "ibuprofen", "motrin": "ibuprofen",
    "ventolin": "albuterol", "proventil": "albuterol", "salbutamol": "albuterol",
    "amoxil": "amoxicillin",
}


def normalize_drug(name: str) -> str:
    """Lowercase + resolve common brand names to the corpus drug key."""
    n = (name or "").strip().lower()
    return DRUG_ALIASES.get(n, n)


@dataclass
class Chunk:
    """A retrievable passage with provenance."""

    id: str
    file: str
    drug: str | None
    source: str  # 'dailymed' | 'medlineplus' | 'glossary' | 'other'
    section_num: int | None
    section_title: str
    subsection: str | None
    text: str  # breadcrumb + body, what we embed and show
    product: str | None = None  # formulation/ingredients when filename alone is ambiguous
    product_id: str | None = None
    raw_text: str | None = None
    start_offset: int | None = None
    end_offset: int | None = None
    document_sha256: str | None = None
    # Complete Markdown body bounded by headings, before embedding-size splits.
    # Optional for synthetic fixtures and already complete glossary entries.
    context_start_offset: int | None = None
    context_end_offset: int | None = None

    @property
    def heading(self) -> str:
        return self.subsection or self.section_title


def parse_filename(name: str) -> tuple[str, str | None]:
    """Derive (source, drug) from a corpus file name."""
    stem = Path(name).stem
    low = stem.lower()
    if low == "glossary":
        return "glossary", None
    for source in ("dailymed", "medlineplus"):
        prefix = f"{source}-"
        if low.startswith(prefix):
            return source, stem[len(prefix):].lower()
    return "other", low


def _wrap_text(text: str, max_chars: int) -> list[str]:
    """Wrap a long block on line boundaries (good for tables); hard-slice long lines."""
    out: list[str] = []
    cur = ""
    for line in text.split("\n"):
        if len(line) > max_chars:
            if cur:
                out.append(cur)
                cur = ""
            for i in range(0, len(line), max_chars):
                out.append(line[i:i + max_chars])
        elif cur and len(cur) + len(line) + 1 > max_chars:
            out.append(cur)
            cur = line
        else:
            cur = f"{cur}\n{line}" if cur else line
    if cur:
        out.append(cur)
    return out


def _split_long(body: str, max_chars: int) -> list[str]:
    """Pack paragraphs into pieces, each guaranteed no larger than ``max_chars``."""
    if len(body) <= max_chars:
        return [body]
    pieces: list[str] = []
    current = ""
    for para in re.split(r"\n\s*\n", body):
        para = para.strip()
        if not para:
            continue
        if len(para) > max_chars:
            # Oversize paragraph: flush, then wrap it so no piece exceeds the limit.
            if current:
                pieces.append(current)
                current = ""
            pieces.extend(_wrap_text(para, max_chars))
        elif current and len(current) + len(para) + 2 > max_chars:
            pieces.append(current)
            current = para
        else:
            current = f"{current}\n\n{para}" if current else para
    if current:
        pieces.append(current)
    return pieces


def _meta_from_stack(stack: list[tuple[int, str]]) -> tuple[str, int | None, str | None]:
    """Derive (section_title, section_num, subsection-path) from the heading stack.

    The H2 heading is the section; every deeper heading (H3, H4, ...) is kept in order
    as a ``>``-joined path, so hierarchy is never lost (fixes deep-heading collisions).
    """
    section_title = "Overview"
    section_num: int | None = None
    subs: list[str] = []
    for level, title in stack:
        if level == 2:
            section_title = title
            num = SECTION_NUM_RE.match(title)
            section_num = int(num.group(1)) if num else None
            subs = []
        elif level >= 3:
            subs.append(title)
    return section_title, section_num, (" > ".join(subs) if subs else None)


def _raw_spans(text: str, max_chars: int) -> list[tuple[int, int]]:
    """Split without rewriting evidence; offsets index the original decoded file."""
    if max_chars <= 0:
        raise ValueError("raw span size must be positive")
    spans = []
    pos = 0
    while pos < len(text):
        end = min(pos + max_chars, len(text))
        if end < len(text):
            # Prefer a line or word boundary when it does not waste most of a chunk.
            line_end = max(text.rfind("\n", pos, end), text.rfind("\r", pos, end)) + 1
            word_end = text.rfind(" ", pos, end) + 1
            if line_end > pos + max_chars // 2:
                end = line_end
            elif word_end > pos + max_chars // 2:
                end = word_end
        spans.append((pos, end))
        pos = end
    return spans


def _chunk_file(path: Path, source: str, drug: str | None) -> list[Chunk]:
    source_bytes = path.read_bytes()
    document = source_bytes.decode("utf-8")
    document_sha256 = hashlib.sha256(source_bytes).hexdigest()
    chunks: list[Chunk] = []
    stack: list[tuple[int, str]] = []
    body_start = 0
    product_id, product = PRODUCT_REGISTRY.get(path.name, (None, None))

    def flush(body_end: int) -> None:
        body = document[body_start:body_end]
        if not body.strip():
            return
        leading = len(body) - len(body.lstrip())
        trailing = len(body) - len(body.rstrip())
        start = body_start + leading
        body = document[start:body_end - trailing]
        section_title, section_num, subsection = _meta_from_stack(stack)
        heading = section_title + (f" > {subsection}" if subsection else "")
        crumb = " — ".join(
            p for p in [drug, f"({source})", heading] if p and p != "(other)"
        )
        # Only the display breadcrumb is shortened; full heading metadata and
        # literal source spans remain intact for provenance and citation.
        if len(crumb) > MAX_CHARS // 3:
            crumb = crumb[:MAX_CHARS // 3 - 3] + "..."
        budget = MAX_CHARS - len(crumb) - 2 if crumb else MAX_CHARS
        for relative_start, relative_end in _raw_spans(body, budget):
            piece_start = start + relative_start
            piece_end = start + relative_end
            piece = document[piece_start:piece_end]
            chunks.append(
                Chunk(
                    id=f"{path.stem}@{document_sha256[:12]}:{piece_start}-{piece_end}",
                    file=path.name,
                    drug=drug,
                    source=source,
                    section_num=section_num,
                    section_title=section_title,
                    subsection=subsection,
                    text=f"{crumb}\n\n{piece}" if crumb else piece,
                    product=product,
                    product_id=product_id,
                    raw_text=piece,
                    start_offset=piece_start,
                    end_offset=piece_end,
                    document_sha256=document_sha256,
                    context_start_offset=start,
                    context_end_offset=body_end - trailing,
                )
            )

    offset = 0
    for line in document.splitlines(keepends=True):
        line_start = offset
        offset += len(line)
        m = HEADING_RE.match(line.rstrip("\r\n"))
        if not m:
            continue
        level = len(m.group(1))
        title = m.group(2).strip()
        if level <= 1:
            # Keep the literal document title in Overview.
            continue
        flush(line_start)
        # Maintain the heading stack: pop siblings/deeper, then push this heading.
        while stack and stack[-1][0] >= level:
            stack.pop()
        stack.append((level, title))
        body_start = offset
    flush(len(document))
    return chunks


def load_corpus(corpus_dir: Path) -> list[Chunk]:
    """Load and chunk every ``.md``/``.txt`` file in ``corpus_dir`` (sorted, stable order)."""
    corpus_dir = Path(corpus_dir)
    # pathlib ordering is case-insensitive on Windows and case-sensitive on
    # Linux. Sort strings explicitly so cache row order is portable to Docker.
    files = sorted(
        (p for p in corpus_dir.iterdir() if p.suffix.lower() in {".md", ".txt"}),
        key=lambda p: p.name,
    )
    chunks: list[Chunk] = []
    for path in files:
        source, drug = parse_filename(path.name)
        chunks.extend(_chunk_file(path, source, drug))
    if not chunks:
        raise RuntimeError(f"No corpus documents found in {corpus_dir!s}")
    return chunks


def _matches_section(chunk: Chunk, spec: dict) -> bool:
    num = spec.get("num")
    # Numbered DailyMed section: match by number (precise, no substring collisions).
    if chunk.section_num is not None and num is not None:
        return chunk.section_num == num
    # MedlinePlus or subsection-based section: word-boundary match on the heading.
    hay = f"{chunk.section_title} {chunk.subsection or ''}".lower()
    # A section-8 pregnancy subsection may contain the word lactation in its
    # deeper headings/body; identify the named 8.1/8.2 branch, not descendants.
    if chunk.section_num == 8 and chunk.subsection:
        first = chunk.subsection.split(" > ", 1)[0].lower()
        if any(term in first for term in ("pregnancy", "lactation")):
            hay = first
    return any(re.search(rf"\b{re.escape(n)}", hay) for n in spec["title"])


def get_section_chunks(
    chunks: list[Chunk],
    drug: str,
    section: str,
    source: str = "dailymed",
    product_id: str | None = None,
    allow_fallback: bool = False,
) -> list[Chunk]:
    """Return the chunks making up a drug's section (e.g. 'contraindications').

    High-precision, deterministic lookup used by the ``get_drug_section`` tool.
    The requested source is strict unless ``allow_fallback`` is explicit.
    """
    drug = normalize_drug(drug)
    source = (source or "dailymed").strip().lower()
    key = normalize_section(section)
    if key is None:
        return []
    spec = SECTION_SPEC[key]

    def choose(candidate_source: str, candidate_spec: dict) -> list[Chunk]:
        return [c for c in chunks
                if c.drug == drug and c.source == candidate_source
                and (product_id is None or c.product_id == product_id)
                and (key != "boxed_warning" or (
                    c.source == "dailymed" and c.section_num is None
                    and (c.section_title.lower().startswith("warning:")
                         or c.section_title.lower().startswith("boxed warning"))))
                and _matches_section(c, candidate_spec)]

    matched = choose(source, spec)
    if not matched and allow_fallback and drug == "aspirin" and key == "contraindications":
        # A labelled warning is relevant evidence, but not an exhaustive
        # contraindications section. The tool must disclose this fallback.
        matched = choose(source, SECTION_SPEC["warnings"])
    if not matched and allow_fallback and source == "dailymed" and key != "boxed_warning":
        matched = choose("medlineplus", spec)
    return matched


def get_section_text(
    chunks: list[Chunk],
    drug: str,
    section: str,
    source: str = "dailymed",
    product_id: str | None = None,
    allow_fallback: bool = False,
) -> str:
    """Concatenated text of a drug's section, or '' if not found."""
    return "\n\n".join(c.text for c in get_section_chunks(
        chunks, drug, section, source, product_id, allow_fallback))


def list_drugs(chunks: list[Chunk]) -> dict[str, list[str]]:
    """Map each drug to the sources available for it."""
    out: dict[str, set[str]] = {}
    for c in chunks:
        if c.drug:
            out.setdefault(c.drug, set()).add(c.source)
    return {drug: sorted(sources) for drug, sources in sorted(out.items())}
