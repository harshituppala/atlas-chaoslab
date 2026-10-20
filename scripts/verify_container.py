"""Build and verify the local Linux image without credentials or external test networking.

Build downloads public dependencies. Tests receive only read-only synthetic test assets;
no host credentials, Git directory, AWS configuration, or Docker socket enter the image.
"""

import argparse
import hashlib
import json
import subprocess
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4


def digest(paths):
    entries = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}
    return hashlib.sha256(json.dumps(entries, sort_keys=True).encode()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docker", default="docker")
    args = parser.parse_args()
    root = Path.cwd().resolve()
    paths = list(Path("src").rglob("*.py")) + list(Path("tests").rglob("*.py"))
    paths += [
        Path(p)
        for p in (
            "Dockerfile",
            ".dockerignore",
            "requirements.lock",
            "pyproject.toml",
            "scripts/seed_documents.py",
            "scripts/verify_container.py",
            "scripts/container_workflow.py",
            "deployment/postgres-runtime-roles.sql",
        )
    ]
    paths += [
        p
        for p in Path("apps/web").rglob("*")
        if p.is_file()
        and not any(
            part in {"node_modules", "dist", "test-results", "playwright-report"}
            for part in p.parts
        )
        and p.suffix != ".tsbuildinfo"
    ]
    paths += [p for p in Path("datasets").rglob("*") if p.is_file()]
    frozen = digest(paths)
    started = datetime.now(UTC).isoformat()
    private = root / "var/container-validation" / uuid4().hex
    private.mkdir(parents=True, mode=0o700)
    name = "atlas-verification-" + private.name
    tag = "atlas-local:validation"

    def docker(*command, **kwargs):
        return subprocess.run([args.docker, *command], check=True, timeout=900, **kwargs)

    with (private / "build.log").open("w") as log:
        docker("build", "-t", tag, ".", stdout=log, stderr=subprocess.STDOUT)
    image = json.loads(docker("image", "inspect", tag, capture_output=True, text=True).stdout)[0]
    identity = image["Id"]  # Use immutable image identity for every following command.
    installed_source = docker(
        "run",
        "--rm",
        "--network",
        "none",
        identity,
        "python",
        "-c",
        "from atlas.models.provenance import source_manifest; import json; "
        "print(json.dumps(source_manifest()))",
        capture_output=True,
        text=True,
    )
    from atlas.models.provenance import source_manifest

    manifest = json.loads(installed_source.stdout)
    if manifest["files"] != source_manifest()["files"]:
        raise SystemExit("Built image source differs from local source")
    with (private / "dependencies.log").open("w") as log:
        docker(
            "run",
            "--rm",
            "--network",
            "none",
            identity,
            "python",
            "-m",
            "pip",
            "check",
            stdout=log,
            stderr=subprocess.STDOUT,
        )
    try:
        with (private / "tests.log").open("w") as log:
            result = subprocess.run(
                [
                    args.docker,
                    "run",
                    "--name",
                    name,
                    "--network",
                    "none",
                    "--mount",
                    f"type=bind,src={root / 'tests'},dst=/app/tests,readonly",
                    "--mount",
                    f"type=bind,src={root / 'scripts/seed_documents.py'},"
                    "dst=/app/scripts/seed_documents.py,readonly",
                    "--env",
                    "PYTHONDONTWRITEBYTECODE=1",
                    identity,
                    "python",
                    "-m",
                    "pytest",
                    "-q",
                    "-p",
                    "no:cacheprovider",
                    "--junitxml=/tmp/container-tests.xml",
                ],
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=300,
            )
        docker(
            "cp",
            name + ":/tmp/container-tests.xml",
            str(private / "junit.xml"),
            capture_output=True,
        )
        if result.returncode:
            raise SystemExit(f"Container tests failed; inspect {private / 'tests.log'}")
    finally:
        subprocess.run([args.docker, "rm", "-f", name], capture_output=True, timeout=30)
    workflow = docker(
        "run",
        "--rm",
        "--network",
        "none",
        "--mount",
        f"type=bind,src={root / 'scripts/container_workflow.py'},dst=/app/verify_workflow.py,readonly",
        identity,
        "python",
        "/app/verify_workflow.py",
        capture_output=True,
        text=True,
    )
    (private / "workflow.json").write_text(workflow.stdout)
    workflow_result = json.loads(workflow.stdout)
    if digest(paths) != frozen:
        raise SystemExit("Verification inputs changed during execution; report refused")
    suites = ET.parse(private / "junit.xml").getroot().findall("testsuite")
    counts = {
        key: sum(int(s.attrib.get(key, 0)) for s in suites)
        for key in ("tests", "failures", "errors", "skipped")
    }
    report = {
        "schema_version": 1,
        "started_at": started,
        "completed_at": datetime.now(UTC).isoformat(),
        "image_id": identity,
        "os": image["Os"],
        "architecture": image["Architecture"],
        "runtime_user": image["Config"]["User"],
        "verification_input_sha256": frozen,
        "image_source_sha256": manifest["source_sha256"],
        "source_matches_host": True,
        "inputs_unchanged": True,
        "dependency_check_passed": True,
        "workflow": workflow_result,
        "junit_sha256": hashlib.sha256((private / "junit.xml").read_bytes()).hexdigest(),
        "counts": {**counts, "passed": counts["tests"] - counts["skipped"]},
        "scope": "Real Linux ARM64 image build, dependency consistency, and offline backend "
        "suite as UID 10001. Read-only host tests and fixture generator were mounted; "
        "application source and dependencies came from the image. Real loopback HTTP, "
        "worker, review concurrency and API restarts used temporary SQLite. PostgreSQL and "
        "embedding integrations are skipped. No Compose stack, live provider, browser, "
        "cloud deployment, image scanning or production identity validation is implied. "
        "Hashes are local provenance, not signed execution attestations.",
    }
    Path("reports/container.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report["counts"]))


if __name__ == "__main__":
    main()
