"""Offline, real loopback HTTP lifecycle/restart check; no provider or host resources."""

import hashlib
import json
import secrets
import signal
import socket
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

import httpx

from atlas.models.provenance import source_manifest
from chaoslab.artifacts import publish_report


def wait_for(check, *, seconds=20):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            result = check()
            if result:
                return result
        except httpx.TransportError:
            pass
        time.sleep(0.05)
    raise RuntimeError("Loopback verification deadline exceeded")


@contextmanager
def serving(root, credentials):
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    # Any competing bind fails startup; authenticated /me also identifies our instance.
    log_path = root / ("server-" + secrets.token_hex(8) + ".log")
    with log_path.open("wb") as log:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "atlas.local_service",
                "--database",
                str(root / "service.db"),
                "--credentials",
                str(credentials),
                "--port",
                str(port),
            ],
            stdout=log,
            stderr=log,
        )
        try:
            with httpx.Client(
                base_url=f"http://127.0.0.1:{port}", timeout=2, trust_env=False
            ) as client:
                yield client
        finally:
            process.terminate()
            try:
                code = process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
                raise RuntimeError("Verification required forced shutdown") from None
            if (
                code not in {0, -signal.SIGTERM}
                or b"Application shutdown complete." not in log_path.read_bytes()
            ):
                raise RuntimeError("Local service did not complete graceful shutdown")


def main():
    junit = Path("var/local-service-tests.xml").read_bytes()
    cases = list(ET.fromstring(junit).iter("testcase"))
    focused = [c for c in cases if c.attrib.get("classname", "").endswith("test_local_service")]
    if len(focused) != 9 or any(
        c.find(tag) is not None for c in focused for tag in ("failure", "error", "skipped")
    ):
        raise ValueError("Expected nine actually executed local service checks")
    if any(c.find(tag) is not None for c in cases for tag in ("failure", "error")):
        raise ValueError("Native regression gate failed")
    source = source_manifest()
    other_paths = ["scripts/verify_local_service.py", "datasets/demo.json"]
    hashes = {p: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in other_paths}
    body = json.loads(Path("datasets/demo.json").read_text())
    scratch = Path("var/local-service-verification")
    scratch.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.TemporaryDirectory(dir=scratch) as directory:
        root = Path(directory).resolve()
        credentials = root / "credentials.json"
        token = secrets.token_urlsafe(32)
        foreign = secrets.token_urlsafe(32)
        credentials.write_text(
            json.dumps(
                {
                    token: {"tenant": "synthetic", "actor": "verifier", "role": "reviewer"},
                    foreign: {"tenant": "other", "actor": "verifier", "role": "viewer"},
                }
            )
        )
        credentials.chmod(0o600)
        headers = {"Authorization": f"Bearer {token}"}
        with serving(root, credentials) as client:

            def connected():
                response = client.get("/api/me", headers=headers)
                return response.status_code == 200 and response.json()["actor"] == "verifier"

            wait_for(connected)
            assert client.get("/readyz").status_code == 200
            assert client.get("/api/jobs").status_code == 401
            posted = client.post(
                "/api/jobs", json=body, headers={**headers, "Idempotency-Key": "http-lifecycle"}
            )
            assert posted.status_code == 202
            job_id = posted.json()["id"]
            job = wait_for(
                lambda: (
                    current
                    if (current := client.get(f"/api/jobs/{job_id}", headers=headers).json())[
                        "status"
                    ]
                    == "succeeded"
                    else None
                )
            )
            assert job["attempts"] == 1
            result_id = job["result_id"]
            result = client.get(f"/api/runs/{result_id}", headers=headers).json()
            assert len(result["assessments"]) == 8
            assert all(a["review_state"] == "pending" for a in result["assessments"])
            assert (
                client.get(
                    f"/api/runs/{result_id}", headers={"Authorization": f"Bearer {foreign}"}
                ).status_code
                == 404
            )
            assert (
                client.post(
                    "/api/jobs",
                    json={**body, "execution_mode": "bedrock"},
                    headers={**headers, "Idempotency-Key": "http-paid-refusal"},
                ).status_code
                == 503
            )
        with serving(root, credentials) as restarted:
            wait_for(lambda: restarted.get("/api/me", headers=headers).status_code == 200)
            assert restarted.get("/readyz").status_code == 200
            assert restarted.get(f"/api/runs/{result_id}", headers=headers).json() == result
            assert restarted.get(f"/api/jobs/{job_id}", headers=headers).json()["attempts"] == 1
        citations = sum(1 + len(a["evidence"]) for a in result["assessments"])
    if source != source_manifest() or hashes != {
        p: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in other_paths
    }:
        raise ValueError("Source changed during HTTP verification")
    report = {
        "schema_version": 1,
        "recorded_at": datetime.now(UTC).isoformat(),
        "scope": "Real native loopback HTTP API plus lifespan-owned baseline worker, real isolated analysis child, SQLite restart, completed lifespan shutdown twice under SIGTERM (Uvicorn may re-raise the signal). Not public sessions, free-provider storage, managed authentication, PostgreSQL, image or cloud validation.",
        "lifecycle_tests_passed": len(focused),
        "native_suite": {
            "passed": sum(c.find("skipped") is None for c in cases),
            "skipped": sum(c.find("skipped") is not None for c in cases),
        },
        "http_checks": {
            "ready_before_and_after_restart": True,
            "unauthenticated_jobs_status": 401,
            "foreign_tenant_result_status": 404,
            "model_submission_status": 503,
            "job_attempts": job["attempts"],
            "requirements": len(result["assessments"]),
            "publication_validated_citations": citations,
            "reviews_pending": True,
            "restart_preserved_result": True,
            "graceful_shutdowns": 2,
        },
        "source_manifest": source,
        "http_exercise_sha256": hashes,
        "junit_sha256": hashlib.sha256(junit).hexdigest(),
        "test_source_sha256": hashlib.sha256(
            Path("tests/test_local_service.py").read_bytes()
        ).hexdigest(),
        "test_hash_scope": "Test source/JUnit hashes captured after testing; HTTP exercise source separately checked before/after. No signed execution attestation.",
        "provider_calls": 0,
    }
    publish_report(Path("reports/local-service.json"), report)
    print(
        json.dumps({"lifecycle_tests_passed": len(focused), "http_checks": report["http_checks"]})
    )


if __name__ == "__main__":
    main()
