import json
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_api import PRINCIPALS, auth
from test_model_jobs import spec

from atlas.execution import execute
from atlas.local_service import BaselineWorker, create_local_service
from atlas.models.intelligence import MODEL_PIPELINE_VERSION
from atlas.worker import process_once


def wait_until(predicate, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("Expected local lifecycle transition did not occur")


@pytest.fixture(autouse=True)
def local_environment(monkeypatch):
    for name in (
        "ATLAS_DATABASE_URL",
        "ATLAS_MODEL_JOB_SPEC",
        "ATLAS_ENABLE_BEDROCK_JOBS",
        "ATLAS_TOKEN_TRUST",
    ):
        monkeypatch.delenv(name, raising=False)


def test_real_child_completes_api_job_and_restart_retains_pending_review(tmp_path):
    path = tmp_path / "service.db"
    app = create_local_service(path, PRINCIPALS)
    body = json.loads(Path("datasets/demo.json").read_text())
    with TestClient(app) as client:
        assert client.get("/readyz").status_code == 200
        assert client.get("/api/jobs").status_code == 401
        posted = client.post("/api/jobs", json=body, headers=auth())
        assert posted.status_code == 202
        job_id = posted.json()["id"]
        wait_until(
            lambda: (
                client.get(f"/api/jobs/{job_id}", headers=auth()).json()["status"] == "succeeded"
            )
        )
        job = client.get(f"/api/jobs/{job_id}", headers=auth()).json()
        assert job["attempts"] == 1
        result_id = job["result_id"]
        result = client.get(f"/api/runs/{result_id}", headers=auth()).json()
        assert len(result["assessments"]) == 8
        assert all(a["review_state"] == "pending" for a in result["assessments"])
        assert client.get(f"/api/jobs/{job_id}", headers=auth("other-token")).status_code == 404
        assert (
            client.post(
                "/api/jobs",
                json={**body, "execution_mode": "bedrock"},
                headers=auth(key="paid-refusal"),
            ).status_code
            == 503
        )
    assert app.state.local_worker.state == "stopped"
    assert not app.state.local_worker.ready()
    with TestClient(create_local_service(path, PRINCIPALS)) as restarted:
        assert restarted.get(f"/api/runs/{result_id}", headers=auth()).json() == result
        assert restarted.get(f"/api/jobs/{job_id}", headers=auth()).json()["status"] == "succeeded"
    assert path.stat().st_mode & 0o777 == 0o600


def test_queue_failure_changes_readiness_without_exception_disclosure(tmp_path):
    app = create_local_service(tmp_path / "failure.db", PRINCIPALS)

    def fail(_):
        raise RuntimeError("private database connection and secret")

    app.state.local_worker._step = fail
    with TestClient(app) as client:
        wait_until(lambda: app.state.local_worker.state == "failed")
        response = client.get("/readyz")
        assert response.status_code == 503
        assert response.json() == {"detail": "Local worker is not ready"}
        assert "secret" not in response.text
        assert client.get("/healthz").status_code == 200
    assert app.state.local_worker.state == "failed"


def test_shutdown_waits_for_active_step_and_never_claims_next():
    entered, release = threading.Event(), threading.Event()
    calls = []

    def step(_):
        calls.append(1)
        entered.set()
        assert release.wait(5)
        return True

    worker = BaselineWorker(None, step=step)
    worker.start()
    assert entered.wait(5)
    with pytest.raises(RuntimeError, match="storage remains open"):
        worker.stop(timeout=0.01)
    assert worker.state == "stopping" and not worker.ready()
    release.set()
    worker.stop()
    worker.stop()
    assert worker.state == "stopped" and len(calls) == 1
    with pytest.raises(RuntimeError, match="cannot be reused"):
        worker.start()


def test_idle_stop_and_stop_before_start_are_idempotent():
    never_started = BaselineWorker(None)
    never_started.stop()
    never_started.stop()
    assert never_started.state == "stopped"
    idle = BaselineWorker(None, step=lambda _: False)
    idle.start()
    assert idle.ready()
    with pytest.raises(RuntimeError, match="cannot be reused"):
        idle.start()
    idle.stop()
    assert idle.state == "stopped"


@pytest.mark.parametrize(
    "name",
    [
        "ATLAS_DATABASE_URL",
        "ATLAS_MODEL_JOB_SPEC",
        "ATLAS_ENABLE_BEDROCK_JOBS",
        "ATLAS_TOKEN_TRUST",
    ],
)
def test_foreign_configuration_refused_before_database_creation(tmp_path, monkeypatch, name):
    monkeypatch.setenv(name, "forbidden")
    path = tmp_path / "must-not-exist.db"
    with pytest.raises(ValueError, match="local profile"):
        create_local_service(path, PRINCIPALS)
    assert not path.exists()


def test_existing_model_job_is_not_claimed_while_baseline_job_progresses(tmp_path):
    body = json.loads(Path("datasets/demo.json").read_text())
    app = create_local_service(tmp_path / "mixed.db", PRINCIPALS)
    queue = app.state.queue
    paid = queue.submit(
        "a",
        "alice",
        "preexisting-model",
        body,
        pipeline_version=MODEL_PIPELINE_VERSION,
        model_spec=spec(),
    )
    baseline = queue.submit("a", "alice", "later-baseline", body)
    # Controlled computation here; the first test executes the actual isolated child.
    app.state.local_worker._step = lambda q: process_once(q, executor=execute)
    with TestClient(app):
        wait_until(lambda: queue.get("a", baseline["id"])["status"] == "succeeded")
        assert queue.get("a", paid["id"])["status"] == "queued"
        assert queue.get("a", paid["id"])["attempts"] == 0
