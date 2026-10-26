"""Rehearse fictional PDF/DOCX intake with an isolated local API, worker and database."""

import argparse
import hashlib
import json
import os
import secrets
import shutil
import subprocess
import sys
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
INPUTS = [
    "apps/web/e2e/workbench.spec.ts",
    "datasets/documents/municipal-rfp.pdf",
    "datasets/documents/capability-register.docx",
    "scripts/verify_document_review.py",
]


def fingerprints():
    names = set(INPUTS)
    for directory, pattern in (("src", "*.py"), ("apps/web/src", "*"), ("apps/web/dist", "*")):
        names.update(
            p.relative_to(ROOT).as_posix() for p in (ROOT / directory).rglob(pattern) if p.is_file()
        )
    if not (ROOT / "apps/web/dist/index.html").is_file():
        raise ValueError("Build the private workbench before rehearsing it")
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in sorted(names)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--node", default=shutil.which("node"))
    parser.add_argument(
        "--pnpm", default=shutil.which("pnpm"), help="pnpm executable or .cjs script"
    )
    parser.add_argument(
        "--all-workflows",
        action="store_true",
        help="Run the full connected-workbench file, including controlled-response cases",
    )
    parser.add_argument(
        "--output", type=Path, default=ROOT / "reports/document-review-rehearsal.json"
    )
    args = parser.parse_args()
    if not args.output.resolve().is_relative_to(
        ROOT / "reports"
    ) and not args.output.resolve().is_relative_to(ROOT / "var"):
        parser.error("Keep the report inside portfolio reports or var")
    if not args.node or not args.pnpm:
        parser.error("Install Node/pnpm or provide their paths")
    frozen = fingerprints()
    run = ROOT / "var/intake-rehearsal" / uuid4().hex
    run.mkdir(parents=True, mode=0o700)
    credentials = run / "credentials.json"
    credentials.write_text(
        json.dumps(
            {
                secrets.token_urlsafe(32): {
                    "tenant": "intake-rehearsal",
                    "actor": "rehearsal-reviewer",
                    "role": "reviewer",
                }
            }
        )
    )
    credentials.chmod(0o600)
    env = {
        key: value for key, value in os.environ.items() if not key.startswith(("ATLAS_", "AWS_"))
    }
    env.update(
        PYTHONPATH=str(ROOT / "src"),
        ATLAS_DATABASE_URL="sqlite:///" + str(run / "review.db"),
        ATLAS_PRINCIPALS=credentials.read_text(),
        ATLAS_TEST_CREDENTIALS=str(credentials),
        ATLAS_TEST_URL="http://127.0.0.1:8136",
        PLAYWRIGHT_BROWSERS_PATH=str(ROOT / ".cache/playwright"),
        PLAYWRIGHT_JSON_OUTPUT_NAME=str(run / "browser.json"),
        TMPDIR=str(ROOT / "var/ui-review/tmp"),
    )
    Path(env["TMPDIR"]).mkdir(parents=True, exist_ok=True)
    env["PATH"] = str(Path(args.node).absolute().parent) + os.pathsep + env["PATH"]
    processes, logs = [], []
    try:
        for name, command in (
            (
                "api",
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "atlas.api:create_app",
                    "--factory",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "8136",
                    "--no-access-log",
                ],
            ),
            ("worker", [sys.executable, "-m", "atlas.worker"]),
        ):
            log = (run / f"{name}.log").open("w")
            logs.append(log)
            processes.append(
                subprocess.Popen(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
            )
            if name == "api":
                for _ in range(100):
                    if processes[-1].poll() is not None:
                        raise RuntimeError("API failed; private log retained")
                    try:
                        with urllib.request.urlopen(
                            env["ATLAS_TEST_URL"] + "/healthz", timeout=1
                        ) as response:
                            if response.status == 200:
                                break
                    except OSError:
                        time.sleep(0.1)
                else:
                    raise RuntimeError("API readiness timed out")
        pnpm = [args.node, args.pnpm] if args.pnpm.endswith((".cjs", ".js")) else [args.pnpm]
        with (run / "browser.log").open("w") as log:
            result = subprocess.run(
                [
                    *pnpm,
                    "--dir",
                    "apps/web",
                    "exec",
                    "playwright",
                    "test",
                    "e2e/workbench.spec.ts",
                    *([] if args.all_workflows else ["--grep", "upload PDF and DOCX"]),
                    "--workers=1",
                    "--retries=0",
                    "--reporter=json",
                ],
                cwd=ROOT,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=90,
            )
        evidence = (run / "browser.json").read_bytes()
        browser = json.loads(evidence)
        stats = browser["stats"]
        if (
            result.returncode
            or stats["expected"] < 1
            or (not args.all_workflows and stats["expected"] != 1)
            or browser.get("errors")
            or any(stats[key] for key in ("unexpected", "flaky", "skipped"))
        ):
            raise RuntimeError("Intake rehearsal failed; private evidence retained")
        if fingerprints() != frozen:
            raise ValueError("Intake test or fixtures changed during execution")
        report = {
            "recorded_at": datetime.now(UTC).isoformat(),
            "scope": "One real Chromium workflow through an isolated loopback API, worker and SQLite database using fresh synthetic bearer credentials. PDF/DOCX upload, queued baseline, exact page mapping and original bytes, conflict approval blocked, rejection saved, reconnect/reload persistence, audit note and disconnect checked. No Cognito, deployed identity, TLS, PostgreSQL, cross-tenant or restart acceptance claim.",
            "browser_workflows_passed": stats["expected"],
            "authentication": "fresh private local bearer; not external sign-in",
            "database": "new isolated SQLite database; no existing workspace changed",
            "input_sha256": {name: frozen[name] for name in INPUTS},
            "source_and_build_manifest_sha256": hashlib.sha256(
                json.dumps(frozen, sort_keys=True).encode()
            ).hexdigest(),
            "manifest_files": len(frozen),
            "provenance_scope": "Source and built artifact hashes checked before and after the rehearsal. Not signed execution provenance or an attestation of every loaded dependency.",
            "browser_evidence_sha256": hashlib.sha256(evidence).hexdigest(),
            "new_model_provider_calls": 0,
        }
        if args.all_workflows:
            report["scope"] = (
                "All connected-workbench cases in the fingerprinted browser test file, through an isolated loopback API/worker/SQLite profile. Includes real intake/source/review persistence and controlled-response quality, execution-mode and identity display cases. Controlled cases are not new model calls, identity-provider acceptance or deployed hosting."
            )
        args.output.write_text(json.dumps(report, indent=2) + "\n")
        print(
            json.dumps({"passed": True, "browser_workflows": stats["expected"], "model_calls": 0})
        )
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
        for log in logs:
            log.close()


if __name__ == "__main__":
    main()
