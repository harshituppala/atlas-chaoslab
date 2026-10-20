import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_api import PRINCIPALS, auth

from atlas.api import create_app
from atlas.execution import execute
from atlas.jobs import JobQueue, LostLease
from atlas.store import Store
from atlas.worker import process_once


class Clock:
    def __init__(self):
        self.time = datetime(2030, 1, 1, tzinfo=UTC)

    def __call__(self):
        return self.time

    def advance(self, seconds):
        self.time += timedelta(seconds=seconds)


@pytest.fixture
def body():
    return json.loads(Path("datasets/demo.json").read_text())


@pytest.fixture
def queue(tmp_path):
    clock = Clock()
    return JobQueue(Store("sqlite:///" + str(tmp_path / "jobs.db")), clock)


def test_recovery_after_expired_lease_rejects_old_result(queue, body):
    job = queue.submit("tenant", "analyst", "test-key-0001", body)
    original = queue.claim(lease_seconds=5)
    assert queue.claim(5) is None
    queue.clock.advance(6)
    recovered = queue.claim(5)
    assert recovered.id == original.id and recovered.attempts == 2
    with pytest.raises(LostLease):
        queue.complete(original, execute(body))
    result = queue.complete(recovered, execute(body))
    assert queue.get("tenant", job["id"])["result_id"] == result
    assert len(queue.store.list("tenant")) == 1
    with pytest.raises(LostLease):
        queue.complete(recovered, execute(body))


def test_simultaneous_claims_have_one_owner(queue, body):
    queue.submit("tenant", "analyst", "test-key-0001", body)
    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(lambda _: queue.claim(), range(2)))
    assert sum(c is not None for c in claims) == 1
    assert queue.get("tenant", next(c for c in claims if c).id)["attempts"] == 1


def test_cancel_running_job_revokes_publication(queue, body):
    job = queue.submit("tenant", "analyst", "test-key-0001", body)
    claim = queue.claim()
    queue.cancel("tenant", "reviewer", job["id"])
    assert queue.cancel("tenant", "reviewer", job["id"])["status"] == "cancelled"
    with pytest.raises(LostLease):
        queue.heartbeat(claim)
    with pytest.raises(LostLease):
        queue.complete(claim, execute(body))
    assert queue.store.list("tenant") == []
    assert sum(e["action"] == "job.cancelled" for e in queue.events("tenant", job["id"])) == 1


def test_retries_obey_backoff_and_attempt_ceiling(queue, body):
    job = queue.submit("tenant", "analyst", "test-key-0001", body, max_attempts=2)
    claim = queue.claim()
    queue.fail(claim, "upstream_unavailable", True)
    assert queue.get("tenant", job["id"])["status"] == "retry_wait"
    assert queue.claim() is None
    queue.clock.advance(2)
    claim = queue.claim()
    queue.fail(claim, "upstream_unavailable", True)
    assert queue.get("tenant", job["id"])["status"] == "failed"
    queue.clock.advance(1000)
    assert queue.claim() is None


def test_crashed_final_attempt_becomes_terminal(queue, body):
    job = queue.submit("tenant", "analyst", "test-key-0001", body, max_attempts=1)
    queue.claim(1)
    queue.clock.advance(2)
    assert queue.claim() is None
    status = queue.get("tenant", job["id"])
    assert status["status"] == "failed" and status["error_code"] == "attempts_exhausted"


def test_atomic_publication_rolls_back_on_storage_error(queue, body, monkeypatch):
    job = queue.submit("tenant", "analyst", "test-key-0001", body)
    claim = queue.claim()
    original = queue.store.persist_snapshot

    def crash(conn, *args):
        original(conn, *args)
        raise RuntimeError("Injected failure after result insert")

    monkeypatch.setattr(queue.store, "persist_snapshot", crash)
    with pytest.raises(RuntimeError):
        queue.complete(claim, execute(body))
    assert queue.get("tenant", job["id"])["status"] == "running"
    assert queue.store.list("tenant") == []
    assert all(e["action"] != "job.succeeded" for e in queue.events("tenant", job["id"]))
    monkeypatch.setattr(queue.store, "persist_snapshot", original)
    queue.complete(claim, execute(body))
    assert len(queue.store.list("tenant")) == 1


def test_worker_cannot_approve_or_alter_source(queue, body):
    queue.submit("tenant", "analyst", "test-key-0001", body)
    claim = queue.claim()
    payload = execute(body)
    payload["assessments"][0]["review_state"] = "approved"
    with pytest.raises(ValueError):
        queue.complete(claim, payload)
    payload = execute(body)
    payload["assessments"][0]["draft"] = "We guarantee every requirement is satisfied."
    with pytest.raises(ValueError):
        queue.complete(claim, payload)
    payload = execute(body)
    payload["documents"][0]["text"] = "altered"
    with pytest.raises(ValueError):
        queue.complete(claim, payload)
    assert queue.store.list("tenant") == []


def test_worker_classifies_failures_without_publishing_secrets(queue, body):
    job = queue.submit("tenant", "analyst", "test-key-0001", body)

    def fail(_):
        raise TimeoutError("secret from upstream")

    assert process_once(queue, fail)
    status = queue.get("tenant", job["id"])
    assert status["status"] == "retry_wait" and status["error_code"] == "upstream_unavailable"
    assert "secret" not in json.dumps(status, default=str)
    queue.clock.advance(2)
    assert process_once(queue)
    assert queue.get("tenant", job["id"])["status"] == "succeeded"


def test_hard_process_crash_and_new_worker_recovery(tmp_path, body):
    url = "sqlite:///" + str(tmp_path / "crash.db")
    clock = Clock()
    queue = JobQueue(Store(url), clock)
    job = queue.submit("tenant", "analyst", "test-key-0001", body)
    code = """import os,sys
from datetime import datetime,timezone
from atlas.store import Store
from atlas.jobs import JobQueue
queue=JobQueue(Store(sys.argv[1]),lambda:datetime(2030,1,1,tzinfo=timezone.utc))
assert queue.claim(1) is not None
os._exit(17)
"""
    child = subprocess.run(
        [sys.executable, "-c", code, url],
        env={**__import__("os").environ, "PYTHONPATH": "src"},
        timeout=10,
    )
    assert child.returncode == 17
    clock.advance(2)
    restarted = JobQueue(Store(url), clock)
    assert process_once(restarted)
    assert restarted.get("tenant", job["id"])["status"] == "succeeded"
    assert len(restarted.store.list("tenant")) == 1


def test_job_api_isolation_idempotency_and_visibility(tmp_path, body):
    app = create_app("sqlite:///" + str(tmp_path / "api.db"), PRINCIPALS)
    with TestClient(app) as client:
        assert client.post("/api/jobs", json=body, headers=auth("viewer-token")).status_code == 403
        first = client.post("/api/jobs", json=body, headers=auth())
        assert first.status_code == 202
        job = first.json()
        assert "lease_token" not in job and "input" not in job
        assert client.post("/api/jobs", json=body, headers=auth()).json()["id"] == job["id"]
        assert client.get("/api/jobs/" + job["id"], headers=auth("other-token")).status_code == 404
        assert (
            client.post(
                "/api/jobs/" + job["id"] + "/cancel", headers=auth("other-token")
            ).status_code
            == 404
        )
        assert client.get("/api/jobs", headers=auth("other-token")).json() == []
        assert process_once(app.state.queue)
        status = client.get("/api/jobs/" + job["id"], headers=auth()).json()
        assert status["status"] == "succeeded"
        assert client.get("/api/runs/" + status["result_id"], headers=auth()).status_code == 200
        assert client.post("/api/jobs/" + job["id"] + "/cancel", headers=auth()).status_code == 409
        body["rfp"]["text"] += "different"
        assert client.post("/api/jobs", json=body, headers=auth()).status_code == 409


def test_request_byte_limit_before_json_parsing(tmp_path):
    app = create_app("sqlite:///" + str(tmp_path / "limits.db"), PRINCIPALS)
    with TestClient(app) as client:
        response = client.post(
            "/api/jobs",
            content=b"x" * 1_500_001,
            headers={**auth(), "Content-Type": "application/json"},
        )
        assert response.status_code == 413


def test_execution_subprocess_has_hard_deadline(body):
    from atlas.worker import execute_isolated

    with pytest.raises(TimeoutError):
        execute_isolated(body, timeout_seconds=0.001)


def test_oversized_analysis_is_terminal_not_a_retry_loop(queue, body):
    body["rfp"]["text"] = "The vendor must " + "x" * 5000
    job = queue.submit("tenant", "analyst", "test-key-0001", body)
    assert process_once(queue)
    status = queue.get("tenant", job["id"])
    assert status["status"] == "failed"
    assert status["error_code"] == "resource_budget_exceeded"
    assert status["attempts"] == 1


def test_publication_uses_stored_input_not_mutated_worker_copy(queue, body):
    job = queue.submit("tenant", "analyst", "test-key-0001", body)
    claim = queue.claim()
    claim.input["rfp"]["text"] = "Vendor must promise perfect service."
    with pytest.raises(ValueError):
        queue.complete(claim, execute(claim.input))
    assert queue.get("tenant", job["id"])["status"] == "running"
    assert queue.store.list("tenant") == []
