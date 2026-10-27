"""Real local application-process restart with synthetic identity and restricted PostgreSQL."""

import argparse
import hashlib
import hmac
import json
import os
import re
import secrets
import signal
import socket
import subprocess
import sys
import threading
import time
from contextlib import ExitStack
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4

import httpx
from backup_fixture import canonical_tables
from login_postgres_fixture import PostgresFixture
from run_managed_workbench import environments
from verify_browser_login_https import certificate, fingerprints, proxy_for

from chaoslab.artifacts import publish_report

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--postgres-bin", required=True)
    parser.add_argument("--node", default="node")
    parser.add_argument("--pnpm-script")
    parser.add_argument("--storage", choices=["keep", "restart", "restore"], default="keep")
    args = parser.parse_args()
    sources = fingerprints()
    for name in (
        "scripts/login_restart_server.py",
        "scripts/verify_managed_restart.py",
        "scripts/backup_fixture.py",
    ):
        sources[name] = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
    work = ROOT / "var/managed-restart" / uuid4().hex[:12]
    work.mkdir(parents=True, mode=0o700)
    cert, key, spki = certificate(work)
    tmp = work / "tmp"
    tmp.mkdir(mode=0o700)
    env = {
        **os.environ,
        "TMPDIR": str(tmp),
        "TMP": str(tmp),
        "TEMP": str(tmp),
        "PLAYWRIGHT_BROWSERS_PATH": str(ROOT / ".cache/playwright"),
        "PYTHONPATH": str(ROOT / "src"),
    }
    command = [args.node, args.pnpm_script] if args.pnpm_script else ["pnpm"]
    with (work / "build.log").open("wb") as build_log:
        subprocess.run(
            [*command, "build"],
            cwd=ROOT / "apps/web",
            env=env,
            stdout=build_log,
            stderr=build_log,
            check=True,
            timeout=120,
        )
    children = {"api": None, "worker": None}
    logs = {}
    events = []
    snapshots = []
    secret = secrets.token_urlsafe(32)
    with ExitStack() as cleanup:
        cleanup.callback(key.unlink, missing_ok=True)
        database = PostgresFixture(work, args.postgres_bin)
        cleanup.callback(lambda: database.close())
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen(128)
        cleanup.callback(listener.close)
        proxy = proxy_for(listener.getsockname()[1])
        proxy_thread = threading.Thread(target=proxy.serve_forever, daemon=True)
        proxy_thread.start()
        cleanup.callback(proxy_thread.join, 5)
        cleanup.callback(proxy.server_close)
        cleanup.callback(proxy.shutdown)
        proxy_url = f"http://127.0.0.1:{proxy.server_port}"
        _, worker_env = environments(
            {
                "api_database": "unused",
                "worker_database": database.urls["worker"],
                "login_settings": "unused",
            },
            env,
        )
        api_env = {k: env[k] for k in ("PATH", "PYTHONPATH", "LANG") if k in env}
        generation = 0
        storage_evidence = {"mode": "keep"}

        def stop(role):
            child = children[role]
            if child is None:
                return
            if child.poll() is None:
                child.send_signal(signal.SIGTERM)
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()
            events.append({"service": role, "event": "stopped", "exit_code": child.returncode})
            children[role] = None
            logs[role].close()
            if child.returncode != 0:
                raise RuntimeError(f"Fixture {role} exited with {child.returncode}")
            if role == "api":
                snapshots.append(json.loads((work / f"metrics-{generation}.json").read_text()))
            if child.returncode != 0:
                raise RuntimeError("Fixture service did not stop cleanly")

        def start_worker():
            if children["worker"] is not None:
                raise RuntimeError("Worker already running")
            logs["worker"] = (work / "worker.log").open("ab")
            children["worker"] = subprocess.Popen(
                [sys.executable, "-m", "atlas.worker"],
                cwd=ROOT,
                env=worker_env,
                stdout=logs["worker"],
                stderr=logs["worker"],
                start_new_session=True,
            )
            events.append({"service": "worker", "event": "started"})

        def start_api():
            nonlocal generation
            generation += 1
            config = {
                "work": str(work),
                "operator_database": database.urls["owner"],
                "api_database": database.urls["api"],
                "proxy": proxy_url,
                "certificate": str(cert),
                "key": str(key),
                "listener_fd": listener.fileno(),
                "control_origin": control_origin,
                "control_secret": secret,
                "metrics_path": str(work / f"metrics-{generation}.json"),
            }
            path = work / "server.json"
            path.write_text(json.dumps(config))
            path.chmod(0o600)
            logs["api"] = (work / f"api-{generation}.log").open("ab")
            children["api"] = subprocess.Popen(
                [sys.executable, str(ROOT / "scripts/login_restart_server.py"), str(path)],
                cwd=ROOT,
                env=api_env,
                stdout=logs["api"],
                stderr=logs["api"],
                start_new_session=True,
                pass_fds=(listener.fileno(),),
            )
            deadline = time.monotonic() + 15
            with httpx.Client(
                proxy=proxy_url, verify=str(cert), trust_env=False, timeout=0.7
            ) as client:
                while time.monotonic() < deadline:
                    if children["api"].poll() is not None:
                        raise RuntimeError("Fixture API exited before readiness")
                    try:
                        if client.get("https://127.0.0.1/healthz").status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    time.sleep(0.05)
                else:
                    raise RuntimeError("Fixture API readiness timed out")
            events.append({"service": "api", "event": "started"})

        def recover_storage():
            nonlocal database, worker_env, storage_evidence
            stop("worker")
            with database.owner.engine.connect() as connection:
                before = canonical_tables(connection)
            if args.storage == "restart":
                storage_evidence = {"mode": "restart", **database.restart()}
            else:
                archive = work / "application.dump"
                database.dump(archive)
                archive_hash = hashlib.sha256(archive.read_bytes()).hexdigest()
                assert archive.stat().st_size > 0
                broken = work / "truncated.dump"
                broken.write_bytes(archive.read_bytes()[:32])
                broken.chmod(0o600)
                with (work / "corrupt-archive.log").open("w") as diagnostic:
                    rejected = subprocess.run(
                        [str(database.binaries / "pg_restore"), "--list", str(broken)],
                        stdout=diagnostic,
                        stderr=diagnostic,
                        env=database.command_environment,
                        timeout=10,
                    )
                assert rejected.returncode != 0
                old_identity = database.identity()[0]
                database.close()
                destination = work / "restore-target"
                destination.mkdir(mode=0o700)
                assert hashlib.sha256(archive.read_bytes()).hexdigest() == archive_hash
                database = PostgresFixture(destination, args.postgres_bin, restore_archive=archive)
                assert database.identity()[0] != old_identity
                assert hashlib.sha256(archive.read_bytes()).hexdigest() == archive_hash
                storage_evidence = {
                    "mode": "restore",
                    "fresh_cluster_identifier": True,
                    "truncated_archive_refused": True,
                    "archive_sha256": archive_hash,
                    "archive_bytes": archive.stat().st_size,
                }
            with database.owner.engine.connect() as connection:
                after = canonical_tables(connection)
            assert after == before
            storage_evidence["all_application_tables_equal"] = True
            storage_evidence["table_count"] = len(before)
            _, worker_env = environments(
                {
                    "api_database": "unused",
                    "worker_database": database.urls["worker"],
                    "login_settings": "unused",
                },
                env,
            )
            start_worker()

        class Control(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_POST(self):
                if not hmac.compare_digest(self.headers.get("X-Fixture-Control", ""), secret):
                    self.send_error(403)
                    return
                if self.path == "/pause-worker":
                    stop("worker")
                elif self.path == "/resume-worker":
                    start_worker()
                elif self.path == "/restart-app":
                    stop("api")
                    if args.storage != "keep":
                        recover_storage()
                    start_api()
                else:
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header("Content-Length", "0")
                self.end_headers()

        control = ThreadingHTTPServer(("127.0.0.1", 0), Control)
        control_origin = f"http://127.0.0.1:{control.server_port}"
        control_thread = threading.Thread(target=control.serve_forever, daemon=True)
        control_thread.start()
        cleanup.callback(control_thread.join, 5)
        cleanup.callback(control.server_close)
        cleanup.callback(control.shutdown)
        cleanup.callback(stop, "api")
        cleanup.callback(stop, "worker")
        start_api()
        start_worker()
        result = subprocess.run(
            [args.node, str(ROOT / "scripts/browser_login_https.mjs")],
            cwd=ROOT,
            env={
                **env,
                "ATLAS_FIXTURE_PROXY": proxy_url,
                "ATLAS_FIXTURE_SPKI": spki,
                "ATLAS_FIXTURE_SEPARATE_WORKER": "1",
                "ATLAS_FIXTURE_RESTART_ORIGIN": control_origin,
                "ATLAS_FIXTURE_RESTART_SECRET": secret,
                "ATLAS_FIXTURE_STORAGE": args.storage,
                "ATLAS_FIXTURE_SCREENSHOT": str(work / "workbench.png"),
            },
            capture_output=True,
            timeout=150,
        )
        (work / "browser.json").write_bytes(result.stdout)
        (work / "browser.log").write_bytes(result.stderr)
        if result.returncode:
            raise RuntimeError("Managed restart browser workflow failed; inspect private run logs")
        observed = json.loads(result.stdout)
        if len(observed["checks"]) != (14 if args.storage == "keep" else 15) or not all(
            observed["checks"].values()
        ):
            raise RuntimeError("Incomplete restart checks")
    assert generation == 2 and len(snapshots) == 2
    assert (
        sum(m["authorized"] for m in snapshots) == sum(m["token_exchanges"] for m in snapshots) == 3
    )
    assert all(
        m["pkce_rejections"] == 0 and m["same_origin_form_post"] and m["external_referrer_absent"]
        for m in snapshots
    )
    assert len([e for e in events if e["event"] == "stopped"]) == (
        4 if args.storage == "keep" else 5
    )
    for name, digest in sources.items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest
    shutdown_logs = [(work / f"api-{n}.log").read_text() for n in (1, 2)]
    drain_deadlines = sum(s.count("timeout graceful shutdown exceeded") for s in shutdown_logs)
    cancelled_tasks = sum(
        int(n) for s in shutdown_logs for n in re.findall(r"Cancel (\d+) running task", s)
    )
    publish_report(
        ROOT
        / (
            "reports/managed-postgres-restart.json"
            if args.storage == "keep"
            else "reports/managed-postgres-database-restart.json"
            if args.storage == "restart"
            else "reports/managed-postgres-restore.json"
        ),
        {
            "recorded_at": datetime.now(UTC).isoformat(),
            "scope": "Real API operating-system process replacement, actual managed factory/queue/separate worker and local restricted PostgreSQL, with a synthetic identity provider and loopback browser TLS.",
            "checks": observed["checks"],
            "service_lifecycle": events,
            "provider_generations": generation,
            "fixture_shutdown": {
                "connection_drain_deadline_seconds": 2,
                "deadline_hits": drain_deadlines,
                "reported_running_tasks_cancelled": cancelled_tasks,
            },
            "database_roles": database.observations,
            "storage_recovery": storage_evidence,
            "database_transport": "Authenticated local loopback TCP without TLS",
            "source_sha256": sources,
            "external_provider_calls": 0,
            "new_cloud_services": 0,
            "new_model_calls": 0,
            "limits": [
                "Synthetic identities/control routes must never be deployed. This is not real Cognito or hosted proxy/TLS acceptance.",
                "Read storage_recovery.mode for database restart versus separate restore. No provider database TLS, supervised production image or hung-worker acceptance.",
                "Restoration uses only this fixture-created trusted logical archive. It is not a safe loader for untrusted backups or a cloud backup policy.",
                "Fixture API shutdown uses a two-second connection-drain deadline; deadline hits and running-task cancellation counts are retained. This is not an uninterrupted-request or fully drained-connection claim.",
                "Browser trust uses only the generated fixture certificate SPKI for this test subprocess; system trust is unchanged.",
            ],
        },
    )
    print(
        json.dumps(
            {
                "status": "passed",
                "browser_groups": len(observed["checks"]),
                "api_generations": generation,
                "clean_service_exits": len([e for e in events if e["event"] == "stopped"]),
            }
        )
    )


if __name__ == "__main__":
    main()
