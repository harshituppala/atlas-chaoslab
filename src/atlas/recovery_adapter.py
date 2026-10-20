"""Failure injection owned by ATLAS; expected outcomes stay in CHAOSLAB fixtures."""

import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .execution import execute
from .jobs import JobQueue, LostLease
from .store import Store


class Clock:
    def __init__(self):
        self.time = datetime(2030, 1, 1, tzinfo=UTC)

    def __call__(self):
        return self.time

    def advance(self, seconds):
        self.time += timedelta(seconds=seconds)


def run(inputs, fault=None):
    scenario = inputs["scenario"]
    body = inputs["documents"]
    base = Path(".cache/recovery")
    base.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=base) as directory:
        clock = Clock()
        queue = JobQueue(Store("sqlite:///" + str(Path(directory) / "jobs.db")), clock)
        attempts = (
            1 if scenario == "last_attempt_crash" else 2 if scenario == "retry_ceiling" else 3
        )
        job = queue.submit(
            "fixture", "fixture-analyst", "case-idempotency-key", body, max_attempts=attempts
        )
        observations = {}
        if scenario == "competing_workers":
            with ThreadPoolExecutor(max_workers=2) as pool:
                claims = list(pool.map(lambda _: queue.claim(), range(2)))
            observations["owners"] = sum(c is not None for c in claims)
        else:
            claim = queue.claim(5)
            if scenario == "expired_worker":
                clock.advance(6)
                new = queue.claim(5)
                try:
                    queue.complete(claim, execute(body))
                    observations["stale_worker_rejected"] = False
                except LostLease:
                    observations["stale_worker_rejected"] = True
                queue.complete(new, execute(body))
            elif scenario == "cancel_running":
                queue.cancel("fixture", "fixture-reviewer", job["id"])
                try:
                    queue.complete(claim, execute(body))
                    observations["stale_worker_rejected"] = False
                except LostLease:
                    observations["stale_worker_rejected"] = True
            elif scenario == "publication_rollback":
                original = queue.store.persist_snapshot

                def injected(conn, *args):
                    original(conn, *args)
                    raise RuntimeError("Injected storage interruption")

                queue.store.persist_snapshot = injected
                try:
                    queue.complete(claim, execute(body))
                except RuntimeError:
                    pass
                observations["results_after_interruption"] = len(queue.store.list("fixture"))
                observations["status_after_interruption"] = queue.get("fixture", job["id"])[
                    "status"
                ]
                queue.store.persist_snapshot = original
                queue.complete(claim, execute(body))
            elif scenario == "retry_ceiling":
                queue.fail(claim, "upstream_unavailable", True)
                observations["premature_retry_blocked"] = queue.claim() is None
                clock.advance(2)
                queue.fail(queue.claim(), "upstream_unavailable", True)
                clock.advance(60)
                observations["exhausted_retry_blocked"] = queue.claim() is None
            elif scenario == "last_attempt_crash":
                clock.advance(6)
                queue.claim()
            elif scenario == "forged_review":
                output = execute(body)
                output["assessments"][0]["review_state"] = "approved"
                try:
                    queue.complete(claim, output)
                    observations["self_approval_rejected"] = False
                except ValueError:
                    observations["self_approval_rejected"] = True
            else:
                raise ValueError("Unknown recovery scenario")
        status = queue.get("fixture", job["id"])
        observations.update(
            status=status["status"],
            attempts=status["attempts"],
            results=len(queue.store.list("fixture")),
        )
        return {"observations": observations, "events": queue.events("fixture", job["id"])}
