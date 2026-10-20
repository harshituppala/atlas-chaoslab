"""Deterministic ASGI concurrency, failure and cancellation admission checks."""

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from atlas.api import create_app
from atlas.limits import BodyLimit


def scope(method="POST"):
    return {"type": "http", "method": method, "path": "/api/runs", "headers": []}


async def response(send, status=200):
    await send({"type": "http.response.start", "status": status, "headers": []})
    await send({"type": "http.response.body", "body": b"ok"})


async def body():
    return {"type": "http.request", "body": b"synthetic body", "more_body": False}


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH"])
def test_saturation_rejects_before_receive_and_health_bypasses_it(method):
    async def exercise():
        entered, release = asyncio.Event(), asyncio.Event()
        reads, responses = [], []

        async def app(request, receive, send):
            if request["method"] == "GET":
                return await response(send)
            entered.set()
            await release.wait()
            await response(send)

        async def send(message):
            responses.append(message)

        async def forbidden_receive():
            reads.append("called")
            raise AssertionError("Rejected request body was read")

        limiter = BodyLimit(app, maximum_inflight=1)
        first_scope = scope(method)
        first = asyncio.create_task(limiter(first_scope, body, send))
        await entered.wait()
        await limiter(scope(method), forbidden_receive, send)
        assert responses[0]["status"] == 503
        assert (b"retry-after", b"1") in responses[0]["headers"]
        await limiter(scope("GET"), forbidden_receive, send)
        assert responses[-2]["status"] == 200
        release.set()
        await first
        assert "atlas.body" not in first_scope
        assert reads == []
        # No leaked slot: the same middleware instance accepts subsequent work.
        await limiter(scope(method), body, send)
        assert responses[-2]["status"] == 200

    asyncio.run(exercise())


@pytest.mark.parametrize(
    "failure", ["oversize", "chunks", "timeout", "disconnect", "receive", "app", "send", "cancel"]
)
def test_all_exit_paths_release_capacity_and_remove_raw_scope_body(failure):
    async def exercise():
        mode = failure
        entered = asyncio.Event()
        responses = []

        async def receive():
            if mode == "oversize":
                return {"type": "http.request", "body": b"x" * 20, "more_body": False}
            if mode == "chunks":
                return {"type": "http.request", "body": b"", "more_body": True}
            if mode == "timeout":
                await asyncio.sleep(0.1)
            if mode == "disconnect":
                return {"type": "http.disconnect"}
            if mode == "receive":
                raise OSError("private receive failure")
            return await body()

        async def app(request, receive, send):
            if mode == "app":
                raise RuntimeError("private application failure")
            if mode == "cancel":
                entered.set()
                await asyncio.Event().wait()
            await response(send)

        async def send(message):
            if mode == "send":
                raise OSError("private send failure")
            responses.append(message)

        limiter = BodyLimit(
            app, maximum=15, maximum_chunks=2, timeout_seconds=0.002, maximum_inflight=1
        )
        request = scope()
        if mode == "cancel":
            task = asyncio.create_task(limiter(request, receive, send))
            await entered.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        elif mode in {"app", "receive", "send"}:
            with pytest.raises((OSError, RuntimeError)):
                await limiter(request, receive, send)
        else:
            await limiter(request, receive, send)
            if mode != "disconnect":
                assert (
                    responses[0]["status"] == {"oversize": 413, "chunks": 413, "timeout": 408}[mode]
                )
        assert "atlas.body" not in request
        mode = "ok"
        await limiter(scope(), receive, send)
        assert responses[-2]["status"] == 200

    asyncio.run(exercise())


def test_cancellation_during_body_receive_releases_capacity():
    async def exercise():
        entered = asyncio.Event()
        messages = []

        async def app(request, receive, send):
            await response(send)

        async def blocked():
            entered.set()
            await asyncio.Event().wait()

        async def send(message):
            messages.append(message)

        limiter = BodyLimit(app, maximum_inflight=1)
        task = asyncio.create_task(limiter(scope(), blocked, send))
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await limiter(scope(), body, send)
        assert messages[0]["status"] == 200

    asyncio.run(exercise())


@pytest.mark.parametrize("capacity", [0, -1, 129, True, 1.5])
def test_capacity_is_a_bounded_positive_integer(capacity):
    with pytest.raises(ValueError):
        BodyLimit(None, maximum_inflight=capacity)


def test_real_api_saturation_response_retains_privacy_headers(tmp_path):
    async def exercise():
        app = create_app(database_url=f"sqlite:///{tmp_path}/admission.db", principals={})
        blocked, release = asyncio.Event(), asyncio.Event()
        entered = 0

        async def receive():
            nonlocal entered
            entered += 1
            if entered == 8:
                blocked.set()
            await release.wait()
            return await body()

        async def send(message):
            pass

        tasks = [asyncio.create_task(app(scope(), receive, send)) for _ in range(8)]
        try:
            await asyncio.wait_for(blocked.wait(), timeout=2)
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://local"
            ) as client:
                rejected = await client.post("/api/runs", content="not consumed")
                assert rejected.status_code == 503
                assert rejected.headers["cache-control"] == "no-store"
                assert rejected.headers["x-content-type-options"] == "nosniff"
                assert rejected.headers["retry-after"] == "1"
                assert (await client.get("/healthz")).status_code == 200
        finally:
            for task in tasks:
                task.cancel()
            results = await asyncio.gather(*tasks, return_exceptions=True)
            assert all(isinstance(result, asyncio.CancelledError) for result in results)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://local") as client:
            # Reclaimed slots allow the ordinary authentication path again.
            assert (await client.post("/api/jobs", json={})).status_code == 401

    asyncio.run(exercise())
