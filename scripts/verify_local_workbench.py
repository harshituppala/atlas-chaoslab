"""Exercise the actual paired local launcher, browser intake and restart persistence."""

import argparse
import hashlib
import json
import os
import signal
import socket
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx

from chaoslab.artifacts import publish_report

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--node", default="node")
    parser.add_argument("--pnpm", default="pnpm")
    args = parser.parse_args()
    sources = [
        ROOT / p
        for p in [
            "scripts/run_local_workbench.py",
            "scripts/run_managed_workbench.py",
            "scripts/run_managed_worker.py",
            "scripts/verify_local_workbench.py",
            "apps/web/e2e/workbench.spec.ts",
        ]
    ] + sorted((ROOT / "src/atlas").rglob("*.py"))
    frozen = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    work = ROOT / "var/local-launcher-check" / uuid4().hex[:12]
    work.mkdir(parents=True, mode=0o700)
    workspace = work / "workspace"
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    env = {k: os.environ[k] for k in ("PATH", "LANG") if k in os.environ}
    env["PYTHONPATH"] = str(ROOT / "src")
    child = None
    log = (work / "execution.log").open("w")
    lifecycle = []

    def start():
        nonlocal child
        child = subprocess.Popen(
            [
                sys.executable,
                str(ROOT / "scripts/run_local_workbench.py"),
                "--workspace",
                str(workspace),
                "--port",
                str(port),
            ],
            cwd=ROOT,
            env=env,
            stdout=log,
            stderr=log,
        )
        for _ in range(100):
            assert child.poll() is None, "Launcher exited before readiness; private log retained"
            try:
                with httpx.Client(trust_env=False, timeout=0.3) as client:
                    if client.get(base + "/readyz").status_code == 200:
                        break
            except httpx.HTTPError:
                pass
            time.sleep(0.1)
        else:
            raise RuntimeError("Paired launcher did not become ready")
        lifecycle.append({"event": "started"})

    def stop():
        pairs = subprocess.check_output(["ps", "-axo", "pid=,ppid="], text=True)
        descendants = [
            int(parts[0])
            for line in pairs.splitlines()
            if len(parts := line.split()) == 2 and int(parts[1]) == child.pid
        ]
        assert len(descendants) == 2
        child.send_signal(signal.SIGTERM)
        assert child.wait(timeout=15) == 0
        for pid in descendants:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                pass
            else:
                raise AssertionError("Local service remained after paired shutdown")
        with socket.socket() as probe:
            assert probe.connect_ex(("127.0.0.1", port)) != 0
        lifecycle.append({"event": "stopped", "services_reaped": len(descendants), "exit_code": 0})

    try:
        start()
        secret_file = workspace / "credentials.json"
        original_credentials = secret_file.read_bytes()
        token = next(iter(json.loads(original_credentials)))
        headers = {"Authorization": "Bearer " + token}
        other = work / "occupied-port-workspace"
        rejected = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/run_local_workbench.py"),
                "--workspace",
                str(other),
                "--port",
                str(port),
            ],
            env=env,
            cwd=ROOT,
            stdout=log,
            stderr=log,
            timeout=10,
        )
        assert rejected.returncode == 1 and not other.exists()
        pnpm = [args.node, args.pnpm] if args.pnpm.endswith((".cjs", ".js")) else [args.pnpm]
        browser_env = {
            **env,
            "ATLAS_TEST_URL": base,
            "ATLAS_TEST_CREDENTIALS": str(secret_file),
            "PLAYWRIGHT_BROWSERS_PATH": str(ROOT / ".cache/playwright"),
            "PLAYWRIGHT_JSON_OUTPUT_NAME": str(work / "browser.json"),
            "TMPDIR": str(workspace / "tmp"),
        }
        browser_env["PATH"] = (
            str(Path(args.node).resolve().parent) + os.pathsep + env.get("PATH", "")
        )
        subprocess.run(
            [
                *pnpm,
                "--dir",
                "apps/web",
                "exec",
                "playwright",
                "test",
                "e2e/workbench.spec.ts",
                "--grep",
                "upload PDF and DOCX",
                "--workers=1",
                "--retries=0",
                "--reporter=json",
            ],
            cwd=ROOT,
            env=browser_env,
            stdout=log,
            stderr=log,
            timeout=90,
            check=True,
        )
        evidence = (work / "browser.json").read_bytes()
        browser = json.loads(evidence)
        assert browser["stats"]["expected"] == 1 and all(
            browser["stats"][k] == 0 for k in ("unexpected", "flaky", "skipped")
        )
        with httpx.Client(base_url=base, headers=headers, trust_env=False) as client:
            runs = client.get("/api/runs").json()
            assert len(runs) == 1
            identifier = runs[0]["id"]
            before = client.get("/api/runs/" + identifier).json()
            audit = client.get(f"/api/runs/{identifier}/audit").json()
            documents = client.get("/api/documents").json()
            originals = {
                d["id"]: hashlib.sha256(
                    client.get(f"/api/documents/{d['id']}/original").content
                ).hexdigest()
                for d in documents
            }
        stop()
        start()
        assert secret_file.read_bytes() == original_credentials
        with httpx.Client(base_url=base, headers=headers, trust_env=False) as client:
            assert client.get("/api/runs/" + identifier).json() == before
            assert client.get(f"/api/runs/{identifier}/audit").json() == audit
            assert client.get("/api/documents").json() == documents
            assert len(originals) == 2
            for doc_id, digest in originals.items():
                response = client.get(f"/api/documents/{doc_id}/original")
                assert (
                    response.status_code == 200
                    and hashlib.sha256(response.content).hexdigest() == digest
                )
        stop()
        assert all(
            hashlib.sha256((ROOT / p).read_bytes()).hexdigest() == h for p, h in frozen.items()
        )
        report = {
            "recorded_at": datetime.now(UTC).isoformat(),
            "scope": "Actual local paired launcher on loopback HTTP/SQLite with a synthetic static reviewer. One real Chromium PDF/DOCX intake/source/review workflow, then paired API/worker stop and restart. Not browser-session/Cognito, TLS, PostgreSQL or hosted acceptance.",
            "checks": {
                "browser_intake_review_passed": True,
                "occupied_port_refused_before_workspace_creation": True,
                "credentials_reused": True,
                "complete_run_and_audit_preserved": True,
                "two_uploaded_originals_preserved": True,
                "paired_processes_reaped": True,
                "listener_released": True,
            },
            "lifecycle": lifecycle,
            "browser_evidence_sha256": hashlib.sha256(evidence).hexdigest(),
            "files_sha256": frozen,
            "new_model_provider_calls": 0,
        }
        publish_report(ROOT / "reports/local-workbench-launcher.json", report)
        print(
            json.dumps(
                {"checks_passed": len(report["checks"]), "browser_workflows": 1, "model_calls": 0}
            )
        )
    finally:
        if child is not None and child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=15)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
        log.close()


if __name__ == "__main__":
    main()
