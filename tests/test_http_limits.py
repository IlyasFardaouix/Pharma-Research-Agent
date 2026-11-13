import asyncio

from app.http_limits import AskBodyLimit


def run_request(parts, *, headers=None, max_bytes=10):
    sent, called = [], []
    messages = iter({"type": "http.request", "body": part, "more_body": i < len(parts) - 1} for i, part in enumerate(parts))

    async def receive():
        return next(messages)

    async def send(message):
        sent.append(message)

    async def app(scope, receive, send):
        called.append(await receive())

    scope = {"type": "http", "path": "/ask", "method": "POST", "headers": headers or []}
    asyncio.run(AskBodyLimit(app, max_bytes=max_bytes)(scope, receive, send))
    return sent, called


def test_chunked_body_cannot_bypass_size_limit():
    sent, called = run_request([b"123456", b"789012"])
    assert sent[0]["status"] == 413 and not called


def test_large_content_length_rejected_before_reading():
    sent, called = run_request([], headers=[(b"content-length", b"1000000")])
    assert sent[0]["status"] == 413 and not called


def test_bounded_body_replayed_exactly_once():
    sent, called = run_request([b"abc", b"def"])
    assert not sent and called == [{"type": "http.request", "body": b"abcdef", "more_body": False}]
