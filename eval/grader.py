"""Acceptance checks for the extractive contract, separate from historical prose scores.

Text authenticity, complete source context, numerical integrity and public-question
coverage are different checks. Passing these finite checks is not clinical validation.
This module never invokes a model and does not use the renderer as its scoring oracle.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import hashlib
from pathlib import Path
import re

from app.answer import COMPARISON_SCOPE, SOURCE_INTRO, NumericComparison
from app.models import DISCLAIMER
from app.agent.comparison import overlap_note


@dataclass(frozen=True)
class Score:
    ok: bool
    failures: tuple[str, ...]


def _result(failures):
    unique = tuple(dict.fromkeys(failures))
    return Score(not unique, unique)


def _body_spans(document: str, *, glossary: bool = False) -> dict[tuple[int, int], str]:
    """Independently identify complete Markdown bodies in the original file.

    Do not trust a client-provided span merely because it is a real substring.
    Glossary tools may select a complete bullet entry, including continuation lines.
    """
    headings = list(re.finditer(r"(?m)^(#{2,6})[ \t]+([^\r\n]+)[\r\n]*", document))
    boundaries = [(0, "Overview")]
    stack = []
    spans = {}
    for match in headings:
        start, label = boundaries[-1]
        body = document[start:match.start()]
        if body.strip():
            spans[(start + len(body) - len(body.lstrip()), match.start() - len(body) + len(body.rstrip()))] = label
        level, title = len(match[1]), match[2].strip()
        while stack and stack[-1][0] >= level:
            stack.pop()
        stack.append((level, title))
        deeper = [name for lev, name in stack if lev >= 3]
        label = " > ".join(deeper) if deeper else next((name for lev, name in stack if lev == 2), "Overview")
        boundaries.append((match.end(), label))
    start, label = boundaries[-1]
    body = document[start:]
    if body.strip():
        spans[(start + len(body) - len(body.lstrip()), len(document.rstrip()))] = label
    if glossary:
        entries = list(re.finditer(r"(?m)^[-*][ \t]+", document))
        for entry in entries:
            tail = document[entry.start():]
            boundary = re.search(r"\r?\n(?:[-*][ \t]+|#{1,6}[ \t]+|\r?\n)", tail)
            raw = tail[:boundary.start()] if boundary else tail
            spans[(entry.start(), entry.start() + len(raw.rstrip()))] = "Glossary"
    return spans


def _canonical_source(citation, corpus_dir, failures):
    name = citation.file
    if not name or Path(name).name != name or "/" in name or "\\" in name or not name.endswith((".md", ".txt")):
        failures.append("invalid corpus filename")
        return
    try:
        source = (corpus_dir / name).read_bytes()
        document = source.decode("utf-8")
        digest = hashlib.sha256(source).hexdigest()
        start, end = citation.start_offset, citation.end_offset
        if type(start) is not int or type(end) is not int or start < 0 or end <= start or end > len(document):
            failures.append("invalid source offsets")
            return
        expected = f"{Path(name).stem}@{digest[:12]}:{start}-{end}"
        if citation.document_sha256 != digest or citation.passage_id != expected or citation.excerpt != document[start:end]:
            failures.append("excerpt does not match original corpus span and digest")
        spans = _body_spans(document, glossary=name == "GLOSSARY.md")
        if (start, end) not in spans:
            failures.append("excerpt is not a complete source context")
        elif citation.section != spans[(start, end)]:
            failures.append("source section metadata does not match original context")
        if name == "GLOSSARY.md":
            expected_source, expected_drug = "glossary", None
        elif name.startswith(("dailymed-", "medlineplus-")):
            expected_source, expected_drug = Path(name).stem.split("-", 1)
        else:
            expected_source, expected_drug = "other", Path(name).stem.lower()
        if citation.source != expected_source or citation.drug != expected_drug:
            failures.append("source or drug metadata does not match source filename")
        # This registry describes source identity, not clinical interchangeability.
        from app.rag.loader import PRODUCT_REGISTRY
        product_id, product = PRODUCT_REGISTRY.get(name, (None, None))
        if citation.product_id != product_id or citation.product != product:
            failures.append("product metadata does not match registered corpus identity")
    except (OSError, UnicodeError):
        failures.append("original source document is unavailable")


_NUMBER = r"(?P<value>\d+(?:[.,]\d+)?)"
_UNIT = r"(?P<unit>[mM]?[lL]\s*/\s*min(?:ute)?(?:\s*/\s*1[.,]73\s*m\s*(?:\^?\s*2|²))?)"
_QUESTION_VALUE = re.compile(r"\beGFR\s*(?:of|=|:)?\s*" + _NUMBER + r"\s*" + _UNIT, re.I)
_SOURCE_VALUE = re.compile(r"\beGFR\s*\)?\s*(?:below|less\s+than|<)\s*" + _NUMBER + r"\s*" + _UNIT, re.I)


def _complete_measurements(pattern, text):
    """Do not authenticate only a recognized prefix of a longer unit.

    Inspect the remaining text independently of the runtime recognizer: unknown
    denominators (/kg, /2 m2, per kg) and unfinished tokens invalidate the match.
    """
    pairs = set()
    for match in pattern.finditer(text):
        remainder = text[match.end():]
        if re.match(r"[\w²^]|[ \t]*(?:/|per\b)", remainder, re.I):
            continue
        pairs.add((match['value'], match['unit']))
    return pairs


def _numeric_issues(question, observations, citations):
    failures, seen = [], set()
    inputs = _complete_measurements(_QUESTION_VALUE, question)
    by_pid = {c.passage_id: c for c in citations}
    for observation in observations:
        key = (observation.question_value, observation.source_threshold, observation.source_unit)
        if key in seen:
            failures.append("duplicate numerical observation")
        seen.add(key)
        if len(inputs) != 1 or (observation.question_value, observation.question_unit) not in inputs:
            failures.append("numerical input or unit is not uniquely established by the question")
        citation = by_pid.get(observation.passage_id)
        thresholds = _complete_measurements(_SOURCE_VALUE, citation.excerpt or "") if citation else set()
        if (observation.source_threshold, observation.source_unit) not in thresholds:
            failures.append("numerical threshold or unit is absent from its exact cited context")
        try:
            left = Decimal(observation.question_value.replace(',', '.'))
            right = Decimal(observation.source_threshold.replace(',', '.'))
            expected = "below" if left < right else "above" if left > right else "equal"
            if not left.is_finite() or not right.is_finite() or observation.relation != expected:
                failures.append("incorrect numerical relation")
        except (InvalidOperation, ValueError):
            failures.append("invalid numerical value")
        if observation.variable != "eGFR" or observation.condition != NumericComparison.model_fields['condition'].default:
            failures.append("numerical observation lacks the approved units/context qualification")
    return failures


def score_source_structure(response, corpus_dir: Path | None, *, question: str = "") -> Score:
    failures = []
    if response.response_mode != "source_excerpts":
        return _result(["not an extractive response"])
    report = response.grounding
    if response.disclaimer != DISCLAIMER or DISCLAIMER not in response.answer:
        failures.append("medical disclaimer missing or changed")
    if response.status == "abstained":
        if response.claims or response.citations or response.numeric_comparisons or getattr(response, 'comparison_scope', None) or getattr(response, 'common_terms', []):
            failures.append("abstention contains factual output")
        if report is None or report.supported or report.verdict != "ungrounded" or report.claim_checks:
            failures.append("abstention has incoherent review")
        approved_refusals = {
            "The requested product or formulation is not covered by the retrieved corpus evidence. I cannot provide its dosing instructions.",
            "The requested information is outside the available corpus. I cannot provide a verified answer from these documents.",
            "I could not verify a complete answer from the provided corpus. Please narrow the question or consult the official prescribing information.",
        }
        if response.answer not in {text + '\n\n' + DISCLAIMER for text in approved_refusals}:
            failures.append("abstention contains unapproved free text")
        if report and (report.notes not in {None, "No complete verified answer was published."} or
                       report.flags not in ([], ["evidence_not_verified"])):
            failures.append("abstention diagnostics contain unverified free text")
        if response.warnings not in ([], ["The answer was withheld because its evidence could not be verified. Try a narrower question."]):
            failures.append("abstention warnings contain unverified free text")
        return _result(failures)
    if response.status != "answered" or not response.claims:
        failures.append("answered response requires source excerpts")
    if report is None or not report.supported or report.flags or report.verdict not in {"grounded", "revised"} or report.scope != "source_provenance":
        failures.append("extractive response lacks an approved source-provenance review")
    if corpus_dir is None:
        failures.append("source_excerpts grading requires the original corpus")
    else:
        corpus_dir = Path(corpus_dir)
    pids = [c.passage_id for c in response.citations]
    cids = [c.id for c in response.claims]
    if len(set(pids)) != len(pids) or len(set(cids)) != len(cids) or len(pids) != len(cids):
        failures.append("source contexts and claims must be unique and one-to-one")
    citations = {c.passage_id: c for c in response.citations}
    checks = list(report.claim_checks) if report else []
    if {c.claim_id for c in checks} != set(cids) or len(checks) != len(cids):
        failures.append("review must cover every public excerpt exactly once")
    by_claim = {c.claim_id: c for c in checks}
    blocks = [SOURCE_INTRO]
    scope = getattr(response, 'comparison_scope', None)
    if scope:
        if scope != COMPARISON_SCOPE:
            failures.append("comparison scope contains unapproved interpretation")
        blocks.append(scope)
    terms = getattr(response, 'common_terms', [])
    if terms:
        per_drug = {}
        for citation in response.citations:
            if citation.drug:
                per_drug.setdefault(citation.drug, set()).update(re.findall(r'\b[a-z][a-z-]{4,}\b', (citation.excerpt or '').lower()))
        shared = set.intersection(*per_drug.values()) if len(per_drug) >= 2 else set()
        if not scope or terms != sorted(set(terms)) or not set(terms).issubset(shared):
            failures.append("common terms are not unique literal matches in every compared drug context")
        blocks.append(overlap_note(terms))
    for claim in response.claims:
        citation = citations.get(claim.passage_ids[0]) if len(claim.passage_ids) == 1 else None
        if citation is None or citation.claim_ids != [claim.id] or claim.text != citation.excerpt:
            failures.append("public claim must equal exactly one linked source context")
            continue
        if corpus_dir is not None:
            _canonical_source(citation, corpus_dir, failures)
        check = by_claim.get(claim.id)
        if check is None or not check.supported or check.verdict != 'entailed' or check.flags:
            failures.append("public excerpt lacks an explicit entailed review")
        elif not check.evidence or any(e.passage_id != citation.passage_id or e.quote not in claim.text for e in check.evidence):
            failures.append("review evidence is missing or not literal in the linked source")
        identity = citation.product or citation.drug or "Glossary"
        blocks.append(f"{identity} — {citation.section} ({citation.file})\n{claim.text}")
    failures.extend(_numeric_issues(question, response.numeric_comparisons, response.citations))
    for observation in response.numeric_comparisons:
        blocks.append(f"Numerical observation: {observation.variable} {observation.question_value} is numerically {observation.relation} {observation.source_threshold}. "
                      f"Question unit: {observation.question_unit}; source unit: {observation.source_unit}. {observation.condition}")
    blocks.append(DISCLAIMER)
    if response.answer != "\n\n".join(blocks):
        failures.append("answer contains omitted evidence or text outside the approved extractive rendering")
    if response.warnings or (report and report.notes not in {None, "Source excerpts are literal; relevance and completeness were reviewed by a model and may be wrong."}):
        failures.append("public diagnostics contain unverified free text")
    return _result(failures)


def _text(response, filename, section=None):
    return "\n".join(c.excerpt or "" for c in response.citations if c.file == filename and
                     (section is None or re.search(section, c.section or "", re.I)))


def score_source_excerpts(item: dict, response, corpus_dir: Path | None = None) -> Score:
    """Frozen public coverage criteria; do not reuse prose keyword-success rules."""
    failures = list(score_source_structure(response, corpus_dir, question=item.get('question', '')).failures)
    expected_status = item.get('expected_status', 'answered')
    if response.status != expected_status:
        failures.append(f"expected status {expected_status}, got {response.status}")
    if response.status == 'abstained':
        return _result(failures)
    if set(item.get('expected_sources', [])) - {c.file for c in response.citations}:
        failures.append("missing expected source document")
    qid = item.get('id')
    warfarin = _text(response, 'dailymed-warfarin.md', r'^4\s+contraindications$')
    apixaban = _text(response, 'dailymed-apixaban.md', r'^4\s+contraindications$')
    if qid in {'q1', 'q2'}:
        required = {
            'pregnancy exception': r'pregnant except in pregnant women with mechanical heart valves, who are at high risk of thromboembolism',
            'bleeding disorders': r'hemorrhagic tendencies or blood dyscrasias',
            'surgery': r'recent or contemplated surgery',
            'bleeding sites': r'central nervous system hemorrhage',
            'obstetric conditions': r'threatened abortion, eclampsia, and preeclampsia',
            'supervision': r'unsupervised patients',
            'procedures': r'spinal puncture',
            'hypersensitivity': r'hypersensitivity to warfarin',
            'anesthesia': r'major regional or lumbar block anesthesia',
            'hypertension': r'malignant hypertension',
        }
        for label, pattern in required.items():
            if not re.search(pattern, warfarin, re.I):
                failures.append(f"warfarin contraindications coverage missing: {label}")
    if qid == 'q2':
        if getattr(response, 'comparison_scope', None) != COMPARISON_SCOPE:
            failures.append("comparison must explicitly limit conclusions to source wording")
        if not {'bleeding', 'hypersensitivity'}.issubset(set(getattr(response, 'common_terms', []))):
            failures.append("comparison lacks the verified shared bleeding and hypersensitivity wording")
        for label in ['Active pathological bleeding', 'Severe hypersensitivity reaction to ELIQUIS']:
            if label.casefold() not in apixaban.casefold():
                failures.append(f"apixaban contraindications coverage missing: {label}")
    if qid == 'q3':
        sertraline = _text(response, 'dailymed-sertraline.md')
        # Require the interaction relationship in real source context, not just
        # the word bleeding somewhere and a glossary definition of INR elsewhere.
        if not re.search(r'warfarin', sertraline, re.I) or not re.search(r'(?:increas\w*[^.]{0,100}bleed\w*|add to (?:this|the) risk)', sertraline, re.I):
            failures.append("missing sertraline-warfarin bleeding-risk evidence")
        monitoring = sertraline + '\n' + _text(response, 'dailymed-warfarin.md')
        if not re.search(r'(?:monitor[^.]{0,120}(?:\bINR\b|international normalized ratio)|(?:\bINR\b|international normalized ratio)[^.]{0,120}monitor)', monitoring, re.I):
            failures.append("missing actionable INR monitoring evidence")
    if qid == 'q4':
        metformin = _text(response, 'dailymed-metformin.md')
        if not re.search(r'contraindicat', metformin, re.I) or not re.search(r'eGFR\s*\)?\s*below 30 mL/min(?:ute)?/1\.73 m\s*(?:2|²)', metformin, re.I):
            failures.append("missing metformin contraindication threshold with normalized units")
        valid_observations = [o for o in response.numeric_comparisons if
                              o.question_value == '25' and o.source_threshold == '30' and o.relation == 'below' and
                              any(c.passage_id == o.passage_id and c.file == 'dailymed-metformin.md' for c in response.citations)]
        if not valid_observations:
            failures.append("missing conditional numerical comparison of the question's 25 to source threshold 30")
    if item.get('suite', 'public') == 'public' and qid not in {'q1', 'q2', 'q3', 'q4'}:
        failures.append("public question has no extractive coverage criteria")
    return _result(failures)
