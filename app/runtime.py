"""Per-application lifecycle and bounded synchronous agent execution."""

from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from typing import Callable

logger = logging.getLogger("pharma-agent")


class ServiceUnavailable(RuntimeError):
    """The agent cannot accept a question right now."""


@dataclass(frozen=True)
class RuntimeSnapshot:
    status: str
    retriever_ready: bool
    corpus_files: int
    chunks: int
    llm_configured: bool
    answer_timeout: float
    startup_error: str | None


@dataclass(frozen=True)
class AnswerJob:
    future: Future
    cancel_event: threading.Event
    deadline: float

    def cancel(self) -> None:
        """Stop future work cooperatively; cancel only if still queued."""
        self.cancel_event.set()
        self.future.cancel()


class Runtime:
    """Own one app's index, worker pool, and active requests."""

    def __init__(self, settings, corpus_builder: Callable, agent_factory: Callable,
                 build_retries: int = 3):
        self.settings = settings
        self.corpus_builder = corpus_builder
        self.agent_factory = agent_factory
        self.build_retries = build_retries
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._slots = threading.BoundedSemaphore(settings.max_concurrent_requests)
        self._executor = ThreadPoolExecutor(
            max_workers=settings.max_concurrent_requests, thread_name_prefix="pharma-answer"
        )
        self._active: dict[Future, AnswerJob] = {}
        self._builder: threading.Thread | None = None
        self._status = "starting"
        self._startup_error: str | None = None
        self._corpus = None
        self._agent = None

    @property
    def builder(self) -> threading.Thread | None:
        return self._builder

    @property
    def active_count(self) -> int:
        with self._lock:
            return len(self._active)

    def snapshot(self) -> RuntimeSnapshot:
        with self._lock:
            corpus = self._corpus
            ready = corpus is not None and self._agent is not None
            return RuntimeSnapshot(
                status=self._status,
                retriever_ready=ready,
                corpus_files=corpus.num_files if corpus else 0,
                chunks=corpus.num_chunks if corpus else 0,
                llm_configured=self.settings.has_llm,
                answer_timeout=self.settings.answer_timeout,
                startup_error=self._startup_error,
            )

    def start(self) -> None:
        if not self.settings.has_llm:
            with self._lock:
                self._status = "degraded"
                self._startup_error = "LLM not configured."
            return
        self._builder = threading.Thread(target=self._build_index, daemon=True,
                                         name="pharma-index-builder")
        self._builder.start()

    def _build_index(self) -> None:
        for attempt in range(1, self.build_retries + 1):
            if self._stop.is_set():
                return
            try:
                corpus = self.corpus_builder(self.settings)
                if self._stop.is_set():
                    return
                agent = self.agent_factory(corpus, self.settings)
                with self._lock:
                    if self._stop.is_set():
                        return
                    self._corpus = corpus
                    self._agent = agent
                    self._status = "ok"
                    self._startup_error = None
                logger.info("Index ready: %d files, %d chunks.", corpus.num_files, corpus.num_chunks)
                return
            except Exception as exc:
                # Provider exception messages may contain URLs or credentials.
                logger.warning("Index build attempt %d/%d failed (%s).",
                               attempt, self.build_retries, type(exc).__name__)
                if attempt < self.build_retries and self._stop.wait(min(2 ** attempt, 10)):
                    return
        with self._lock:
            if not self._stop.is_set():
                self._status = "degraded"
                self._startup_error = "Index build failed; restart after checking server configuration."
        logger.error("Index build failed after %d attempts.", self.build_retries)

    @staticmethod
    def _run(agent, question: str, cancel_event: threading.Event, deadline: float):
        return agent.answer(question, cancel_event=cancel_event, deadline=deadline)

    def submit(self, question: str) -> AnswerJob:
        with self._lock:
            if self._stop.is_set():
                raise ServiceUnavailable("Service is shutting down.")
            if self._status == "starting":
                raise ServiceUnavailable("Service warming up; retry shortly.")
            if not self.settings.has_llm:
                raise ServiceUnavailable("LLM not configured.")
            if self._agent is None:
                raise ServiceUnavailable(self._startup_error or "Agent unavailable.")
            if not self._slots.acquire(blocking=False):
                raise ServiceUnavailable("Service is busy; retry shortly.")
            event = threading.Event()
            deadline = time.monotonic() + self.settings.answer_timeout
            try:
                future = self._executor.submit(self._run, self._agent, question, event, deadline)
            except RuntimeError:
                self._slots.release()
                raise ServiceUnavailable("Service is shutting down.") from None
            job = AnswerJob(future, event, deadline)
            self._active[future] = job
        # A fast future may already be done: adding the callback outside the lock
        # avoids deadlock when concurrent.futures invokes it immediately.
        future.add_done_callback(self._finish)
        return job

    def _finish(self, future: Future) -> None:
        with self._lock:
            if self._active.pop(future, None) is not None:
                self._slots.release()

    def shutdown(self) -> None:
        with self._lock:
            if self._stop.is_set():
                return
            self._stop.set()
            self._status = "degraded"
            self._agent = None
            self._corpus = None
            jobs = tuple(self._active.values())
        for job in jobs:
            job.cancel()
        self._executor.shutdown(wait=False, cancel_futures=True)
        if self._builder is not None:
            self._builder.join(timeout=0.1)
