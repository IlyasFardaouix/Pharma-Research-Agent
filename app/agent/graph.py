"""Compile the research workflow and run it with isolated request budgets."""
from __future__ import annotations

import time
from threading import Event

from langchain_openai import ChatOpenAI
from langgraph.errors import GraphRecursionError
from langgraph.graph import END, StateGraph
from openai import BadRequestError

from app.execution import AgentBudgetExceeded, RunBudget, current_budget
from app.agent.nodes import (
    agent_node, critic_node, finalize_node, plan_node, route_after_agent,
    route_after_critic, route_after_tools, tools_node,
)
from app.agent.state import AgentState
from app.config import Settings
from app.models import AnswerResponse, GroundingReport, public_answer
from app.rag.index import CorpusIndex
from app.tools.registry import build_tools

RECURSION_LIMIT = 80


def _make_llm(settings: Settings, omit_temperature: bool = False) -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.openai_model,
        api_key=settings.openai_api_key or "missing",
        base_url=settings.openai_base_url or None,
        timeout=settings.request_timeout,
        max_retries=0,
        temperature=None if omit_temperature else settings.temperature,
        max_completion_tokens=settings.max_completion_tokens,
        use_responses_api=False,
    )


class _BoundedModel:
    """Count every invocation, including the sole explicit compatibility retry."""

    def __init__(self, model, fallback, settings: Settings):
        self.model, self.fallback, self.settings = model, fallback, settings

    def invoke(self, messages):
        size = sum(len(m.model_dump_json()) for m in messages)
        if size > self.settings.max_context_chars:
            raise AgentBudgetExceeded("Conversation exceeded the context budget.")

        def call(model):
            budget = current_budget.get()
            remaining = budget.take_llm() if budget else self.settings.request_timeout
            result = model.invoke(messages, timeout=min(remaining, self.settings.request_timeout))
            if budget:
                budget.check()
            return result

        try:
            return call(self.model)
        except BadRequestError as exc:
            # Only a provider 400 naming this parameter permits retry.
            # No shared graph mutation, and no replay of earlier paid calls.
            body = exc.body if isinstance(exc.body, dict) else {}
            error = body.get("error", body)
            if self.settings.temperature is not None and isinstance(error, dict) and error.get("param") == "temperature":
                return call(self.fallback)
            raise


def build_graph(corpus: CorpusIndex, settings: Settings, omit_temperature: bool = False, *, llm=None, critic_llm=None):
    supplied = llm is not None
    llm = llm if supplied else _make_llm(settings, omit_temperature)
    fallback = llm if supplied else _make_llm(settings, True)
    tools, handlers = build_tools(corpus)
    plain = _BoundedModel(llm, fallback, settings)
    reviewer = _BoundedModel(critic_llm, critic_llm, settings) if critic_llm is not None else plain
    bound = _BoundedModel(llm.bind_tools(tools), fallback.bind_tools(tools), settings)
    graph = StateGraph(AgentState)
    graph.add_node("planner", lambda s: plan_node(s, plain))
    graph.add_node("agent", lambda s: agent_node(s, bound))
    graph.add_node("tools", lambda s: tools_node(s, handlers))
    graph.add_node("critic", lambda s: critic_node(s, reviewer, settings))
    graph.add_node("finalize", finalize_node)
    graph.set_entry_point("planner")
    graph.add_edge("planner", "agent")
    graph.add_conditional_edges("agent", route_after_agent, {"tools": "tools", "critic": "critic"})
    graph.add_conditional_edges("tools", route_after_tools, {"agent": "agent", "finalize": "finalize"})
    graph.add_conditional_edges("critic", route_after_critic, {"revise": "agent", "finalize": "finalize"})
    graph.add_edge("finalize", END)
    return graph.compile()


class PharmaAgent:
    def __init__(self, corpus: CorpusIndex, settings: Settings):
        self.corpus, self.settings = corpus, settings
        self.graph = build_graph(corpus, settings)

    def answer(self, question: str, *, cancel_event: Event | None = None,
               deadline: float | None = None) -> AnswerResponse:
        token = current_budget.set(RunBudget(
            deadline=deadline if deadline is not None else time.monotonic() + self.settings.answer_timeout,
            cancel_event=cancel_event if cancel_event is not None else Event(),
            max_llm_calls=self.settings.max_llm_calls,
            max_tool_calls=self.settings.max_tool_calls,
        ))
        final: dict = {"question": question}
        try:
            # Preserve plan/trace on a later limit, never an unreviewed draft.
            for state in self.graph.stream(final, config={"recursion_limit": RECURSION_LIMIT}, stream_mode="values"):
                final = state
        except (GraphRecursionError, AgentBudgetExceeded) as exc:
            final = dict(final)
            final["grounding"] = GroundingReport(verdict="ungrounded", supported=False,
                flags=["Agent step budget exhausted." if isinstance(exc, GraphRecursionError) else str(exc)])
            final.update(finalize_node(final))
        finally:
            current_budget.reset(token)
        grounding = final.get("grounding")
        return public_answer(AnswerResponse(
            answer=final.get("draft_answer", ""), citations=final.get("citations", []),
            status=final.get("answer_status", "abstained"), claims=final.get("claims", []),
            response_mode=final.get("response_mode", "source_excerpts"),
            numeric_comparisons=final.get("numeric_comparisons", []),
            comparison_scope=final.get("comparison_scope"),
            common_terms=final.get("common_terms", []),
            plan=final.get("plan", []), tool_trace=final.get("tool_trace", []),
            grounding=grounding, warnings=list(grounding.flags) if grounding else [],
        ))
