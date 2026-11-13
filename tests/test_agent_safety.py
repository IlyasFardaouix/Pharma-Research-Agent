"""Grounding, provider protocol, and request limits: no network."""
import time
from threading import Event
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import ValidationError

from app.agent.budget import AgentBudgetExceeded, RunBudget, current_budget
from app.agent.graph import _BoundedModel, _make_llm
from app.agent.nodes import _critic_evidence, agent_node, critic_node, finalize_node, tools_node, route_after_tools
from app.agent.policies import corpus_caveats as _corpus_caveats
from app.answer import AnswerClaim, DraftAnswer, DraftReview
from app.config import Settings
from app.models import Citation, GroundingReport


class Model:
    def __init__(self, content):
        self.content, self.calls = content, 0

    def invoke(self, *args, **kwargs):
        self.calls += 1
        return self.content


@pytest.mark.parametrize("changes", [
    {"complete": "true"}, {"complete": 1}, {"safe": "false"}, {"flags": None}, {"claims": None}, {"unexpected": True},
])
def test_critic_contract_fails_closed(changes):
    valid = {"complete": True, "safe": True, "claims": [], "flags": []}
    with pytest.raises(ValidationError):
        DraftReview.model_validate(valid | changes)


def test_warfarin_pregnancy_exception_cannot_be_omitted():
    p = SimpleNamespace(chunk=SimpleNamespace(drug="warfarin", text="contraindicated in pregnancy except women with mechanical heart valves at high risk of thromboembolism"))
    assert _corpus_caveats("Warfarin is contraindicated during pregnancy.", [p])
    assert not _corpus_caveats("Warfarin pregnancy contraindication has an exception for mechanical heart valves at high risk of thromboembolism.", [p])
    assert not _corpus_caveats("Warfarin is contraindicated in pregnancy except for mechanical heart valves at high thromboembolic risk.", [p])
    assert _corpus_caveats("La warfarine est contre-indiquée pendant la grossesse.", [p])
    assert not _corpus_caveats("Warfarine pendant la grossesse : exception pour valves cardiaques mécaniques à haut risque de thromboembolie.", [p])


def test_content_blocks_become_structured_draft():
    raw = '{"status":"abstained","claims":[],"abstention_reason":"outside_corpus"}'
    result = agent_node({"messages": []}, Model(AIMessage(content=[{"type": "text", "text": raw}])))
    assert result["draft"].status == "abstained"


@pytest.mark.parametrize("response", [
    AIMessage(content="partial claim", response_metadata={"finish_reason": "length"}),
    AIMessage(content="", invalid_tool_calls=[{"name": "search", "args": "{oops", "id": "x", "error": "bad"}]),
    AIMessage(content="", tool_calls=[{"name": "search", "args": {}, "id": ""}]),
])
def test_bad_provider_response_is_not_replayed(response):
    r = agent_node({"messages": []}, Model(response))
    assert r["response_error"] and not r.get("messages") and r["draft"] is None


def test_unreviewed_draft_is_never_published():
    r = finalize_node({"draft_answer": "Take an invented dose (invented.md).", "grounding": GroundingReport(verdict="ungrounded", supported=False)})
    assert "invented" not in r["draft_answer"] and r["citations"] == []


def test_unknown_citation_cannot_pass_model_review():
    fake = Model(AIMessage(content='{"verdict":"grounded","supported":true,"flags":[]}'))
    result = critic_node({"question": "test", "draft": DraftAnswer(status="answered", claims=[AnswerClaim(id="c1", text="Unknown evidence claim", passage_ids=["unknown"])]), "retrieved": []}, fake, Settings(_env_file=None, max_revisions=0))
    assert result["grounding"].verdict == "ungrounded"


def test_complete_evidence_is_required(monkeypatch):
    import app.agent.nodes as nodes
    monkeypatch.setattr(nodes, "format_passages", lambda *a, **k: "A" * 101)
    with pytest.raises(AgentBudgetExceeded):
        _critic_evidence([], "", budget=100)


def test_tool_budget_caps_one_large_batch():
    calls = [{"name": "x", "args": {}, "id": str(i)} for i in range(100)]
    model_response = AIMessage(content="", tool_calls=calls)
    budget = RunBudget(time.monotonic() + 5, Event(), 5, 3)
    token = current_budget.set(budget)
    try:
        result = tools_node({"messages": [model_response]}, {})
        assert budget.tool_calls == 3
        assert len(result["tool_trace"]) == 3
        assert route_after_tools(result) == "finalize"
    finally:
        current_budget.reset(token)


def test_llm_budget_and_cancel_prevent_calls():
    model = Model(AIMessage(content="ok"))
    wrapper = _BoundedModel(model, model, Settings(_env_file=None))
    budget = RunBudget(time.monotonic() + 5, Event(), 1, 2)
    token = current_budget.set(budget)
    try:
        wrapper.invoke([HumanMessage(content="q")])
        with pytest.raises(AgentBudgetExceeded):
            wrapper.invoke([HumanMessage(content="q")])
        assert model.calls == 1
        budget.cancel_event.set()
        with pytest.raises(AgentBudgetExceeded):
            wrapper.invoke([])
    finally:
        current_budget.reset(token)


def test_none_temperature_is_absent_from_wire_parameters():
    m = _make_llm(Settings(_env_file=None), omit_temperature=True)
    assert "temperature" not in m._default_params
    assert m._default_params.get("max_completion_tokens") == 4096


@pytest.mark.parametrize("kwargs", [{"top_k": -1}, {"max_revisions": -1}, {"min_relevance": 5}, {"request_timeout": -1}, {"max_concurrent_requests": 0}, {"openai_base_url": "file:///tmp/x"}])
def test_invalid_configuration_is_rejected(kwargs):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **kwargs)
