"""Publication invariants, including adversarial changes to otherwise valid data."""
import json
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage

from app.answer import AnswerClaim, ClaimReview, DraftAnswer, DraftReview, EvidenceQuote, GroundingReport
from app.agent.grounding import draft_issues, parse_json_document, render_answer, review_report
from app.models import AnswerResponse
from app.agent.graph import PharmaAgent, build_graph
from app.config import Settings
from app.rag.index import Passage
from app.rag.loader import Chunk
from app.tools.base import ToolResult


TEXT = "The source contains a documented research fact and an important qualification."


def passage(pid="p1", text=TEXT):
    return Passage(chunk=Chunk(id=pid, file="dailymed-example.md", drug="example", source="dailymed",
        section_num=4, section_title="Contraindications", subsection=None, text="breadcrumb\n" + text,
        raw_text=text), score=1)


def draft():
    return DraftAnswer(status="answered", claims=[AnswerClaim(id="c1", text="a documented research fact", passage_ids=["p1"])])


def review():
    return DraftReview(complete=True, safe=True, claims=[ClaimReview(claim_id="c1", supported=True, verdict="entailed",
        evidence=[EvidenceQuote(passage_id="p1", quote=TEXT)], flags=[])], flags=[])


def test_only_claim_selected_passage_is_published_not_every_hit_in_file():
    evidence = [passage(), passage("irrelevant", "An unrelated passage in the SAME source file.")]
    report = review_report(draft(), review(), evidence)
    rendered = render_answer(draft(), report, evidence)
    assert rendered["answer_status"] == "answered"
    assert [c.passage_id for c in rendered["citations"]] == ["p1"]
    assert rendered["citations"][0].excerpt == TEXT
    assert rendered["citations"][0].claim_ids == ["c1"]
    assert rendered["claims"][0].text == TEXT
    assert draft().claims[0].text != rendered["claims"][0].text
    assert rendered["response_mode"] == "source_excerpts"
    assert rendered["grounding"].scope == "source_provenance"


@pytest.mark.parametrize("change", ["missing_review", "extra_review", "wrong_quote", "wrong_passage", "unsupported", "incomplete", "unsafe", "missing_verdict", "contradicted"])
def test_adversarial_review_cannot_authorize_publication(change):
    data = review().model_dump()
    if change == "missing_review": data["claims"] = []
    elif change == "extra_review": data["claims"].append(data["claims"][0])
    elif change == "wrong_quote": data["claims"][0]["evidence"][0]["quote"] = "This text was invented by a model."
    elif change == "wrong_passage": data["claims"][0]["evidence"][0]["passage_id"] = "irrelevant"
    elif change == "unsupported": data["claims"][0]["supported"] = False
    elif change == "incomplete": data["complete"] = False
    elif change == "unsafe": data["safe"] = False
    elif change == "missing_verdict": data["claims"][0]["verdict"] = None
    elif change == "contradicted": data["claims"][0]["verdict"] = "contradicted"
    report = review_report(draft(), DraftReview.model_validate(data), [passage()])
    result = render_answer(draft(), report, [passage()])
    assert result["answer_status"] == "abstained" and not result["claims"] and not result["citations"]
    assert not result["claims"]
    # The final API object must accept every refusal, including a needs_revision
    # report after the revision limit, without leaking an invalid status.
    published = AnswerResponse(answer=result["draft_answer"], status=result["answer_status"],
        claims=result["claims"], citations=result["citations"], grounding=result["grounding"])
    assert published.grounding.verdict == "ungrounded"


def test_supported_boolean_without_per_claim_review_is_insufficient():
    result = render_answer(draft(), GroundingReport(verdict="grounded", supported=True), [passage()])
    assert result["answer_status"] == "abstained"


def test_abstention_never_publishes_raw_unverified_model_text():
    candidate = DraftAnswer(status="abstained", abstention_reason="missing_product")
    result = render_answer(candidate, None, [])
    assert result["answer_status"] == "abstained" and "product" in result["draft_answer"]


@pytest.mark.parametrize("text", ['{"safe":true,"safe":false}', '{"value":NaN}', 'Prose {"valid":true}', '{"valid":true} extra'])
def test_ambiguous_or_non_json_documents_are_rejected(text):
    with pytest.raises(ValueError):
        parse_json_document(text)


class ScriptedModel:
    def __init__(self, responses):
        self.responses, self.calls = list(responses), 0

    def bind_tools(self, tools):
        return self

    def invoke(self, messages, **kwargs):
        self.calls += 1
        return self.responses.pop(0)


def make_agent(monkeypatch, *, max_calls=8):
    import app.agent.graph as graph_module
    model = ScriptedModel([AIMessage(content='["Find the source fact"]'),
        AIMessage(content="", tool_calls=[{"name": "lookup", "args": {}, "id": "t1"}]),
        AIMessage(content=draft().model_dump_json())])
    critic = ScriptedModel([AIMessage(content=review().model_dump_json())])
    evidence = [passage(), passage("irrelevant", "This is not used by the final claim.")]
    monkeypatch.setattr(graph_module, "build_tools", lambda corpus: ([], {"lookup": lambda: ToolResult(content="evidence", passages=evidence)}))
    settings = Settings(_env_file=None, max_llm_calls=max_calls)
    compiled = build_graph(SimpleNamespace(), settings, llm=model, critic_llm=critic)
    agent = PharmaAgent.__new__(PharmaAgent)
    agent.graph, agent.settings = compiled, settings
    return agent, model, critic


def test_whole_graph_uses_verified_claims_and_exact_provenance(monkeypatch):
    agent, model, critic = make_agent(monkeypatch)
    result = agent.answer("Research the example fact")
    assert result.status == "answered" and result.grounding.supported
    assert [c.passage_id for c in result.citations] == ["p1"]
    assert result.claims[0].passage_ids == ["p1"]
    assert result.claims[0].text == TEXT
    assert len(result.tool_trace) == 1 and model.calls == 3 and critic.calls == 1


def test_request_budget_propagates_into_real_langgraph_nodes(monkeypatch):
    agent, model, critic = make_agent(monkeypatch, max_calls=3)
    result = agent.answer("Research the example fact")
    assert result.status == "abstained" and not result.claims
    assert not result.grounding.supported and len(result.tool_trace) == 1
    assert model.calls == 3 and critic.calls == 0


def test_pregnancy_exception_is_scoped_to_each_claims_evidence():
    warfarin = Passage(Chunk(id="warfarin", file="dailymed-warfarin.md", drug="warfarin",
        source="dailymed", section_num=4, section_title="Contraindications", subsection=None,
        text="Pregnancy, except women with mechanical heart valves at high risk of thromboembolism."), 1)
    other = passage("other", "The other drug has a pregnancy warning.")
    # An omitted subject must not bypass the guard.
    invalid = DraftAnswer(status="answered", claims=[
        AnswerClaim(id="c1", text="Contraindicated during pregnancy.", passage_ids=["warfarin"])])
    assert draft_issues(invalid, [warfarin, other])
    # Evidence for a different claim must not impose a warfarin exception here.
    valid = DraftAnswer(status="answered", claims=[
        AnswerClaim(id="c1", text="The other drug has a pregnancy warning.", passage_ids=["other"])])
    assert not draft_issues(valid, [warfarin, other])


@pytest.mark.parametrize("status,claims,report", [
    ("answered", [], GroundingReport(verdict="grounded", supported=True)),
    ("answered", draft().claims, GroundingReport(verdict="ungrounded", supported=False)),
    ("abstained", draft().claims, GroundingReport(verdict="ungrounded", supported=False)),
    ("abstained", [], GroundingReport(verdict="needs_revision", supported=False)),
])
def test_response_contract_rejects_incoherent_publication(status, claims, report):
    with pytest.raises(ValueError):
        AnswerResponse(answer="Example", status=status, claims=claims, grounding=report)
