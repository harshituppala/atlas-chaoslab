import asyncio

from atlas.limits import BodyLimit


def test_body_deadline_prevents_parser_execution():
    async def exercise():
        responses = []

        async def app(*_):
            raise AssertionError("Timed-out request reached parser")

        async def receive():
            await asyncio.sleep(0.1)
            return {"type": "http.request", "body": b"partial", "more_body": True}

        async def send(message):
            responses.append(message)

        await BodyLimit(app, timeout_seconds=0.001)(
            {"type": "http", "method": "POST"}, receive, send
        )
        assert responses[0]["status"] == 408

    asyncio.run(exercise())


def test_empty_chunk_flood_is_bounded_without_accumulating_bytes():
    async def exercise():
        responses, calls = [], 0

        async def app(*_):
            raise AssertionError("Chunk flood reached parser")

        async def receive():
            nonlocal calls
            calls += 1
            return {"type": "http.request", "body": b"", "more_body": True}

        async def send(message):
            responses.append(message)

        await BodyLimit(app, maximum_chunks=3)({"type": "http", "method": "POST"}, receive, send)
        assert calls == 4 and responses[0]["status"] == 413

    asyncio.run(exercise())


def test_chunked_upload_is_available_without_altering_downstream_body():
    async def exercise():
        parts = iter(
            [
                {"type": "http.request", "body": b"first", "more_body": True},
                {"type": "http.request", "body": b"second", "more_body": False},
            ]
        )

        async def receive():
            return next(parts)

        async def app(scope, receive, send):
            assert scope["atlas.body"] == b"firstsecond"
            assert (await receive())["body"] == b"firstsecond"

        async def send(_):
            pass

        await BodyLimit(app)({"type": "http", "method": "POST"}, receive, send)

    asyncio.run(exercise())
