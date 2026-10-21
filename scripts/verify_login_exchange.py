"""Record offline login-component checks; never contact or configure a provider."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]


def tree_hash(directory):
    digest = hashlib.sha256()
    for path in sorted((ROOT / directory).rglob("*.py")):
        digest.update(path.relative_to(ROOT).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--http-sessions", action="store_true")
    args = parser.parse_args()
    focused = ["tests/test_login_exchange.py"]
    if args.http_sessions:
        focused += ["tests/test_browser_sessions.py", "tests/test_http_privacy.py"]
    source_before, tests_before = tree_hash("src"), tree_hash("tests")
    script_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    work = ROOT / "var/login-exchange" / uuid4().hex[:12]
    work.mkdir(parents=True)
    started = datetime.now(UTC).isoformat()
    results = {}
    for label, targets in (("focused", focused), ("native", [])):
        xml = work / f"{label}.xml"
        command = [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            *targets,
            "--basetemp",
            str(work / label),
            "--junitxml",
            str(xml),
        ]
        result = subprocess.run(
            command,
            cwd=ROOT,
            env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
            capture_output=True,
            text=True,
        )
        (work / f"{label}.log").write_text(result.stdout + result.stderr)
        if result.returncode != 0:
            raise RuntimeError(f"Offline {label} checks failed; inspect {work.name}/{label}.log")
        suites = list(ElementTree.parse(xml).getroot().iter("testsuite"))
        totals = {
            key: sum(int(suite.get(key, 0)) for suite in suites)
            for key in ("tests", "failures", "errors", "skipped")
        }
        assert totals["tests"] > 0 and totals["failures"] == totals["errors"] == 0
        results[label] = {
            **totals,
            "passed": totals["tests"] - totals["skipped"],
            "junit_sha256": hashlib.sha256(xml.read_bytes()).hexdigest(),
        }
    if (
        source_before != tree_hash("src")
        or tests_before != tree_hash("tests")
        or script_hash != hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    ):
        raise RuntimeError("Source or tests changed; offline report publication refused")
    report = {
        "started_at": started,
        "recorded_at": datetime.now(UTC).isoformat(),
        "scope": "Controlled ASGI HTTPS/session requests, token/key services and RSA-signed synthetic JWTs. No actual browser, AWS user pool or deployed identity flow validated."
        if args.http_sessions
        else "Offline backend exchange component; controlled provider/key services and synthetic RSA JWTs. No real provider/browser acceptance.",
        "source_sha256": source_before,
        "test_sources_sha256": tests_before,
        "verifier_script_sha256": script_hash,
        "checks": results,
        "provider_network_calls": 0,
        "cloud_resources_created": 0,
        "default_browser_routes_enabled": False,
        "opt_in_http_routes_exercised": args.http_sessions,
        "limits": "Process-local attempts/sessions; explicit factory opt-in only. The workbench UI and actual browser/provider login remain unfinished. No distributed session backend, refresh-token storage, provider logout or deployed proxy-log acceptance. Controlled HTTP clients do not enforce browser SameSite behavior.",
    }
    output = ROOT / (
        "reports/browser-sessions-offline.json"
        if args.http_sessions
        else "reports/login-exchange-offline.json"
    )
    temporary = work / "report.json"
    temporary.write_text(json.dumps(report, indent=2) + "\n")
    os.replace(temporary, output)
    print(
        json.dumps(
            {
                label: {key: row[key] for key in ("passed", "skipped")}
                for label, row in results.items()
            }
        )
    )


if __name__ == "__main__":
    main()
