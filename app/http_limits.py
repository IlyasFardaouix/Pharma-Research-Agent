"""Bound the JSON body before FastAPI buffers and parses it, including chunked input."""
import asyncio


class AskBodyLimit:
    def __init__(self, app, max_bytes: int = 16384, receive_timeout: float = 10):
        self.app, self.max_bytes, self.receive_timeout = app, max_bytes, receive_timeout

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("path") != "/ask" or scope.get("method") != "POST":
            return await self.app(scope, receive, send)

        async def reject(status, detail):
            import json
            body = json.dumps({"detail": detail}).encode()
            await send({"type": "http.response.start", "status": status,
                        "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
            await send({"type": "http.response.body", "body": body})

        headers = dict(scope.get("headers", []))
        try:
            length = int(headers.get(b"content-length", b"0"))
        except ValueError:
            return await reject(400, "Invalid Content-Length.")
        if length < 0:
            return await reject(400, "Invalid Content-Length.")
        if length > self.max_bytes:
            return await reject(413, "Request body too large.")

        chunks, size = [], 0
        deadline = asyncio.get_running_loop().time() + self.receive_timeout
        while True:
            try:
                message = await asyncio.wait_for(receive(), max(0, deadline - asyncio.get_running_loop().time()))
            except TimeoutError:
                return await reject(408, "Request body timed out.")
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            size += len(chunk)
            if size > self.max_bytes:
                return await reject(413, "Request body too large.")
            chunks.append(chunk)
            if not message.get("more_body", False):
                break
        body = b"".join(chunks)
        delivered = False

        async def replay():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        await self.app(scope, replay, send)
