"""Verify Docker teardown of detached analysis children; no API, database or provider."""

import argparse
import hashlib
import json
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from chaoslab.artifacts import publish_report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docker", default="docker")
    parser.add_argument(
        "--image", required=True, help="Existing local image; never pulled or built"
    )
    args = parser.parse_args()
    root = Path.cwd().resolve()
    private = root / "var/supervisor-container" / uuid4().hex
    private.mkdir(parents=True, mode=0o700)
    shared = private / "signals"
    shared.mkdir(mode=0o777)
    shared.chmod(0o777)  # No secrets; private parent remains mode0700 on host.
    name = "atlas-supervisor-" + private.name[:12]
    log = (private / "docker.log").open("w")

    def docker(*command, capture=True, check=True):
        return subprocess.run(
            [args.docker, *command],
            check=check,
            text=True,
            stdout=subprocess.PIPE if capture else log,
            stderr=log,
            timeout=45,
        )

    def state():
        return json.loads(docker("inspect", name, "--format", "{{json .State}}").stdout)

    def wait_until(predicate):
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            result = predicate()
            if result:
                return result
            time.sleep(0.05)
        raise AssertionError("Container lifecycle condition did not complete")

    # Stand-ins exercise the actual supervisor and bounded child primitive.
    # The bounded child deliberately creates a new session, outside the worker group.
    (shared / "worker.py").write_text("""import os,time,threading,uuid
from pathlib import Path
from atlas.child_process import run_bounded
marker=Path('/proof')/('heartbeat-'+uuid.uuid4().hex)
code="import time;from pathlib import Path;p=Path("+repr(str(marker))+");n=0\\nwhile True:\\n q=p.with_suffix('.next');q.write_text(str(n));q.replace(p);n+=1;time.sleep(.05)"
threading.Thread(target=lambda:run_bounded(['python','-c',code],b'',timeout_seconds=60),daemon=True).start()
while True:
 if Path('/proof/exit-worker').exists():os._exit(3)
 time.sleep(.02)
""")
    (shared / "entry.py").write_text("""import importlib.util,os
s=importlib.util.spec_from_file_location('supervisor','/app/scripts/run_managed_workbench.py')
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
raise SystemExit(m.supervise([['python','-c','import time;time.sleep(60)'],['python','/proof/worker.py']],[dict(os.environ),dict(os.environ)],grace=.3,poll_interval=.02))
""")
    image = docker("image", "inspect", args.image, "--format", "{{.Id}}").stdout.strip()
    observations = {}
    try:
        docker(
            "create",
            "--name",
            name,
            "--network",
            "none",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--pids-limit",
            "64",
            "--memory",
            "256m",
            "--tmpfs",
            "/tmp:rw,nosuid,nodev,size=32m",
            "-e",
            "PYTHONDONTWRITEBYTECODE=1",
            "-v",
            str(root / "src") + ":/app/src:ro",
            "-v",
            str(root / "scripts/run_managed_workbench.py")
            + ":/app/scripts/run_managed_workbench.py:ro",
            "-v",
            str(shared) + ":/proof:rw",
            image,
            "python",
            "/proof/entry.py",
        )
        docker("start", name)
        marker = wait_until(lambda: next(shared.glob("heartbeat-*"), None))
        wait_until(lambda: marker.read_text().strip().isdigit() and int(marker.read_text()) >= 2)
        docker("stop", "--timeout", "3", name)
        stopped = state()
        assert not stopped["Running"] and stopped["ExitCode"] == 0 and not stopped["OOMKilled"]
        last = marker.read_bytes()
        time.sleep(0.4)
        assert marker.read_bytes() == last
        observations["operator_shutdown"] = {
            "container_stopped": True,
            "exit_code": 0,
            "detached_heartbeat_stopped": True,
        }
        docker("start", name)
        new_marker = wait_until(
            lambda: next((p for p in shared.glob("heartbeat-*") if p != marker), None)
        )
        wait_until(
            lambda: new_marker.read_text().strip().isdigit() and int(new_marker.read_text()) >= 2
        )
        assert marker.read_bytes() == last
        observations["restart"] = {
            "fresh_analysis_session": True,
            "old_heartbeat_not_resumed": True,
        }
        (shared / "exit-worker").write_text("requested")
        wait_until(lambda: not state()["Running"])
        failed = state()
        assert failed["ExitCode"] == 1 and not failed["OOMKilled"]
        final = new_marker.read_bytes()
        time.sleep(0.4)
        assert new_marker.read_bytes() == final
        observations["worker_failure"] = {
            "container_stopped": True,
            "exit_code": 1,
            "detached_heartbeat_stopped": True,
        }
        paths = [
            "scripts/run_managed_workbench.py",
            "scripts/verify_supervisor_container.py",
            "src/atlas/child_process.py",
        ]
        publish_report(
            Path("reports/supervisor-container.json"),
            {
                "recorded_at": datetime.now(UTC).isoformat(),
                "image_id": image,
                "scope": "Real local Docker lifecycle using actual supervisor and bounded analysis-child primitive, with stand-in API/worker. Not actual API/queue/database/provider or hosted acceptance.",
                "observations": observations,
                "network": "none",
                "root_filesystem": "read-only",
                "current_source_mounted_readonly": True,
                "new_image_built": False,
                "new_model_calls": 0,
                "new_services": 0,
                "source_sha256": {
                    p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in paths
                },
                "limits": [
                    "Evidence applies to whole-container teardown with this supervisor as PID1. Process-group cleanup alone remains insufficient outside that boundary.",
                    "No hung-worker detection, real queue lease recovery, PostgreSQL persistence/restore or hosted proxy/sign-in validation.",
                    "An explicitly mounted synthetic heartbeat directory was writable; no credentials, Docker socket or other owner files entered the container.",
                ],
            },
        )
        print(json.dumps({"status": "passed", "checks": list(observations)}))
    finally:
        docker("rm", "--force", name, check=False)
        log.close()


if __name__ == "__main__":
    main()
