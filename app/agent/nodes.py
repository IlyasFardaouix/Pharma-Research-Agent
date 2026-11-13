"""Workflow nodes: collect evidence, validate typed claims, review, publish."""
from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from openai import APIError
from pydantic import ValidationError

from app.answer import DraftAnswer, DraftReview, GroundingReport
from app.execution import AgentBudgetExceeded, current_budget
from app.agent.grounding import draft_issues, parse_json_document, render_answer, review_report
from app.agent.prompts import AGENT_SYSTEM, CRITIC_SYSTEM, PLANNER_SYSTEM, revision_instruction
from app.agent.state import AgentState
from app.config import Settings
from app.models import ToolCallTrace
from app.tools.base import format_passages


def _text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            b if isinstance(b, str) else b["text"] for b in content
            if isinstance(b, str) or (isinstance(b, dict) and b.get("type") in {"text", "output_text"} and isinstance(b.get("text"), str))
        )
    return ""


def _summary(content: str, limit: int = 160) -> str:
    lines = content.strip().splitlines()
    return (lines[0] if lines else "")[:limit]


def _critic_evidence(retrieved: list, draft=None, budget: int = 60000) -> str:
    evidence = format_passages(retrieved)
    if len(evidence) > budget:
        raise AgentBudgetExceeded("Retrieved evidence exceeds the complete-review budget; narrow the question.")
    return evidence


def plan_node(state: AgentState, llm) -> dict:
    question = state["question"]
    try:
        response = llm.invoke([SystemMessage(content=PLANNER_SYSTEM), HumanMessage(content=question)])
        parsed = parse_json_document(_text(response.content))
        plan = [s.strip()[:500] for s in parsed[:8] if isinstance(s, str) and s.strip()] if isinstance(parsed, list) else []
    except (AgentBudgetExceeded, APIError):
        raise
    except (ValueError, TypeError, AttributeError):
        plan = []
    plan = plan or [question]
    return {"plan": plan, "messages": [SystemMessage(content=AGENT_SYSTEM),
        HumanMessage(content=f"Question: {question}\nPlan: {json.dumps(plan)}")],
        "retrieved": [], "citations": [], "tool_trace": [], "revision_count": 0,
        "should_revise": False, "draft": None, "draft_error": "", "response_error": ""}


def agent_node(state: AgentState, llm_with_tools) -> dict:
    response: AIMessage = llm_with_tools.invoke(state["messages"])
    calls = getattr(response, "tool_calls", None) or []
    if getattr(response, "invalid_tool_calls", None):
        return {"draft": None, "response_error": "Model emitted invalid tool arguments."}
    if response.response_metadata.get("finish_reason") in {"length", "content_filter"}:
        return {"draft": None, "response_error": "Model output was truncated or filtered."}
    if any(not isinstance(c.get("id"), str) or not c["id"] for c in calls) or len({c["id"] for c in calls}) != len(calls):
        return {"draft": None, "response_error": "Model emitted missing or duplicate tool-call IDs."}
    result = {"messages": [response], "response_error": "", "draft_error": "", "draft": None}
    if not calls:
        try:
            result["draft"] = DraftAnswer.model_validate(parse_json_document(_text(response.content)))
        except (ValueError, TypeError, ValidationError):
            result["draft_error"] = "Return the required JSON answer schema with unique claim IDs, text and exact passage_ids. No prose outside JSON."
    return result


def route_after_agent(state: AgentState) -> str:
    if state.get("response_error") or state.get("draft_error"):
        return "critic"
    return "tools" if getattr(state["messages"][-1], "tool_calls", None) else "critic"


def tools_node(state: AgentState, handlers: dict) -> dict:
    retrieved = list(state.get("retrieved", []))
    trace = list(state.get("tool_trace", []))
    seen = {p.chunk.id for p in retrieved}
    messages = []
    result_state = {"messages": messages, "retrieved": retrieved, "tool_trace": trace}
    for call in state["messages"][-1].tool_calls:
        budget = current_budget.get()
        try:
            if budget:
                budget.take_tool()
            name, args = call["name"], call.get("args") or {}
            handler = handlers.get(name)
            result = None
            if handler is None:
                content = "Unknown corpus tool. Use one of the advertised tool names."
            else:
                try:
                    result = handler(**args)
                    content = result.content
                except AgentBudgetExceeded:
                    raise
                except APIError:
                    raise  # provider failures belong to the HTTP error boundary
                except Exception:
                    content = "Tool failed. Check its argument schema or use another corpus tool."
            messages.append(ToolMessage(content=content, tool_call_id=call["id"], name=name))
            trace.append(ToolCallTrace(tool=name, args=args, result_summary=_summary(content)))
            if result is not None:
                for passage in result.passages:
                    if passage.chunk.id not in seen:
                        seen.add(passage.chunk.id)
                        retrieved.append(passage)
        except AgentBudgetExceeded as exc:
            # Preserve completed calls in this batch, then finish without replaying
            # a partially answered tool-call message to the provider.
            result_state.update(response_error=str(exc), grounding=GroundingReport(
                verdict="ungrounded", supported=False, flags=[str(exc)]))
            return result_state
    return result_state


def route_after_tools(state: AgentState) -> str:
    return "finalize" if state.get("response_error") else "agent"


def _review_result(state: AgentState, report: GroundingReport, settings: Settings) -> dict:
    revision = state.get("revision_count", 0)
    revise = report.verdict == "needs_revision" and revision < settings.max_revisions
    if report.verdict == "needs_revision" and not revise:
        report = report.model_copy(update={"verdict": "ungrounded", "supported": False})
    result = {"grounding": report, "should_revise": revise}
    if revise:
        result.update(revision_count=revision + 1, was_revised=True,
            messages=[HumanMessage(content=revision_instruction(report.flags))])
    return result


def critic_node(state: AgentState, llm, settings: Settings) -> dict:
    if state.get("response_error"):
        return {"grounding": GroundingReport(verdict="ungrounded", supported=False,
            flags=[state["response_error"]]), "should_revise": False}
    draft = state.get("draft")
    if draft is None:
        return _review_result(state, GroundingReport(verdict="needs_revision", supported=False,
            flags=[state.get("draft_error") or "No valid structured draft was produced."]), settings)
    if draft.status == "abstained":
        return {"grounding": GroundingReport(verdict="ungrounded", supported=False,
            notes=f"The agent abstained: {draft.abstention_reason}."), "should_revise": False}
    retrieved = state.get("retrieved", [])
    problems = draft_issues(draft, retrieved, question=state["question"])
    if not retrieved:
        problems.append("No corpus evidence was retrieved before answering.")
    if problems:
        return _review_result(state, GroundingReport(verdict="needs_revision", supported=False,
            flags=problems), settings)
    evidence = _critic_evidence(retrieved, budget=settings.max_evidence_chars)
    prompt = (f"QUESTION:\n{state['question']}\nPLAN:\n{json.dumps(state.get('plan', []))}\n"
        f"SOURCE SELECTION JSON (text is a literal focus, not the final answer):\n{draft.model_dump_json()}\n"
        f"SELECTED PUBLIC CONTEXT IDS:\n{json.dumps(list(dict.fromkeys(pid for claim in draft.claims for pid in claim.passage_ids)))}\n"
        f"FULL RETRIEVED EVIDENCE (only selected complete contexts will be published; unselected text cannot fill a missing answer component):\n{evidence}")
    try:
        response = llm.invoke([SystemMessage(content=CRITIC_SYSTEM), HumanMessage(content=prompt)])
        if response.response_metadata.get("finish_reason") in {"length", "content_filter"}:
            raise ValueError("incomplete review")
        review = DraftReview.model_validate(parse_json_document(_text(response.content)))
        report = review_report(draft, review, retrieved)
    except (AgentBudgetExceeded, APIError):
        raise
    except (ValueError, TypeError, ValidationError):
        report = GroundingReport(verdict="needs_revision", supported=False,
            flags=["Review was malformed or incomplete. A complete per-claim review with literal source quotes is required."])
    return _review_result(state, report, settings)


def route_after_critic(state: AgentState) -> str:
    return "revise" if state.get("should_revise") else "finalize"


def finalize_node(state: AgentState) -> dict:
    return render_answer(state.get("draft"), state.get("grounding"),
        state.get("retrieved", []), was_revised=state.get("was_revised", False),
        question=state.get("question", ""))
