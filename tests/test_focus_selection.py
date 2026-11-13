import pytest
from app.answer import AnswerClaim, ClaimReview, DraftAnswer, DraftReview, EvidenceQuote
from app.agent.grounding import draft_issues, render_answer, review_report
from test_extractive_safety import passage


def selected(text, ids=None):
    return DraftAnswer(status="answered", claims=[AnswerClaim(id="c1", text=text, passage_ids=ids or ["p1"])])


def test_focus_may_be_partial_but_public_context_retains_the_whole_exception():
    raw = "Warfarin is contraindicated in pregnancy, except pregnant women with mechanical heart valves at high risk of thromboembolism.\nOther qualifications remain here."
    p = passage(raw, drug="warfarin")
    focus = "Warfarin is contraindicated in pregnancy"
    draft = selected(focus)
    assert not draft_issues(draft, [p])
    review = DraftReview(complete=True, safe=True, flags=[], claims=[ClaimReview(claim_id="c1", supported=True,
        verdict="entailed", evidence=[EvidenceQuote(passage_id="p1", quote=raw[:150])])])
    output = render_answer(draft, review_report(draft, review, [p]), [p])
    assert output["answer_status"] == "answered" and output["claims"][0].text == raw
    assert "except pregnant women" in output["claims"][0].text


def test_literal_focus_can_contain_sentences_and_decimal_units_without_false_paraphrase_checks():
    raw = "Documented threshold is 30 mL/min. Additional contextual information follows."
    assert not draft_issues(selected(raw), [passage(raw)])


@pytest.mark.parametrize("focus,ids", [("A paraphrase not present in the document.", ["p1"]),
    ("Short", ["p1"]), ("A" * 1801, ["p1"]), ("Documented source information.", ["p1", "p2"])])
def test_nonliteral_oversized_or_combined_focus_is_rejected(focus, ids):
    assert draft_issues(selected(focus, ids), [passage("Documented source information.")])


@pytest.mark.parametrize("complete,safe,supported", [(False, True, True), (True, False, True), (True, True, False)])
def test_exact_focus_does_not_bypass_relevance_completeness_or_safety_review(complete, safe, supported):
    raw = "A literal but potentially irrelevant source context."
    p = passage(raw)
    draft = selected(raw)
    review = DraftReview(complete=complete, safe=safe, flags=[], claims=[ClaimReview(claim_id="c1", supported=supported,
        verdict="entailed" if supported else "insufficient", evidence=[EvidenceQuote(passage_id="p1", quote=raw)])])
    assert render_answer(draft, review_report(draft, review, [p]), [p])["answer_status"] == "abstained"
