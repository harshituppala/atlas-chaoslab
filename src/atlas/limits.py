"""Enforce a byte budget before JSON parsing, including chunked requests."""

import asyncio
import threading

from starlette.responses import JSONResponse


class BodyLimit:
    def __init__(
        self,
        app,
        maximum=1_500_000,
        timeout_seconds=10,
        maximum_chunks=10_000,
        maximum_inflight=8,
    ):
        if type(maximum_inflight) is not int or not 1 <= maximum_inflight <= 128:
            raise ValueError("Invalid body admission capacity")
        self.slots = threading.BoundedSemaphore(maximum_inflight)
        self.app, self.maximum = app, maximum
        self.timeout, self.maximum_chunks = timeout_seconds, maximum_chunks

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] not in {"POST", "PUT", "PATCH"}:
            return await self.app(scope, receive, send)
        if not self.slots.acquire(blocking=False):
            return await JSONResponse(
                {"detail": "Request body capacity unavailable"},
                status_code=503,
                headers={"Retry-After": "1"},
            )(scope, receive, send)
        try:
            await self.consume(scope, receive, send)
        finally:
            # Hold admission through downstream processing while raw body references are live.
            scope.pop("atlas.body", None)
            self.slots.release()

    async def consume(self, scope, receive, send):
        chunks, total, messages = [], 0, 0
        try:
            async with asyncio.timeout(self.timeout):
                while True:
                    message = await receive()
                    if message["type"] == "http.disconnect":
                        return
                    chunk = message.get("body", b"")
                    total += len(chunk)
                    messages += 1
                    if total > self.maximum or messages > self.maximum_chunks:
                        response = JSONResponse(
                            {"detail": "Request body budget exceeded"}, status_code=413
                        )
                        return await response(scope, receive, send)
                    if chunk:
                        chunks.append(chunk)
                    if not message.get("more_body", False):
                        break
        except TimeoutError:
            return await JSONResponse(
                {"detail": "Request body deadline exceeded"}, status_code=408
            )(scope, receive, send)
        consumed = False
        body = b"".join(chunks)
        chunks.clear()
        scope["atlas.body"] = body

        async def bounded_receive():
            nonlocal consumed
            if not consumed:
                consumed = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        await self.app(scope, bounded_receive, send)
