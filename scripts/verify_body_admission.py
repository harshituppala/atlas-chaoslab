"""Measured in-process ASGI saturation diagnostic; no sockets, LLM calls or client data."""

import asyncio
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from atlas.limits import BodyLimit
from chaoslab.artifacts import publish_report


async def exercise():
    capacity, total, size = 8, 200, 65_536
    release, entered, refused = asyncio.Event(), asyncio.Event(), asyncio.Event()
    active = peak = accepted = rejected = reads = read_bytes = 0

    async def app(scope, receive, send):
        nonlocal active, peak, accepted
        if scope["method"] == "GET":
            await send({"type": "http.response.start", "status": 200, "headers": []})
            return
        accepted += 1
        active += 1
        peak = max(peak, active)
        if accepted == capacity:
            entered.set()
        assert scope["atlas.body"] == b"x" * size
        await release.wait()
        active -= 1
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    limiter = BodyLimit(app, maximum_inflight=capacity)
    outcomes, scopes = [], []

    def request(number):
        request_scope = {"type": "http", "method": "POST", "path": "/api/jobs", "headers": []}
        scopes.append(request_scope)

        async def receive():
            nonlocal reads, read_bytes
            reads += 1
            read_bytes += size
            return {"type": "http.request", "body": b"x" * size, "more_body": False}

        async def send(message):
            nonlocal rejected
            if message["type"] == "http.response.start":
                outcomes.append(message["status"])
                if message["status"] == 503:
                    rejected += 1
                    if rejected == total - capacity:
                        refused.set()

        return limiter(request_scope, receive, send)

    tasks = [asyncio.create_task(request(n)) for n in range(total)]
    try:
        await asyncio.wait_for(entered.wait(), 3)
        await asyncio.wait_for(refused.wait(), 3)
        health = []

        async def forbidden_receive():
            raise AssertionError("Health request attempted to buffer a body")

        async def health_send(message):
            health.append(message)

        await limiter({"type": "http", "method": "GET"}, forbidden_receive, health_send)
        assert health[0]["status"] == 200
        assert peak == capacity and reads == capacity and rejected == total - capacity
    finally:
        release.set()
        await asyncio.gather(*tasks)
    assert outcomes.count(200) == capacity and outcomes.count(503) == total - capacity
    assert all("atlas.body" not in scope for scope in scopes)
    # A full second wave proves that all eight slots are reusable.
    previous_reads = reads
    await asyncio.gather(*(request(n) for n in range(capacity)))
    assert reads - previous_reads == capacity and outcomes.count(200) == 2 * capacity
    return {
        "simultaneous_attempts": total,
        "capacity": capacity,
        "body_bytes_each": size,
        "accepted_first_wave": accepted - capacity,
        "rejected_first_wave": rejected,
        "peak_active_downstream": peak,
        "body_reads_first_wave": previous_reads,
        "body_bytes_read_first_wave": read_bytes - capacity * size,
        "health_status_during_saturation": 200,
        "second_wave_accepted": capacity,
        "scope_body_removed_after_response": True,
    }


def main():
    paths = ["src/atlas/limits.py", "scripts/verify_body_admission.py"]
    frozen = {p: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in paths}
    result = asyncio.run(exercise())
    if frozen != {p: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in paths}:
        raise ValueError("Body admission source changed during execution")
    report = {
        "schema_version": 1,
        "recorded_at": datetime.now(UTC).isoformat(),
        "scope": "Actual in-process synthetic ASGI concurrency with one limiter instance. Not a network/HTTP-server load test, measured RSS cap, distributed admission, tenant fairness or production DoS guarantee.",
        "observed": result,
        "source_sha256": frozen,
    }
    publish_report(Path("reports/body-admission.json"), report)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
