"""Run inside the built image: real loopback HTTP, worker, durable SQLite and restart.

Only synthetic documents and randomly generated temporary local bearer tokens are used.
The caller must provide a container with external networking disabled. No provider calls.
"""

import json
import os
import secrets
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from atlas.domain import Citation, Document


def main():
    assert os.getuid() == 10001
    body = json.loads(Path("datasets/demo.json").read_text())
    documents = {d["id"]: Document.model_validate(d) for d in [body["rfp"], *body["knowledge"]]}
    tokens = {name: secrets.token_urlsafe(32) for name in ("analyst", "one", "two", "foreign")}
    principals = {
        tokens[name]: {
            "tenant": "b" if name == "foreign" else "a",
            "actor": name,
            "role": "analyst" if name == "analyst" else "reviewer",
        }
        for name in tokens
    }
    base = "http://127.0.0.1:8123"

    def request(path, actor="one", data=None, method=None):
        headers = {
            "Authorization": "Bearer " + tokens[actor],
            "Idempotency-Key": "container-workflow-001",
            "Content-Type": "application/json",
        }
        req = urllib.request.Request(
            base + path,
            data=None if data is None else json.dumps(data).encode(),
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as response:
                raw = response.read()
                return response.status, json.loads(raw) if raw else None
        except urllib.error.HTTPError as error:
            return error.code, None

    with tempfile.TemporaryDirectory(prefix="atlas-container-") as folder:
        env = {
            **os.environ,
            "ATLAS_DATABASE_URL": "sqlite:///" + folder + "/atlas.db",
            "ATLAS_PRINCIPALS": json.dumps(principals),
            "ATLAS_ENABLE_BEDROCK_JOBS": "0",
        }
        processes = []

        def start_api():
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "atlas.api:create_app",
                    "--factory",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "8123",
                ],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            processes.append(process)
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError("Container API exited before readiness")
                try:
                    if request("/readyz")[0] == 200:
                        return process
                except OSError:
                    pass
                time.sleep(0.05)
            raise TimeoutError("Container API readiness deadline")

        try:
            api = start_api()
            with urllib.request.urlopen(base + "/", timeout=5) as response:
                assert response.status == 200 and b"<html" in response.read().lower()
            code, capability = request("/api/execution-options")
            assert code == 200
            # Admission must remain explicitly disabled in this offline exercise.
            assert request("/api/jobs", "analyst", {**body, "execution_mode": "bedrock"})[0] == 503
            code, job = request("/api/jobs", "analyst", body)
            assert code == 202 and job["status"] == "queued"
            assert request("/api/jobs", "analyst", body)[1]["id"] == job["id"]
            assert request("/api/jobs/" + job["id"], "foreign")[0] == 404
            api.terminate()
            api.wait(timeout=10)
            api = start_api()
            assert request("/api/jobs/" + job["id"])[1]["status"] == "queued"
            subprocess.run(
                [sys.executable, "-m", "atlas.worker", "--once"],
                env=env,
                check=True,
                timeout=30,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            code, completed = request("/api/jobs/" + job["id"])
            assert code == 200 and completed["status"] == "succeeded"
            code, run = request("/api/runs/" + completed["result_id"])
            assert code == 200
            citation_count = 0
            for item in run["assessments"]:
                for value in [item["requirement"]["source"], *item["evidence"]]:
                    citation = Citation.model_validate(value)
                    assert citation.matches(documents[citation.document_id])
                    citation_count += 1
            item = next(a for a in run["assessments"] if a["status"] == "evidence_found")
            path = f"/api/runs/{run['id']}/reviews/{item['requirement']['id']}"
            decision = {"version": 1, "decision": "approved", "note": "Synthetic source checked."}
            with ThreadPoolExecutor(max_workers=2) as pool:
                statuses = list(
                    pool.map(lambda actor: request(path, actor, decision)[0], ["one", "two"])
                )
            assert sorted(statuses) == [200, 409]
            api.terminate()
            api.wait(timeout=10)
            api = start_api()
            restored = request("/api/runs/" + run["id"])[1]
            reviewed = next(
                a
                for a in restored["assessments"]
                if a["requirement"]["id"] == item["requirement"]["id"]
            )
            assert reviewed["review_state"] == "approved" and reviewed["version"] == 2
            events = request(f"/api/runs/{run['id']}/audit")[1]
            assert sum(e["action"] == "review.approved" for e in events) == 1
            assert request("/api/runs/" + run["id"], "foreign")[0] == 404
            print(
                json.dumps(
                    {
                        "runtime_uid": os.getuid(),
                        "http_ready": True,
                        "frontend_served": True,
                        "model_admission_disabled": True,
                        "queued_job_survives_api_restart": True,
                        "real_worker_completed": True,
                        "citation_count_validated": citation_count,
                        "competing_review_statuses": sorted(statuses),
                        "review_survives_api_restart": True,
                        "tenant_isolation": True,
                        "storage": "temporary SQLite",
                        "paid_calls": 0,
                    }
                )
            )
        finally:
            for process in processes:
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=10)


if __name__ == "__main__":
    main()
