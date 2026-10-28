"""Build an allowlisted lab image and execute constrained, network-isolated Linux checks."""

import argparse
import hashlib
import json
import shutil
import subprocess
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from atlas.models.provenance import source_manifest
from chaoslab.artifacts import publish_report

FRONTEND = [
    "apps/web/package.json",
    "apps/web/pnpm-lock.yaml",
    "apps/web/pnpm-workspace.yaml",
    "apps/web/tsconfig.json",
    "apps/web/vite.lab.config.ts",
    "apps/web/lab/index.html",
    "apps/web/src/lab.tsx",
    "apps/web/src/SavedReviewExample.tsx",
    "apps/web/src/lab.css",
    "apps/web/src/Dialog.tsx",
    "apps/web/src/PublicHeader.tsx",
    "apps/web/src/PublicEvaluation.tsx",
    "apps/web/src/ContractTestPanel.tsx",
    "apps/web/src/ScenarioPanel.tsx",
    "reports/scenarios-baseline.json",
    "reports/scenarios-live-v4.json",
    "reports/reasoning-transfer-baseline.json",
    "reports/reasoning-transfer-live-v4.json",
    "reports/contract-model-test.json",
    "reports/contract-model-test-standalone-replay.json",
    "datasets/reasoning-transfer.json",
]


def hashes(root, paths):
    result = {}
    for path in sorted(paths):
        source = root / path
        if source.is_symlink() or not source.resolve().is_relative_to(root):
            raise ValueError("Container input must remain in the portfolio root")
        result[path] = hashlib.sha256(source.read_bytes()).hexdigest()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docker", default="docker")
    args = parser.parse_args()
    root = Path.cwd().resolve()
    paths = [p.as_posix() for p in Path("src").rglob("*.py")]
    paths += [
        "Dockerfile.lab",
        "requirements.lock",
        "pyproject.toml",
        "datasets/demo.json",
        *FRONTEND,
    ]
    supporting = [
        "scripts/verify_lab_container.py",
        "scripts/lab_container_workflow.py",
        "tests/test_synthetic_lab.py",
        "tests/test_lab_container.py",
    ]
    frozen = hashes(root, paths + supporting)
    manifest = source_manifest()
    private = root / "var/lab-container" / uuid4().hex
    private.mkdir(parents=True, mode=0o700)
    context = private / "context"
    context.mkdir(mode=0o700)
    for path in paths:
        destination = context / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / path, destination)
    if hashes(context, paths) != {p: frozen[p] for p in paths}:
        raise ValueError("Container context differs from frozen allowlist")
    (private / "inputs.json").write_text(json.dumps(frozen, indent=2))
    name = "atlas-lab-check-" + private.name

    def docker(*command, **kwargs):
        try:
            return subprocess.run([args.docker, *command], timeout=900, check=True, **kwargs)
        except subprocess.CalledProcessError as exc:
            if exc.stderr:
                error = exc.stderr.encode() if isinstance(exc.stderr, str) else exc.stderr
                with (private / "docker-errors.log").open("ab") as log:
                    log.write(error)
            raise

    with (private / "build.log").open("w") as log:
        docker(
            "build",
            "--file",
            str(context / "Dockerfile.lab"),
            "--tag",
            "atlas-synthetic-lab:validation",
            str(context),
            stdout=log,
            stderr=subprocess.STDOUT,
        )
    image = json.loads(
        docker(
            "image", "inspect", "atlas-synthetic-lab:validation", capture_output=True, text=True
        ).stdout
    )[0]
    identity = image["Id"]
    assert image["Config"]["User"] == "10001"
    started = False
    try:
        docker(
            "run",
            "--detach",
            "--name",
            name,
            "--network",
            "none",
            "--read-only",
            "--memory",
            "512m",
            "--memory-swap",
            "512m",
            "--cpus",
            "1",
            "--pids-limit",
            "64",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--tmpfs",
            "/app/var:rw,noexec,nosuid,size=16m,uid=10001,gid=10001",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=8m,uid=10001,gid=10001",
            "--mount",
            f"type=bind,src={root / supporting[1]},dst=/verification/lab_container_workflow.py,readonly",
            "--mount",
            f"type=bind,src={root / supporting[2]},dst=/verification/test_synthetic_lab.py,readonly",
            "--mount",
            f"type=bind,src={root / supporting[3]},dst=/verification/test_lab_container.py,readonly",
            "--env",
            "ATLAS_LAB_CONTAINER=1",
            "--env",
            "ATLAS_LAB_ORIGIN=http://127.0.0.1:8000",
            identity,
            stdout=subprocess.DEVNULL,
        )
        started = True
        inspected = json.loads(docker("inspect", name, capture_output=True, text=True).stdout)[0]
        host = inspected["HostConfig"]
        assert host["NetworkMode"] == "none" and host["ReadonlyRootfs"]
        assert not host["PortBindings"] and not host["Privileged"]
        assert host["Memory"] == 536870912 and host["MemorySwap"] == 536870912
        assert host["PidsLimit"] == 64 and host["NanoCpus"] == 1000000000
        assert host["CapDrop"] == ["ALL"] and "no-new-privileges" in host["SecurityOpt"]
        assert all(
            m["Type"] == "bind" and not m["RW"] and m["Destination"].startswith("/verification/")
            for m in inspected["Mounts"]
            if m["Type"] == "bind"
        )
        installed = json.loads(
            docker(
                "exec",
                name,
                "python",
                "-c",
                "import json; from atlas.models.provenance import source_manifest; print(json.dumps(source_manifest()))",
                capture_output=True,
                text=True,
            ).stdout
        )
        assert installed["files"] == manifest["files"]
        with (private / "dependencies.log").open("w") as log:
            docker(
                "exec", name, "python", "-m", "pip", "check", stdout=log, stderr=subprocess.STDOUT
            )
        with (private / "tests.log").open("w") as log:
            docker(
                "exec",
                name,
                "python",
                "-m",
                "pytest",
                "-q",
                "-p",
                "no:cacheprovider",
                "/verification/test_synthetic_lab.py",
                "/verification/test_lab_container.py",
                "--basetemp=/app/var/pytest",
                "--junitxml=/app/var/linux-tests.xml",
                stdout=log,
                stderr=subprocess.STDOUT,
            )
        junit = docker(
            "exec",
            name,
            "python",
            "-c",
            "import sys; from pathlib import Path; sys.stdout.buffer.write(Path('/app/var/linux-tests.xml').read_bytes())",
            capture_output=True,
        ).stdout
        (private / "linux-tests.xml").write_bytes(junit)
        cases = list(ET.fromstring(junit).iter("testcase"))
        if len(cases) != 41 or any(
            c.find(t) is not None for c in cases for t in ("failure", "error", "skipped")
        ):
            raise ValueError("Expected all 41 focused Linux tests to pass")
        before = json.loads(
            docker(
                "exec",
                name,
                "python",
                "/verification/lab_container_workflow.py",
                "before",
                capture_output=True,
                text=True,
            ).stdout
        )
        cookie = before.pop("restart_cookie")
        assert isinstance(cookie, str) and len(cookie) == 43
        peak_text = docker(
            "exec",
            name,
            "python",
            "-c",
            "from pathlib import Path; p=Path('/sys/fs/cgroup/memory.peak'); print(p.read_text().strip() if p.exists() else 'unknown')",
            capture_output=True,
            text=True,
        ).stdout.strip()
        peak = int(peak_text) if peak_text.isdecimal() else None
        docker("restart", "--time", "30", name, stdout=subprocess.DEVNULL)
        after = json.loads(
            docker(
                "exec",
                "--interactive",
                name,
                "python",
                "/verification/lab_container_workflow.py",
                "after",
                input=json.dumps({"cookie": cookie}),
                capture_output=True,
                text=True,
            ).stdout
        )
        del cookie
        state = json.loads(docker("inspect", name, capture_output=True, text=True).stdout)[0][
            "State"
        ]
        assert state["Running"] and not state["OOMKilled"]
        if hashes(root, paths + supporting) != frozen or source_manifest() != manifest:
            raise ValueError("Lab source or verification inputs changed during execution")
        report = {
            "schema_version": 1,
            "recorded_at": datetime.now(UTC).isoformat(),
            "scope": "Actual local Docker Linux image, 41 focused lab/config tests, real HTTP/baseline/review and intentional ephemeral restart under isolated networking/resource flags. Not the full suite inside Linux, a hosted provider, TLS/browser-in-image or durable customer service.",
            "image_id": identity,
            "image_architecture": image["Architecture"],
            "image_python_version": installed["python_version"],
            "image_os": image["Os"],
            "source_sha256": manifest["source_sha256"],
            "source_unchanged": True,
            "build_context_files": len(paths),
            "context_scope": "Allowlisted Python source/locks, two synthetic fixtures, four named public reports and dedicated lab frontend only. No repository history, credentials, private observations, external contracts, owner documents or host runtime/cache copied into build context. Engine-managed image/build caches remain in Docker storage.",
            "input_sha256": frozen,
            "linux_tests_passed": len(cases),
            "linux_junit_sha256": hashlib.sha256(junit).hexdigest(),
            "runtime_constraints": {
                "uid": 10001,
                "network": "none",
                "host_ports": False,
                "root_read_only": True,
                "memory_limit_bytes": host["Memory"],
                "swap_limit_bytes": host["MemorySwap"],
                "pids_limit": host["PidsLimit"],
                "cpus": 1,
                "capabilities_dropped": "ALL",
                "no_new_privileges": True,
            },
            "observed_cgroup_memory_peak_bytes_before_restart": peak,
            "memory_scope": "Cgroup peak after focused tests and first HTTP exercise, when available; includes accounted memory/cache, not process RSS or a representative peak under load. Does not cover build memory or all future workloads.",
            "before_restart": before,
            "after_restart": after,
            "dependency_check_passed": True,
            "runtime_model_provider_calls": 0,
            "base_image_scope": "Official public image index digests pinned in Dockerfile.lab; not a vulnerability scan, signed build or cross-architecture validation.",
        }
        publish_report(Path("reports/synthetic-lab-container.json"), report)
        print(
            json.dumps(
                {
                    "linux_tests_passed": len(cases),
                    "before_restart": before,
                    "after_restart": after,
                    "cgroup_peak_bytes": peak,
                }
            )
        )
    finally:
        if started:
            try:
                with (private / "server.log").open("w") as log:
                    subprocess.run(
                        [args.docker, "logs", name],
                        stdout=log,
                        stderr=subprocess.STDOUT,
                        timeout=30,
                    )
            finally:
                docker("rm", "--force", name, stdout=subprocess.DEVNULL)


if __name__ == "__main__":
    main()
