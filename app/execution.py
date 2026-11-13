"""Shared per-request execution limits for retrieval and workflow calls."""
from __future__ import annotations

import time
from contextvars import ContextVar
from dataclasses import dataclass
from threading import Event


class AgentBudgetExceeded(RuntimeError):
    """A request must stop before another provider/tool call."""


@dataclass
class RunBudget:
    deadline: float
    cancel_event: Event
    max_llm_calls: int
    max_tool_calls: int
    llm_calls: int = 0
    tool_calls: int = 0

    def check(self) -> float:
        remaining = self.deadline - time.monotonic()
        if self.cancel_event.is_set() or remaining <= 0:
            raise AgentBudgetExceeded("Request cancelled or time budget exhausted.")
        return remaining

    def take_llm(self) -> float:
        remaining = self.check()
        if self.llm_calls >= self.max_llm_calls:
            raise AgentBudgetExceeded("Language-model call budget exhausted.")
        self.llm_calls += 1
        return remaining

    def take_tool(self) -> None:
        self.check()
        if self.tool_calls >= self.max_tool_calls:
            raise AgentBudgetExceeded("Tool-call budget exhausted.")
        self.tool_calls += 1


current_budget: ContextVar[RunBudget | None] = ContextVar("pharma_run_budget", default=None)
