"""Validate provenance and review contracts, then render solely from checked claims."""
from __future__ import annotations

import json
import re

from app.answer import AnswerClaim, ClaimReview, DraftAnswer, DraftReview, GroundingReport, SOURCE_INTRO, COMPARISON_SCOPE
from app.agent.policies import corpus_caveats
from app.agent.fidelity import fidelity_issues
from app.agent.numeric import numerical_observations
from app.agent.comparison import common_literal_terms, overlap_note
from app.models import DISCLAIMER
from app.tools.base import citation_of


def parse_json_document(text: str):
    """Accept one JSON document, optionally fenced; reject prose and duplicate keys."""
    value = text.strip()
    if value.startswith("```"):
        match = re.fullmatch(r"```(?:json)?\s*\n?(.*?)\n?```", value, re.DOTALL)
        if not match:
            raise ValueError("invalid JSON fence")
        value = match.group(1).strip()

    def pairs(items):
        result = {}
        for key, item in items:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = item
        return result

    def invalid_constant(value):
        raise ValueError("non-finite JSON number")

    return json.loads(value, object_pairs_hook=pairs, parse_constant=invalid_constant)


def passage_text(passage) -> str:
    return getattr(passage.chunk, "raw_text", None) or passage.chunk.text


def draft_issues(draft: DraftAnswer, retrieved: list, *, question: str = "") -> list[str]:
    """Validate literal focus selections; review/publication use whole contexts."""
    known = {p.chunk.id: p for p in retrieved}
    flags, invalid_focus = [], []
    for claim in draft.claims:
        if any(pid not in known for pid in claim.passage_ids):
            flags.append(f"Claim {claim.id} references a passage that was not retrieved. Use the exact passage_id shown by a tool.")
        if len(claim.passage_ids) != 1:
            flags.append(f"Selection {claim.id} must identify exactly one complete source context. Select other contexts separately.")
        selected = known.get(claim.passage_ids[0]) if len(claim.passage_ids) == 1 else None
        if not 12 <= len(claim.text) <= 1800 or selected is None or claim.text not in passage_text(selected):
            flags.append(f"Selection {claim.id} requires a 12-1800 character focus quote copied literally from its one source context. Do not paraphrase, combine or normalize source wording.")
            invalid_focus.append(claim)
            flags.extend(corpus_caveats(claim.text, [known[pid] for pid in claim.passage_ids if pid in known]))
    # These paraphrase checks give repair feedback only. A real focus quote may
    # be partial: its qualifications must remain in the complete public context,
    # which the critic still has to assess for relevance, completeness and safety.
    if invalid_focus:
        flags.extend(fidelity_issues(draft.model_copy(update={"claims": invalid_focus}), retrieved, question=question))
    return list(dict.fromkeys(flags))


def review_report(draft: DraftAnswer, review: DraftReview, retrieved: list) -> GroundingReport:
    """An approval requires complete per-claim checks and literal supporting quotes."""
    passages = {p.chunk.id: p for p in retrieved}
    claims = {c.id: c for c in draft.claims}
    flags = list(review.flags)
    check_ids = [c.claim_id for c in review.claims]
    if set(check_ids) != set(claims) or len(check_ids) != len(set(check_ids)):
        flags.append("Review must assess every claim exactly once, with no extra claim IDs.")
    if not review.complete:
        flags.append("The answer does not completely address the question.")
    if not review.safe:
        flags.append("Review identified an unsafe or ambiguous product/prescribing interpretation.")
    for check in review.claims:
        claim = claims.get(check.claim_id)
        if claim is None:
            continue
        flags.extend(check.flags)
        if check.verdict != "entailed":
            flags.append(f"Claim {check.claim_id} lacks an explicit entailed verdict; contradicted or insufficient evidence cannot authorize publication.")
        if not check.supported:
            flags.append(f"Claim {check.claim_id} is not supported by its cited passages.")
        quoted_ids = {q.passage_id for q in check.evidence}
        if quoted_ids != set(claim.passage_ids):
            flags.append(f"Review of {check.claim_id} must provide an exact quote for every referenced passage and no others.")
        for support in check.evidence:
            passage = passages.get(support.passage_id)
            if passage is None or support.passage_id not in claim.passage_ids or support.quote not in passage_text(passage):
                flags.append(f"Review quote for {check.claim_id} does not occur literally in the referenced source passage.")
    flags = list(dict.fromkeys(flags))
    return GroundingReport(verdict="needs_revision" if flags else "grounded", supported=not flags,
        flags=flags, notes=review.notes, claim_checks=review.claims)


_ABSTENTIONS = {
    "missing_product": "The requested product or formulation is not covered by the retrieved corpus evidence. I cannot provide its dosing instructions.",
    "outside_corpus": "The requested information is outside the available corpus. I cannot provide a verified answer from these documents.",
    "insufficient_evidence": "I could not verify a complete answer from the provided corpus. Please narrow the question or consult the official prescribing information.",
}


def render_answer(draft: DraftAnswer | None, report: GroundingReport | None,
                  retrieved: list, *, was_revised: bool = False, question: str = "") -> dict:
    approved = draft is not None and draft.status == "answered" and report is not None and report.supported and report.verdict in {"grounded", "revised"} and not report.flags
    if approved:
        # Revalidate the same invariants at the publication boundary. A caller
        # cannot bypass review by setting a supported boolean on arbitrary text.
        checks = DraftReview(complete=True, safe=True, claims=report.claim_checks, flags=[])
        validated = review_report(draft, checks, retrieved)
        problems = draft_issues(draft, retrieved, question=question) + validated.flags
        if problems:
            report = GroundingReport(verdict="ungrounded", supported=False, flags=list(dict.fromkeys(problems)))
            approved = False
    if not approved:
        reason = draft.abstention_reason if draft and draft.status == "abstained" else "insufficient_evidence"
        refusal_report = (report.model_copy(update={"verdict": "ungrounded", "supported": False})
                          if report else GroundingReport(verdict="ungrounded", supported=False))
        return {"answer_status": "abstained", "response_mode": "source_excerpts", "claims": [], "citations": [], "numeric_comparisons": [],
            "draft_answer": _ABSTENTIONS.get(reason, _ABSTENTIONS["insufficient_evidence"]) + "\n\n" + DISCLAIMER,
            "grounding": refusal_report}

    passages = {p.chunk.id: p for p in retrieved}
    chosen = {}
    for claim in draft.claims:
        for pid in claim.passage_ids:
            chosen.setdefault(pid, passages[pid])
    claims, citations, public_checks, lines = [], [], [], []
    for number, (pid, passage) in enumerate(chosen.items(), 1):
        cid = f"c{number}"
        literal = passage_text(passage)
        # Never publish the model's paraphrase or a shortened supporting quote.
        # The complete retrieved context is the public factual text.
        claims.append(AnswerClaim(id=cid, text=literal, passage_ids=[pid]))
        citation = citation_of(passage).model_copy(update={"claim_ids": [cid]})
        citations.append(citation)
        supports = [q for check in report.claim_checks for q in check.evidence if q.passage_id == pid]
        public_checks.append(ClaimReview(claim_id=cid, supported=True, verdict="entailed", evidence=supports[:1]))
        identity = passage.chunk.product or passage.chunk.drug or "Glossary"
        lines.append(f"{identity} — {passage.chunk.heading} ({passage.chunk.file})\n{literal}")
    observations = numerical_observations(question, list(chosen.values()))
    comparison_scope = (COMPARISON_SCOPE if len({p.chunk.drug for p in chosen.values() if p.chunk.drug}) >= 2
                        and re.search(r"\b(?:compar\w*|differences?|versus|vs)\b", question, re.I) else None)
    common_terms = common_literal_terms(list(chosen.values())) if comparison_scope else []
    for observation in observations:
        lines.append(f"Numerical observation: {observation.variable} {observation.question_value} is numerically {observation.relation} {observation.source_threshold}. "
                     f"Question unit: {observation.question_unit}; source unit: {observation.source_unit}. {observation.condition}")
    report = report.model_copy(update={"verdict": "revised" if was_revised else "grounded",
        "claim_checks": public_checks, "scope": "source_provenance"})
    return {"answer_status": "answered", "response_mode": "source_excerpts", "claims": claims, "citations": citations,
        "numeric_comparisons": observations, "comparison_scope": comparison_scope, "common_terms": common_terms,
        "draft_answer": "\n\n".join([SOURCE_INTRO, *([comparison_scope] if comparison_scope else []),
            *([overlap_note(common_terms)] if common_terms else []), *lines, DISCLAIMER]),
        "grounding": report}
