"""HTTP contract tests with independent apps and no provider calls."""

import threading
import time
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient
from openai import BadRequestError

from app.main import create_app
from app.answer import AnswerClaim, ClaimReview, EvidenceQuote
from app.models import AnswerResponse, Citation, GroundingReport


CORPUS = SimpleNamespace(num_files=1, num_chunks=4)


def settings(*, has_llm=True, answer_timeout=0.1, max_concurrent_requests=1):
    return SimpleNamespace(has_llm=has_llm, answer_timeout=answer_timeout,
                           max_concurrent_requests=max_concurrent_requests)


class FakeAgent:
    def answer(self, question: str, *, cancel_event=None, deadline=None) -> AnswerResponse:
        return AnswerResponse(
            answer="Warfarin is contraindicated in pregnancy (dailymed-warfarin.md).",
            status="answered",
            claims=[AnswerClaim(id="c1", text="Warfarin is contraindicated in pregnancy.",
                                passage_ids=["warfarin-4-1"])],
            citations=[Citation(file="dailymed-warfarin.md", drug="warfarin", source="dailymed",
                                section="4 CONTRAINDICATIONS", passage_id="warfarin-4-1",
                                excerpt="Warfarin sodium tablets are contraindicated in pregnancy.",
                                claim_ids=["c1"])],
            plan=["Find warfarin contraindications"],
            grounding=GroundingReport(verdict="grounded", supported=True,
                                      claim_checks=[ClaimReview(claim_id="c1", supported=True, verdict="entailed",
                                          evidence=[EvidenceQuote(passage_id="warfarin-4-1",
                                              quote="contraindicated in pregnancy")])]),
        )


def fresh_app(*, agent=None, configured=True, timeout=0.1, slots=1, builder=None):
    return create_app(
        settings=settings(has_llm=configured, answer_timeout=timeout, max_concurrent_requests=slots),
        corpus_builder=builder or (lambda _settings: CORPUS),
        agent_factory=lambda _corpus, _settings: agent or FakeAgent(),
    )


def await_status(client, expected="ok"):
    for _ in range(100):
        response = client.get("/health")
        if response.json()["status"] == expected:
            return response.json()
        time.sleep(0.01)
    pytest.fail(f"Service did not reach {expected}")


@pytest.fixture
def client():
    with TestClient(fresh_app()) as c:
        await_status(c)
        yield c


def test_health_and_answer_contract(client):
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["retriever_ready"]
    assert health.json()["answer_timeout"] == 0.1
    response = client.post("/ask", json={"question": "warfarin contraindications?"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "answered"
    assert body["claims"][0]["passage_ids"] == ["warfarin-4-1"]
    assert body["disclaimer"] and body["grounding"]["verdict"] == "grounded"
    assert body["citations"][0]["passage_id"] == "warfarin-4-1"
    assert body["citations"][0]["claim_ids"] == ["c1"]
    assert "contraindicated" in body["citations"][0]["excerpt"]


def test_blank_question_is_rejected(client):
    assert client.post("/ask", json={"question": "   "}).status_code == 422
    assert client.post("/ask", json={"question": ""}).status_code == 422


def test_warming_up_blocks_questions():
    entered, release = threading.Event(), threading.Event()

    def slow_build(_settings):
        entered.set()
        release.wait(2)
        return CORPUS

    with TestClient(fresh_app(builder=slow_build)) as client:
        assert entered.wait(1)
        assert client.get("/health").json()["status"] == "starting"
        assert client.post("/ask", json={"question": "warfarin?"}).status_code == 503
        release.set()
        assert await_status(client)["retriever_ready"]


def test_no_key_degrades_immediately_without_building_index():
    calls = []
    with TestClient(fresh_app(configured=False, builder=lambda _settings: calls.append(1))) as client:
        health = client.get("/health").json()
        assert health["status"] == "degraded" and not health["llm_configured"]
        assert not health["retriever_ready"]
        assert client.post("/ask", json={"question": "warfarin?"}).status_code == 503
    assert not calls


def test_timeout_keeps_capacity_until_worker_exits():
    entered, release = threading.Event(), threading.Event()
    events = []

    class SlowAgent(FakeAgent):
        def answer(self, question, *, cancel_event=None, deadline=None):
            events.append(cancel_event)
            entered.set()
            release.wait(2)
            return super().answer(question, cancel_event=cancel_event, deadline=deadline)

    with TestClient(fresh_app(agent=SlowAgent())) as client:
        await_status(client)
        try:
            assert client.post("/ask", json={"question": "warfarin?"}).status_code == 504
            assert entered.is_set() and events[0].is_set()
            assert client.app.state.runtime.active_count == 1
            assert client.post("/ask", json={"question": "warfarin?"}).status_code == 503
        finally:
            release.set()
        for _ in range(100):
            if client.app.state.runtime.active_count == 0:
                break
            time.sleep(0.01)
        assert client.app.state.runtime.active_count == 0
        assert client.post("/ask", json={"question": "warfarin?"}).status_code == 200


@pytest.mark.parametrize("failure,status", [
    (RuntimeError("secret-key-should-never-appear"), 500),
    (TimeoutError("provider request expired"), 504),
])
def test_errors_do_not_expose_provider_message(failure, status):
    class FailingAgent:
        def answer(self, question, **kwargs):
            raise failure

    with TestClient(fresh_app(agent=FailingAgent())) as client:
        await_status(client)
        response = client.post("/ask", json={"question": "warfarin?"})
        assert response.status_code == status
        assert str(failure) not in response.text


def test_provider_content_filter_is_clear_without_leaking_details():
    class FilteredAgent:
        def answer(self, question, **kwargs):
            raise BadRequestError("filtered", response=httpx.Response(
                400, request=httpx.Request("POST", "https://provider.invalid")),
                body={"message": "ContentPolicyViolationError: private-routing-secret", "code": "400"})

    with TestClient(fresh_app(agent=FilteredAgent())) as client:
        await_status(client)
        response = client.post("/ask", json={"question": "adversarial prompt"})
        assert response.status_code == 422
        assert "content policy" in response.json()["detail"]
        assert "private-routing-secret" not in response.text


def test_shutdown_prevents_late_index_publication():
    entered, release = threading.Event(), threading.Event()
    agents = []

    def slow_build(_settings):
        entered.set()
        release.wait(2)
        return CORPUS

    app = create_app(settings=settings(), corpus_builder=slow_build,
                     agent_factory=lambda corpus, cfg: agents.append(1))
    with TestClient(app) as client:
        assert entered.wait(1)
        assert client.get("/health").json()["status"] == "starting"
    release.set()
    app.state.runtime.builder.join(1)
    assert not app.state.runtime.builder.is_alive()
    assert app.state.runtime.snapshot().status == "degraded"
    assert not agents


def test_independent_app_instances_do_not_share_readiness():
    entered, release = threading.Event(), threading.Event()

    def slow_build(_settings):
        entered.set()
        release.wait(2)
        return CORPUS

    with TestClient(fresh_app(builder=slow_build)) as warming:
        assert entered.wait(1)
        with TestClient(fresh_app()) as ready:
            await_status(ready)
            assert warming.get("/health").json()["status"] == "starting"
            assert ready.get("/health").json()["status"] == "ok"
        release.set()
