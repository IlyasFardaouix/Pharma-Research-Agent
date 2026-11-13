"""Publication holds even when an injected reviewer approves false prose.

This is fault injection, not an estimate of real-model attack success rates.
Literal output still does not guarantee relevance or clinical completeness.
"""
import json
from types import SimpleNamespace

import pytest

from app.answer import AnswerClaim, ClaimReview, DraftAnswer, DraftReview, EvidenceQuote, GroundingReport
from app.agent.grounding import render_answer, review_report
from app.agent.numeric import numerical_observations
from app.models import AnswerResponse, ToolCallTrace, public_answer
from app.rag.index import Passage
from app.rag.loader import Chunk


def passage(text, *, drug="metformin", pid="p1"):
    return Passage(Chunk(id=pid, file=f"dailymed-{drug}.md", drug=drug, source="dailymed",
        section_num=4, section_title="Contraindications", subsection=None, text=text, raw_text=text), 1)


def approve(text, evidence):
    draft = DraftAnswer(status="answered", claims=[AnswerClaim(id="c1", text=text, passage_ids=["p1"])])
    # Deliberately wrong reviewer includes the new verdict; this isn't testing a missing field.
    review = DraftReview(complete=True, safe=True, claims=[ClaimReview(claim_id="c1", supported=True,
        verdict="entailed", evidence=[EvidenceQuote(passage_id="p1", quote=evidence.chunk.raw_text[:1000])])], flags=[])
    return render_answer(draft, review_report(draft, review, [evidence]), [evidence])


@pytest.mark.parametrize("false_claim", [
    "Metformin permanently cures all forms of cancer.",
    "Metformin is safe when eGFR is below 30 L/min/1.73 m2.",
    "Insulin is contraindicated at this threshold.",
    "Metformin has no renal contraindication.",
    "Warfarin-only contraindications include active bleeding.",
    "Metformin is contraindicated below 30. It permanently cures cancer.",
])
def test_optimistic_reviewer_cannot_publish_invented_factual_prose(false_claim):
    original = "  Metformin is contraindicated in patients with severe renal impairment (eGFR below 30 mL/min/1.73 m2).\n"
    result = approve(false_claim, passage(original))
    assert false_claim not in result["draft_answer"]
    if result["answer_status"] == "answered":
        assert result["claims"][0].text == original
        assert result["citations"][0].excerpt == original
    else:
        assert not result["claims"] and not result["citations"]


def test_false_critic_diagnostics_are_not_a_public_backdoor():
    response = AnswerResponse(answer="No verified answer.", status="abstained", response_mode="source_excerpts",
        grounding=GroundingReport(verdict="ungrounded", supported=False,
            flags=["Take an invented dose"], notes="Invented clinical conclusion"), warnings=["Invented benefit"])
    public = public_answer(response).model_dump_json()
    assert "invented" not in public.lower()
    assert "evidence_not_verified" in public


@pytest.mark.parametrize("field", ["query", "term", "drug", "section", "product_id"])
def test_search_hypotheses_do_not_leak_as_public_clinical_findings(field):
    response = AnswerResponse(answer="No verified answer.", status="abstained", response_mode="source_excerpts",
        plan=["Metformin cures all cancer"],
        tool_trace=[ToolCallTrace(tool="search_corpus", args={field: "Metformin cures all cancer"}, result_summary="Metformin cures all cancer"),
                    ToolCallTrace(tool="Metformin cures all cancer", args={}, result_summary="Metformin cures all cancer")],
        grounding=GroundingReport(verdict="ungrounded", supported=False))
    cleaned = public_answer(response)
    assert "cancer" not in cleaned.model_dump_json()
    assert cleaned.tool_trace[0].tool == "search_corpus"
    assert cleaned.tool_trace[1].tool == "unknown_corpus_tool"
    assert cleaned.plan_kind == "workflow_summary"


@pytest.mark.parametrize("value,relation", [("25", "below"), ("30", "equal"), ("30.1", "above"), ("29,9", "below")])
def test_numerical_observation_is_decimal_and_explicitly_conditional(value, relation):
    evidence = passage("Severe renal impairment (eGFR) below 30 mL/min/1.73 m2.")
    result = numerical_observations(f"Given eGFR {value} mL/min, what do these documents say?", [evidence])
    assert len(result) == 1 and result[0].relation == relation
    assert result[0].question_unit == "mL/min" and result[0].source_unit == "mL/min/1.73 m2"
    assert "normalization" in result[0].condition and "context" in result[0].condition


@pytest.mark.parametrize("question", ["What about renal impairment?", "eGFR 25", "eGFR 25 mL/min or eGFR 40 mL/min?"])
def test_no_numerical_inference_without_unambiguous_explicit_input(question):
    assert numerical_observations(question, [passage("eGFR below 30 mL/min")]) == []


@pytest.mark.parametrize("suffix", ["/2 m2", "/1.74 m2", "/kg", " / kg", " per kg", "/1.73 m2/kg", "utes"])
def test_unrecognized_unit_suffix_is_not_silently_discarded(suffix):
    question = "Given eGFR 25 mL/min" + suffix + ", compare the threshold."
    assert numerical_observations(question, [passage("eGFR below 30 mL/min/1.73 m2")]) == []
    assert numerical_observations("eGFR 25 mL/min", [passage("eGFR below 30 mL/min" + suffix)]) == []


def test_short_draft_limit_is_separate_from_literal_excerpt_limit():
    source = "A literal context.\n" * 200
    claim = AnswerClaim(id="c1", text=source, passage_ids=["p1"])
    assert claim.text == source
    with pytest.raises(ValueError):
        DraftAnswer(status="answered", claims=[claim])


def test_numeric_spelling_variants_are_deduplicated_without_rewriting_source_units():
    first = passage("eGFR below 30 mL/minute/1.73 m 2")
    second = passage("eGFR below 30 mL/min/1.73 m2", pid="p2")
    result = numerical_observations("eGFR 25 mL/min", [first, second])
    assert len(result) == 1
    assert result[0].source_unit == "mL/minute/1.73 m 2" and result[0].passage_id == "p1"
