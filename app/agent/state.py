"""Typed state shared across the LangGraph nodes."""

from __future__ import annotations

from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

from app.models import Citation, GroundingReport, ToolCallTrace
from app.answer import AnswerClaim, DraftAnswer, NumericComparison
from app.rag.index import Passage


class AgentState(TypedDict, total=False):
    # Input
    question: str

    # Planning
    plan: list[str]

    # ReAct conversation (reducer appends new messages)
    messages: Annotated[list[BaseMessage], add_messages]

    # Evidence accumulated from tool calls
    retrieved: list[Passage]
    citations: list[Citation]
    tool_trace: list[ToolCallTrace]

    # Draft + review
    draft_answer: str
    grounding: GroundingReport
    revision_count: int
    should_revise: bool
    was_revised: bool
    response_error: str
    draft: DraftAnswer | None
    draft_error: str
    answer_status: str
    claims: list[AnswerClaim]
    response_mode: str
    comparison_scope: str | None
    common_terms: list[str]
    numeric_comparisons: list[NumericComparison]
