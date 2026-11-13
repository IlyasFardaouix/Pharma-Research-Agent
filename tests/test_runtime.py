"""Runtime ownership and shutdown behavior without network calls."""

import threading
import time
from types import SimpleNamespace

import pytest

from app.runtime import Runtime, ServiceUnavailable


CORPUS = SimpleNamespace(num_files=1, num_chunks=2)


def config(*, slots=1, has_llm=True):
    return SimpleNamespace(max_concurrent_requests=slots, answer_timeout=1,
                           has_llm=has_llm)


def wait_ready(runtime):
    for _ in range(100):
        if runtime.snapshot().status == "ok":
            return
        time.sleep(0.01)
    pytest.fail("Runtime did not become ready")


def test_shutdown_signals_active_agent_and_rejects_new_work():
    entered, release = threading.Event(), threading.Event()
    observed = []

    class SlowAgent:
        def answer(self, question, *, cancel_event=None, deadline=None):
            observed.append(cancel_event)
            entered.set()
            release.wait(2)
            return question

    runtime = Runtime(config(), lambda _: CORPUS, lambda corpus, settings: SlowAgent())
    runtime.start()
    wait_ready(runtime)
    job = runtime.submit("question")
    assert entered.wait(1)
    try:
        runtime.shutdown()
        assert observed[0].is_set()
        assert runtime.snapshot().status == "degraded"
        with pytest.raises(ServiceUnavailable):
            runtime.submit("another")
    finally:
        release.set()
    assert job.future.result(timeout=2) == "question"
    assert runtime.active_count == 0


def test_executor_and_semaphore_bound_active_work():
    entered, release = threading.Event(), threading.Event()
    starts = []

    class SlowAgent:
        def answer(self, question, *, cancel_event=None, deadline=None):
            starts.append(question)
            if len(starts) == 2:
                entered.set()
            release.wait(2)
            return question

    runtime = Runtime(config(slots=2), lambda _: CORPUS, lambda corpus, settings: SlowAgent())
    runtime.start()
    wait_ready(runtime)
    try:
        first = runtime.submit("one")
        second = runtime.submit("two")
        assert entered.wait(1)
        assert runtime.active_count == 2
        with pytest.raises(ServiceUnavailable, match="busy"):
            runtime.submit("three")
    finally:
        release.set()
    assert first.future.result(timeout=2) == "one"
    assert second.future.result(timeout=2) == "two"
    runtime.shutdown()


def test_failed_build_is_explicitly_bounded_until_restart():
    calls = []

    def fail(_settings):
        calls.append(1)
        raise RuntimeError("provider-private-details")

    runtime = Runtime(config(), fail, lambda corpus, settings: object(), build_retries=1)
    runtime.start()
    runtime.builder.join(1)
    try:
        assert len(calls) == 1
        assert runtime.snapshot().status == "degraded"
        assert "provider-private-details" not in runtime.snapshot().startup_error
        with pytest.raises(ServiceUnavailable, match="restart"):
            runtime.submit("question")
    finally:
        runtime.shutdown()
