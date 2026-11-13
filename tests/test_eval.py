"""Offline regression tests for the public-question rubric."""

import yaml
import json
import hashlib
from types import SimpleNamespace
from functools import lru_cache
from pathlib import Path

import pytest

import app.eval as eval_module
from app.eval import QUESTIONS_FILE, score_answer, score_structure
from app.models import AnswerClaim, AnswerResponse, Citation, ClaimReview, EvidenceQuote, GroundingReport
from app.answer import DraftAnswer, DraftReview


ITEMS = {item["id"]: item for item in yaml.safe_load(QUESTIONS_FILE.read_text(encoding="utf-8"))["questions"]}
VALVE_CAVEAT = (
    "An exception may apply in pregnancy with mechanical heart valves at high risk "
    "of thromboembolism (dailymed-warfarin.md)."
)


def response(answer, sources, verdict="grounded", supported=True, flags=None):
    claim = AnswerClaim(id="c1", text=answer, passage_ids=[f"{source}#0" for source in sources])
    valid = AnswerResponse(
        answer=answer,
        status="answered",
        claims=[claim],
        citations=[Citation(file=source, passage_id=f"{source}#0",
                            excerpt="Synthetic exact evidence for the test.", claim_ids=["c1"])
                   for source in sources],
        grounding=GroundingReport(
            verdict="grounded", supported=True, flags=[],
            claim_checks=[ClaimReview(claim_id="c1", supported=True, flags=[],
                                      evidence=[EvidenceQuote(passage_id=f"{source}#0",
                                                              quote="Synthetic exact evidence")
                                                for source in sources])],
        ),
    )
    # Negative evaluator fixtures intentionally bypass the publication validator:
    # they model corrupted external responses, never valid server output.
    return valid.model_copy(update={"grounding": valid.grounding.model_copy(update={
        "verdict": verdict, "supported": supported, "flags": flags or []})})


def test_affirmative_metformin_claims_pass():
    source = "dailymed-metformin.md"
    answer = (
        "Metformin is contraindicated at eGFR 25 mL/min/1.73 m2 (dailymed-metformin.md). "
        "The eGFR contraindication threshold is below 30 mL/min/1.73 m2 (dailymed-metformin.md)."
    )
    assert score_answer(ITEMS["q4"], response(answer, [source])).ok


def test_egfr_symbol_threshold_passes():
    source = "dailymed-metformin.md"
    answer = (
        "Metformin is contraindicated at eGFR 25 (dailymed-metformin.md). "
        "Metformin is contraindicated when eGFR <30 (dailymed-metformin.md)."
    )
    assert score_answer(ITEMS["q4"], response(answer, [source])).ok


def test_inline_citation_can_include_numbered_section():
    source = "dailymed-metformin.md"
    answer = (
        "Metformin is contraindicated at eGFR 25 "
        "(dailymed-metformin.md, 2.3 Recommendations for Use in Renal Impairment). "
        "The eGFR contraindication threshold is below 30 "
        "(dailymed-metformin.md, 2.3 Recommendations for Use in Renal Impairment)."
    )
    assert score_answer(ITEMS["q4"], response(answer, [source])).ok


def test_cited_bullet_inherits_drug_and_relation_from_heading():
    answer = "Warfarin contraindications:\n- Pregnancy (dailymed-warfarin.md)\n" + VALVE_CAVEAT
    assert score_answer(ITEMS["q1"], response(answer, ["dailymed-warfarin.md"])).ok


def test_citation_after_sentence_period_is_kept_with_claim():
    answer = "Warfarin is contraindicated in pregnancy. (dailymed-warfarin.md) " + VALVE_CAVEAT
    assert score_answer(ITEMS["q1"], response(answer, ["dailymed-warfarin.md"])).ok


def test_typed_claim_bullet_keeps_multi_sentence_context_for_its_citation():
    answer = (
        "- Both labels list hypersensitivity as a contraindication. Warfarin lists hypersensitivity "
        "to warfarin, while apixaban lists a severe hypersensitivity reaction to apixaban. "
        "(dailymed-warfarin.md; dailymed-apixaban.md)\n"
        "- Warfarin is contraindicated in pregnancy, except women with mechanical heart valves "
        "at high risk of thromboembolism. (dailymed-warfarin.md)\n"
        "- Apixaban is contraindicated in active pathological bleeding. (dailymed-apixaban.md)"
    )
    assert score_answer(ITEMS["q2"], response(answer, ["dailymed-warfarin.md", "dailymed-apixaban.md"])).ok
    contradicted = answer.replace("Warfarin lists hypersensitivity", "Warfarin is not contraindicated in hypersensitivity")
    assert not score_answer(ITEMS["q2"], response(contradicted, ["dailymed-warfarin.md", "dailymed-apixaban.md"])).ok


def test_no_unique_contraindication_is_not_negation_of_shared_conditions():
    answer = (
        "- Warfarin is contraindicated in pregnancy, except women with mechanical heart valves "
        "at high risk of thromboembolism. (dailymed-warfarin.md)\n"
        "- Apixaban has no contraindication unique to it in this comparison: its label lists "
        "active pathological bleeding and severe hypersensitivity, and warfarin also lists "
        "corresponding bleeding and hypersensitivity contraindications. "
        "(dailymed-apixaban.md; dailymed-warfarin.md)"
    )
    sources = ["dailymed-warfarin.md", "dailymed-apixaban.md"]
    assert score_answer(ITEMS["q2"], response(answer, sources)).ok
    negated = answer.replace("no contraindication unique to it in this comparison", "no contraindications")
    assert not score_answer(ITEMS["q2"], response(negated, sources)).ok


def test_pregnancy_without_high_risk_mechanical_valve_exception_fails():
    answer = "Warfarin is contraindicated in pregnancy (dailymed-warfarin.md)."
    scored = score_answer(ITEMS["q1"], response(answer, ["dailymed-warfarin.md"]))
    assert not scored.ok
    assert any("high_risk_mechanical_valve_exception" in failure for failure in scored.failures)


def test_keyword_soup_footer_and_negated_claim_do_not_pass():
    source = "dailymed-metformin.md"
    answer = (
        "Metformin is not contraindicated at eGFR 25. "
        "The words metformin, eGFR, 25, below 30, and contraindicated appear here.\n"
        "Sources: dailymed-metformin.md\n"
        "This is a technical demonstration."
    )
    scored = score_answer(ITEMS["q4"], response(answer, [source]))
    assert not scored.ok
    assert sum("inline-cited claim" in failure for failure in scored.failures) == 2


def test_contradiction_fails_even_after_valid_claim():
    source = "dailymed-warfarin.md"
    answer = (
        "Warfarin is contraindicated in pregnancy (dailymed-warfarin.md). "
        "Warfarin is not contraindicated in pregnancy (dailymed-warfarin.md). "
        + VALVE_CAVEAT
    )
    scored = score_answer(ITEMS["q1"], response(answer, [source]))
    assert not scored.ok
    assert any("contradictory negation" in failure for failure in scored.failures)


def test_ungrounded_and_flagged_report_fail_despite_correct_text():
    source = "dailymed-warfarin.md"
    answer = "Warfarin is contraindicated in pregnancy (dailymed-warfarin.md). " + VALVE_CAVEAT
    for verdict, supported, flags in [
        ("ungrounded", False, []),
        ("grounded", True, ["Unsupported claim"]),
    ]:
        assert not score_answer(ITEMS["q1"], response(answer, [source], verdict, supported, flags)).ok


def test_comparison_requires_drug_specific_inline_sources():
    warfarin, apixaban = "dailymed-warfarin.md", "dailymed-apixaban.md"
    answer = (
        "Warfarin is contraindicated in hypersensitivity (dailymed-warfarin.md). "
        "Apixaban is contraindicated in hypersensitivity (dailymed-warfarin.md). "
        "Warfarin is contraindicated in pregnancy (dailymed-warfarin.md). "
        "Apixaban is contraindicated in active pathological bleeding (dailymed-apixaban.md)."
    )
    scored = score_answer(ITEMS["q2"], response(answer, [warfarin, apixaban]))
    assert not scored.ok
    assert any("apixaban_hypersensitivity" in failure for failure in scored.failures)


def test_inline_citation_can_group_two_source_files():
    warfarin, apixaban = "dailymed-warfarin.md", "dailymed-apixaban.md"
    for separator in (";", ","):
        both = f"(dailymed-warfarin.md{separator} dailymed-apixaban.md)"
        answer = (
            f"Warfarin is contraindicated in hypersensitivity {both}. "
            f"Apixaban is contraindicated in severe hypersensitivity {both}. "
            "Warfarin is contraindicated in pregnancy (dailymed-warfarin.md). "
            + VALVE_CAVEAT + " "
            f"Apixaban is contraindicated in active pathological bleeding {both}. "
            "This does not establish that every bleeding-associated condition is categorically "
            f"outside apixaban's broader contraindication for active pathological bleeding {both}."
        )
        assert score_answer(ITEMS["q2"], response(answer, [warfarin, apixaban])).ok


def test_apixaban_active_bleeding_negation_fails():
    warfarin, apixaban = "dailymed-warfarin.md", "dailymed-apixaban.md"
    answer = (
        "Warfarin is contraindicated in hypersensitivity (dailymed-warfarin.md). "
        "Apixaban is contraindicated in severe hypersensitivity (dailymed-apixaban.md). "
        "Warfarin is contraindicated in pregnancy (dailymed-warfarin.md). "
        + VALVE_CAVEAT + " "
        "Apixaban is not contraindicated during active pathological bleeding (dailymed-apixaban.md)."
    )
    scored = score_answer(ITEMS["q2"], response(answer, [warfarin, apixaban]))
    assert not scored.ok
    assert any("contradictory negation: apixaban_active_bleeding" in f for f in scored.failures)


def test_interaction_needs_both_risk_and_monitoring():
    warfarin, sertraline = "dailymed-warfarin.md", "dailymed-sertraline.md"
    answer = (
        "Sertraline with warfarin increases bleeding risk (dailymed-sertraline.md). "
        "INR is mentioned (dailymed-warfarin.md)."
    )
    scored = score_answer(ITEMS["q3"], response(answer, [warfarin, sertraline]))
    assert not scored.ok
    assert any("monitor_inr" in failure for failure in scored.failures)


def test_sertraline_label_can_support_inr_monitoring():
    warfarin, sertraline = "dailymed-warfarin.md", "dailymed-sertraline.md"
    answer = (
        "Sertraline with warfarin increases bleeding risk (dailymed-sertraline.md). "
        "Patients taking warfarin should carefully monitor INR when adding sertraline "
        "(dailymed-sertraline.md)."
    )
    assert score_answer(ITEMS["q3"], response(answer, [warfarin, sertraline])).ok


def test_inr_monitoring_not_recommended_fails():
    warfarin, sertraline = "dailymed-warfarin.md", "dailymed-sertraline.md"
    answer = (
        "Sertraline with warfarin increases bleeding risk (dailymed-sertraline.md). "
        "INR monitoring is not recommended for warfarin with sertraline (dailymed-sertraline.md)."
    )
    scored = score_answer(ITEMS["q3"], response(answer, [warfarin, sertraline]))
    assert not scored.ok
    assert any("contradictory negation: monitor_inr" in f for f in scored.failures)


def test_threshold_mutation_fails_public_smoke():
    answer = (
        "Metformin is contraindicated at eGFR 35 (dailymed-metformin.md). "
        "The contraindication threshold is below eGFR 30 (dailymed-metformin.md)."
    )
    assert not score_answer(ITEMS["q4"], response(answer, ["dailymed-metformin.md"])).ok


def test_generic_structure_accepts_linked_claim_and_quote():
    assert score_structure(response("INR is a blood test.", ["GLOSSARY.md"])).ok


def test_generic_structure_rejects_swapped_quote_and_citation_link():
    valid = response("INR is a blood test.", ["GLOSSARY.md"])
    check = valid.grounding.claim_checks[0].model_copy(update={
        "evidence": [EvidenceQuote(passage_id="GLOSSARY.md#0", quote="A different unsupported quote")]
    })
    report = valid.grounding.model_copy(update={"claim_checks": [check]})
    broken = valid.model_copy(update={"grounding": report})
    assert any("invalid exact evidence" in f for f in score_structure(broken).failures)
    citation = valid.citations[0].model_copy(update={"claim_ids": ["c2"]})
    broken = valid.model_copy(update={"citations": [citation]})
    assert any("incorrect claim links" in f for f in score_structure(broken).failures)


def test_generic_structure_rejects_missing_review_or_passage():
    valid = response("INR is a blood test.", ["GLOSSARY.md"])
    report = valid.grounding.model_copy(update={"claim_checks": []})
    assert any("review does not cover" in f for f in score_structure(valid.model_copy(update={"grounding": report})).failures)
    assert any("citation passage IDs do not match" in f for f in score_structure(valid.model_copy(update={"citations": []})).failures)
    extra = Citation(file="GLOSSARY.md", passage_id="GLOSSARY.md#unclaimed",
                     excerpt="Synthetic exact evidence", claim_ids=["c1"])
    assert any("citation passage IDs do not match" in f for f in score_structure(
        valid.model_copy(update={"citations": [*valid.citations, extra]})).failures)
    stray_evidence = EvidenceQuote(passage_id="GLOSSARY.md#unclaimed",
                                   quote="Synthetic exact evidence")
    check = valid.grounding.claim_checks[0].model_copy(update={
        "evidence": [*valid.grounding.claim_checks[0].evidence, stray_evidence]})
    report = valid.grounding.model_copy(update={"claim_checks": [check]})
    assert any("invalid exact evidence" in f for f in score_structure(
        valid.model_copy(update={"grounding": report})).failures)


def test_corpus_span_and_digest_are_verified(tmp_path):
    document = "# Label\n\n🦄 Café — This exact passage supports the claimed fact.\n"
    path = tmp_path / "test.md"
    path.write_bytes(document.encode("utf-8"))
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    start = document.index("This exact")
    end = document.index("\n", start)
    assert start != len(document[:start].encode("utf-8"))  # code-point, not byte offset
    pid = f"test@{digest[:12]}:{start}-{end}"
    claim = AnswerClaim(id="c1", text="The claimed fact.", passage_ids=[pid])
    citation = Citation(file="test.md", passage_id=pid, excerpt=document[start:end],
                        document_sha256=digest, start_offset=start, end_offset=end,
                        claim_ids=["c1"])
    review = ClaimReview(claim_id="c1", supported=True,
                         evidence=[EvidenceQuote(passage_id=pid, quote="This exact passage")])
    result = AnswerResponse(answer="The claimed fact. (test.md)", status="answered", claims=[claim],
                            citations=[citation], grounding=GroundingReport(
                                verdict="grounded", supported=True, claim_checks=[review]))
    assert score_structure(result, tmp_path).ok
    altered = citation.model_copy(update={"start_offset": start + 1})
    assert any("original corpus span" in f for f in score_structure(
        result.model_copy(update={"citations": [altered]}), tmp_path).failures)
    forged_pid = f"test@{digest[:12]}:{start + 1}-{end}"
    forged_claim = claim.model_copy(update={"passage_ids": [forged_pid]})
    forged_citation = citation.model_copy(update={"passage_id": forged_pid})
    forged_review = review.model_copy(update={"evidence": [
        EvidenceQuote(passage_id=forged_pid, quote="This exact passage")]})
    forged_report = result.grounding.model_copy(update={"claim_checks": [forged_review]})
    forged = result.model_copy(update={"claims": [forged_claim], "citations": [forged_citation],
                                       "grounding": forged_report})
    assert any("original corpus span" in f for f in score_structure(forged, tmp_path).failures)
    path.write_bytes(document.replace("claimed", "different").encode("utf-8"))
    assert any("original corpus span" in f for f in score_structure(result, tmp_path).failures)


def test_real_server_render_links_shared_passages_to_exact_claims(tmp_path):
    from app.agent.grounding import render_answer, review_report
    from app.rag.index import Passage
    from app.rag.loader import Chunk

    document = "# INR\n\n## INR\n\nINR measures blood clotting and is used to monitor warfarin.\n\n## Monitoring\n\nWarfarin requires INR monitoring.\n"
    path = tmp_path / "GLOSSARY.md"
    path.write_bytes(document.encode("utf-8"))
    digest = hashlib.sha256(path.read_bytes()).hexdigest()

    def passage(body):
        start = document.index(body)
        end = start + len(body)
        pid = f"GLOSSARY@{digest[:12]}:{start}-{end}"
        return Passage(Chunk(id=pid, file=path.name, drug=None, source="glossary",
                             section_num=None, section_title="INR" if body.startswith("INR") else "Monitoring", subsection=None,
                             text=body, raw_text=body, start_offset=start,
                             end_offset=end, document_sha256=digest), 0.9)

    first = passage("INR measures blood clotting and is used to monitor warfarin.")
    second = passage("Warfarin requires INR monitoring.")
    draft = DraftAnswer(status="answered", claims=[
        AnswerClaim(id="c1", text="INR measures blood clotting", passage_ids=[first.chunk.id]),
        AnswerClaim(id="c2", text="used to monitor warfarin", passage_ids=[first.chunk.id]),
        AnswerClaim(id="c3", text="Warfarin requires INR monitoring.", passage_ids=[second.chunk.id]),
    ])
    review = DraftReview(complete=True, safe=True, flags=[], claims=[
        ClaimReview(claim_id="c1", supported=True, verdict="entailed", evidence=[
            EvidenceQuote(passage_id=first.chunk.id, quote="INR measures blood clotting")]),
        ClaimReview(claim_id="c2", supported=True, verdict="entailed", evidence=[
            EvidenceQuote(passage_id=first.chunk.id, quote="used to monitor warfarin")]),
        ClaimReview(claim_id="c3", supported=True, verdict="entailed", evidence=[
            EvidenceQuote(passage_id=second.chunk.id, quote="Warfarin requires INR monitoring.")]),
    ])
    retrieved = [first, second]
    rendered = render_answer(draft, review_report(draft, review, retrieved), retrieved)
    answer = AnswerResponse(answer=rendered["draft_answer"], status=rendered["answer_status"],
                            claims=rendered["claims"], citations=rendered["citations"],
                            grounding=rendered["grounding"], response_mode=rendered["response_mode"])

    assert score_structure(answer, tmp_path).ok
    from eval.grader import score_source_structure
    assert score_source_structure(answer, tmp_path).ok
    assert "INR measures blood clotting and is used to monitor warfarin." in answer.answer
    assert "Warfarin requires INR monitoring." in answer.answer
    assert "- INR measures blood clotting. (GLOSSARY.md)" not in answer.answer
    assert {c.passage_id: c.claim_ids for c in answer.citations} == {
        first.chunk.id: ["c1"], second.chunk.id: ["c2"]}


def test_abstention_has_no_claims_or_citations():
    abstained = AnswerResponse(
        status="abstained", answer="No relevant passage was found.",
        grounding=GroundingReport(verdict="ungrounded", supported=False),
    )
    item = {"id": "unseen", "suite": "general", "question": "Unseen drug?", "expected_status": "abstained"}
    assert score_answer(item, abstained).ok
    assert not score_answer(item, response("Unsupported answer.", ["GLOSSARY.md"])).ok
    assert not score_structure(abstained.model_copy(update={"citations": [Citation(file="GLOSSARY.md")]})).ok


def test_live_harness_reports_agent_errors_and_continues(monkeypatch, tmp_path, capsys):
    from app.agent import graph
    from app.rag import index

    questions = {"questions": [dict(ITEMS["q1"], id="q1", question=f"q{i}") for i in (1, 2)]}
    path = tmp_path / "questions.yaml"
    path.write_text(yaml.safe_dump(questions), encoding="utf-8")
    monkeypatch.setattr(eval_module, "QUESTIONS_FILE", path)
    monkeypatch.setattr(eval_module, "get_settings", lambda: SimpleNamespace(
        has_llm=True, openai_model="mock", corpus_dir=None))
    monkeypatch.setattr(index.CorpusIndex, "build", lambda settings: object())

    class FakeAgent:
        def __init__(self, corpus, settings):
            self.calls = 0

        def answer(self, question):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("hidden details")
            return response("Warfarin is contraindicated in pregnancy (dailymed-warfarin.md). " + VALVE_CAVEAT, ["dailymed-warfarin.md"])

    monkeypatch.setattr(graph, "PharmaAgent", FakeAgent)
    output_path = tmp_path / "eval.json"
    assert eval_module.main(["--questions", str(path), "--output", str(output_path)]) == 2
    output = capsys.readouterr().out
    assert "Score: 1/2 passed; 1 agent errors." in output
    assert "hidden details" not in output
    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert report["summary"]["passed"] == 1
    assert report["summary"]["total"] == 2
    assert report["summary"]["agent_errors"] == 1
    assert report["results"][0]["response"] is None
    assert report["results"][0]["error_type"] == "RuntimeError"
    assert "hidden details" not in output_path.read_text(encoding="utf-8")


def test_live_harness_masks_index_initialization_failure(monkeypatch, tmp_path, capsys):
    from app.rag import index

    def fail(_settings):
        raise RuntimeError("provider-private-details including secret-key")

    monkeypatch.setattr(eval_module, "get_settings", lambda: SimpleNamespace(
        has_llm=True, openai_model="mock", corpus_dir=None))
    monkeypatch.setattr(index.CorpusIndex, "build", fail)
    output = tmp_path / "startup.json"
    assert eval_module.main(["--output", str(output)]) == 2
    assert "provider-private-details" not in capsys.readouterr().out
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["startup_error_type"] == "RuntimeError"
    assert report["summary"]["unattempted"] == 4
    assert "secret-key" not in output.read_text(encoding="utf-8")


# The extractive contract is evaluated separately. Legacy prose fixtures above
# remain unchanged so rescoring old runs does not silently change their contract.
CORPUS = Path(__file__).resolve().parents[1] / "corpus"


@lru_cache
def _corpus_contexts():
    from app.rag.loader import load_corpus
    from app.rag.context import expand_context_passages
    from app.rag.index import Passage
    chunks = load_corpus(CORPUS)
    return expand_context_passages([Passage(c, 1.0) for c in chunks], chunks,
                                   max_context_chars=2_000_000)


def _test_render(response):
    """Test producer for externally supplied responses, including corrupt ones."""
    from app.answer import SOURCE_INTRO
    from app.models import DISCLAIMER
    from app.agent.comparison import overlap_note
    lines = [SOURCE_INTRO]
    if response.comparison_scope:
        lines.append(response.comparison_scope)
    if response.common_terms:
        lines.append(overlap_note(response.common_terms))
    by_pid = {c.passage_id: c for c in response.citations}
    for claim in response.claims:
        citation = by_pid[claim.passage_ids[0]]
        lines.append(f"{citation.product or citation.drug or 'Glossary'} — {citation.section} ({citation.file})\n{claim.text}")
    for obs in response.numeric_comparisons:
        lines.append(f"Numerical observation: {obs.variable} {obs.question_value} is numerically {obs.relation} {obs.source_threshold}. "
                     f"Question unit: {obs.question_unit}; source unit: {obs.source_unit}. {obs.condition}")
    return response.model_copy(update={"answer": "\n\n".join(lines + [DISCLAIMER])})


def _extractive(specs, *, question="", compare=False, numeric=False):
    from app.tools.base import citation_of
    from app.answer import COMPARISON_SCOPE
    from app.agent.comparison import common_literal_terms
    from app.agent.numeric import numerical_observations
    selected = [p for p in _corpus_contexts() if any(p.chunk.file == name and p.chunk.heading.startswith(heading)
                                                  for name, heading in specs)]
    assert len(selected) == len(specs), "fixture must select exactly the intended source contexts"
    claims, citations, checks = [], [], []
    for i, passage in enumerate(selected, 1):
        cid, pid, raw = f"c{i}", passage.chunk.id, passage.chunk.raw_text
        claims.append(AnswerClaim(id=cid, text=raw, passage_ids=[pid]))
        citations.append(citation_of(passage).model_copy(update={"claim_ids": [cid]}))
        checks.append(ClaimReview(claim_id=cid, supported=True, verdict="entailed",
                                 evidence=[EvidenceQuote(passage_id=pid, quote=raw[:120])]))
    result = AnswerResponse(answer="temporary", status="answered", response_mode="source_excerpts",
                            claims=claims, citations=citations, grounding=GroundingReport(
                                verdict="grounded", supported=True, scope="source_provenance", claim_checks=checks),
                            comparison_scope=COMPARISON_SCOPE if compare else None,
                            common_terms=common_literal_terms(selected) if compare else [],
                            numeric_comparisons=numerical_observations(question, selected) if numeric else [])
    return _test_render(result)


@pytest.mark.parametrize("qid,specs,compare,numeric", [
    ("q1", [("dailymed-warfarin.md", "4 CONTRAINDICATIONS")], False, False),
    ("q2", [("dailymed-warfarin.md", "4 CONTRAINDICATIONS"), ("dailymed-apixaban.md", "4 CONTRAINDICATIONS")], True, False),
    ("q3", [("dailymed-sertraline.md", "5.3 Increased Risk of Bleeding"), ("dailymed-warfarin.md", "5.1 Hemorrhage")], False, False),
    ("q4", [("dailymed-metformin.md", "4 CONTRAINDICATIONS")], False, True),
    ("q4", [("dailymed-metformin.md", "2.3 Recommendations for Use in Renal Impairment")], False, True),
])
def test_extractive_public_acceptance_requires_complete_real_evidence(qid, specs, compare, numeric):
    from eval.grader import score_source_excerpts
    item = ITEMS[qid]
    result = _extractive(specs, question=item['question'], compare=compare, numeric=numeric)
    score = score_source_excerpts(item, result, CORPUS)
    assert score.ok, score.failures


def test_extracts_cannot_be_graded_without_original_corpus():
    from eval.grader import score_source_excerpts
    result = _extractive([("dailymed-warfarin.md", "4 CONTRAINDICATIONS")])
    assert not score_source_excerpts(ITEMS['q1'], result).ok


def test_authentic_mid_context_fragment_fails_even_with_new_correct_hash_and_offsets():
    from eval.grader import score_source_excerpts
    result = _extractive([("dailymed-warfarin.md", "4 CONTRAINDICATIONS")])
    old = result.citations[0]
    # Real text, correct file/hash/offsets, but deliberately cut before exception.
    text = old.excerpt[:old.excerpt.index('Warfarin sodium tablets, USP are contraindicated in women')].rstrip()
    end = old.start_offset + len(text)
    pid = f"dailymed-warfarin@{old.document_sha256[:12]}:{old.start_offset}-{end}"
    citation = old.model_copy(update={"excerpt": text, "end_offset": end, "passage_id": pid})
    claim = result.claims[0].model_copy(update={"text": text, "passage_ids": [pid]})
    check = ClaimReview(claim_id=claim.id, supported=True, verdict='entailed', evidence=[EvidenceQuote(passage_id=pid, quote=text)])
    changed = _test_render(result.model_copy(update={"claims": [claim], "citations": [citation],
                          "grounding": result.grounding.model_copy(update={"claim_checks": [check]})}))
    score = score_source_excerpts(ITEMS['q1'], changed, CORPUS)
    assert not score.ok
    assert any('complete source context' in f for f in score.failures)
    assert any('pregnancy exception' in f for f in score.failures)


def test_two_authentic_notices_without_comparison_are_not_a_complete_comparison():
    from eval.grader import score_source_excerpts
    specs = [("dailymed-warfarin.md", "4 CONTRAINDICATIONS"), ("dailymed-apixaban.md", "4 CONTRAINDICATIONS")]
    result = _extractive(specs)
    score = score_source_excerpts(ITEMS['q2'], result, CORPUS)
    assert not score.ok and any('shared' in f for f in score.failures)
    result = _extractive(specs, compare=True)
    malicious = _test_render(result.model_copy(update={"common_terms": result.common_terms + ['safe']}))
    assert not score_source_excerpts(ITEMS['q2'], malicious, CORPUS).ok


def test_complete_authentic_wrong_section_does_not_satisfy_question():
    from eval.grader import score_source_excerpts
    result = _extractive([("dailymed-warfarin.md", "12.1 Mechanism of Action")])
    assert not score_source_excerpts(ITEMS['q1'], result, CORPUS).ok


def test_risk_alone_or_monitoring_alone_is_not_complete_interaction_answer():
    from eval.grader import score_source_excerpts
    monitoring_only = _extractive([("dailymed-warfarin.md", "5.1 Hemorrhage")])
    score = score_source_excerpts(ITEMS['q3'], monitoring_only, CORPUS)
    assert not score.ok and any('bleeding-risk' in f for f in score.failures)
    risk_only = _extractive([("dailymed-warfarin.md", "7.3 Drugs that Increase Bleeding Risk")])
    score = score_source_excerpts(ITEMS['q3'], risk_only, CORPUS)
    assert not score.ok and any('monitoring' in f for f in score.failures)


def test_threshold_excerpt_without_applying_numeric_input_is_incomplete():
    from eval.grader import score_source_excerpts
    result = _extractive([("dailymed-metformin.md", "4 CONTRAINDICATIONS")])
    score = score_source_excerpts(ITEMS['q4'], result, CORPUS)
    assert not score.ok and any('conditional numerical comparison' in f for f in score.failures)


@pytest.mark.parametrize("mutation", [
    {"relation": "above"}, {"source_threshold": "45"}, {"question_value": "35"},
    {"question_unit": "L/min"}, {"source_unit": "L/min/1.73 m2"},
    {"condition": "The patient is eligible for metformin."}, {"passage_id": "invented"},
])
def test_numeric_mutations_fail_even_when_answer_text_is_consistent_with_bad_metadata(mutation):
    from eval.grader import score_source_excerpts
    result = _extractive([("dailymed-metformin.md", "4 CONTRAINDICATIONS")], question=ITEMS['q4']['question'], numeric=True)
    observation = result.numeric_comparisons[0].model_copy(update=mutation)
    changed = _test_render(result.model_copy(update={"numeric_comparisons": [observation]}))
    assert not score_source_excerpts(ITEMS['q4'], changed, CORPUS).ok


@pytest.mark.parametrize("value,relation", [('25', 'below'), ('30', 'equal'), ('35', 'above')])
def test_numeric_general_checks_preserve_strict_threshold_boundary(value, relation):
    from eval.grader import score_source_structure
    question = f"For eGFR {value} mL/min/1.73 m2, show the metformin threshold."
    result = _extractive([("dailymed-metformin.md", "4 CONTRAINDICATIONS")], question=question, numeric=True)
    assert result.numeric_comparisons[0].relation == relation
    score = score_source_structure(result, CORPUS, question=question)
    assert score.ok, score.failures


@pytest.mark.parametrize("target", ['answer', 'notes', 'scope', 'claim_text', 'drug_metadata', 'review_verdict'])
def test_literal_evidence_cannot_launder_unverified_public_text(target):
    from eval.grader import score_source_excerpts
    result = _extractive([("dailymed-warfarin.md", "4 CONTRAINDICATIONS")])
    false = "Warfarin is safe in every pregnancy."
    if target == 'answer': result = result.model_copy(update={'answer': result.answer + '\n' + false})
    elif target == 'notes': result = result.model_copy(update={'grounding': result.grounding.model_copy(update={'notes': false})})
    elif target == 'scope': result = _test_render(result.model_copy(update={'comparison_scope': false}))
    elif target == 'claim_text': result = _test_render(result.model_copy(update={'claims': [result.claims[0].model_copy(update={'text': false})]}))
    elif target == 'drug_metadata': result = _test_render(result.model_copy(update={'citations': [result.citations[0].model_copy(update={'drug': 'apixaban'})]}))
    else: result = result.model_copy(update={'grounding': result.grounding.model_copy(update={'claim_checks': [result.grounding.claim_checks[0].model_copy(update={'verdict': None})]})})
    assert not score_source_excerpts(ITEMS['q1'], result, CORPUS).ok


def test_every_real_expanded_corpus_context_matches_independent_source_boundaries():
    from eval.grader import _canonical_source
    from app.tools.base import citation_of
    for passage in _corpus_contexts():
        failures = []
        _canonical_source(citation_of(passage), CORPUS, failures)
        assert not failures, (passage.chunk.id, failures)


def test_optimistic_reviewer_does_not_make_false_prose_public_in_extractive_contract():
    from app.agent.grounding import review_report, render_answer
    passage = next(p for p in _corpus_contexts() if p.chunk.file == 'dailymed-metformin.md' and p.chunk.heading == '4 CONTRAINDICATIONS')
    false = "Metformin permanently cures all forms of cancer."
    draft = DraftAnswer(status='answered', claims=[AnswerClaim(id='c1', text=false, passage_ids=[passage.chunk.id])])
    review = DraftReview(complete=True, safe=True, flags=[], claims=[ClaimReview(
        claim_id='c1', supported=True, verdict='entailed', evidence=[EvidenceQuote(passage_id=passage.chunk.id, quote=passage.chunk.raw_text[:120])])])
    rendered = render_answer(draft, review_report(draft, review, [passage]), [passage])
    assert false not in rendered['draft_answer']
    assert all(claim.text != false for claim in rendered['claims'])
    if rendered['answer_status'] == 'answered':
        assert rendered['claims'][0].text == passage.chunk.raw_text


def test_extractive_abstention_cannot_hide_false_prose_in_answer_or_diagnostics():
    from eval.grader import score_source_excerpts
    from app.models import DISCLAIMER
    item = {"id": "missing", "suite": "general", "expected_status": "abstained", "question": "Unknown product?"}
    result = AnswerResponse(status='abstained', response_mode='source_excerpts',
        answer="The requested product or formulation is not covered by the retrieved corpus evidence. I cannot provide its dosing instructions.\n\n" + DISCLAIMER,
        grounding=GroundingReport(verdict='ungrounded', supported=False))
    assert score_source_excerpts(item, result, CORPUS).ok
    false = 'The unknown drug cures all diseases.'
    for corrupted in [
        result.model_copy(update={'answer': false + '\n\n' + DISCLAIMER}),
        result.model_copy(update={'warnings': [false]}),
        result.model_copy(update={'grounding': result.grounding.model_copy(update={'notes': false})}),
        result.model_copy(update={'grounding': result.grounding.model_copy(update={'flags': [false]})}),
    ]:
        assert not score_source_excerpts(item, corrupted, CORPUS).ok


@pytest.mark.parametrize('suffix', ['/2 m2', '/1.74 m2', '/kg', ' per kg', '/1.73 m2/kg'])
def test_grader_rejects_numeric_unit_prefix_when_normalization_was_explicitly_different(suffix):
    from app.answer import NumericComparison
    from eval.grader import score_source_structure
    question = 'eGFR 25 mL/min' + suffix
    result = _extractive([('dailymed-metformin.md', '4 CONTRAINDICATIONS')])
    # Model the previous parser's error independently: it discarded the suffix.
    observation = NumericComparison(question_value='25', source_threshold='30', relation='below',
        question_unit='mL/min', source_unit='mL/min/1.73 m 2', passage_id=result.citations[0].passage_id)
    changed = _test_render(result.model_copy(update={'numeric_comparisons': [observation]}))
    score = score_source_structure(changed, CORPUS, question=question)
    assert not score.ok and any('input or unit' in failure for failure in score.failures)


def test_grader_rejects_unknown_source_denominator_even_with_literal_prefix():
    from app.answer import NumericComparison
    from eval.grader import _numeric_issues
    citation = Citation(file='dailymed-metformin.md', passage_id='test', excerpt='eGFR below 30 mL/min/kg')
    observation = NumericComparison(question_value='25', source_threshold='30', relation='below',
        question_unit='mL/min', source_unit='mL/min', passage_id='test')
    failures = _numeric_issues('eGFR 25 mL/min', [observation], [citation])
    assert any('threshold or unit' in failure for failure in failures)
