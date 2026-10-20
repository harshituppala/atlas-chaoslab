"""Publish completed local PostgreSQL evidence without upgrading historical provenance."""

import json
import subprocess
from hashlib import sha256
from pathlib import Path

import psycopg
from defusedxml.ElementTree import fromstring

from atlas.models.provenance import source_manifest
from chaoslab.artifacts import publish_report


def main():
    junit = Path("var/postgresql/model-jobs-integration.xml").read_bytes()
    cases = list(fromstring(junit, forbid_dtd=True).iter("testcase"))
    if not cases or any(
        c.find(tag) is not None for c in cases for tag in ("failure", "error", "skipped")
    ):
        raise SystemExit("Require a complete successful PostgreSQL suite")
    if not any(
        c.get("name") == "test_postgres_model_jobs_pinned_publication_review_and_rollback"
        for c in cases
    ):
        raise SystemExit("Model job integration group is missing")
    with psycopg.connect(
        **json.loads(Path("var/postgresql/client.json").read_text())
    ) as connection:
        version = connection.execute("SHOW server_version").fetchone()[0]
    report = {
        "schema_version": 1,
        "scope": "Local PostgreSQL suite on owned disposable schemas; model-job group uses actual restricted SCRAM logins and controlled model output. No paid inference, browser model review, cloud deployment or model accuracy claim.",
        "groups_passed": len(cases),
        "server_version": version,
        "junit_sha256": sha256(junit).hexdigest(),
        "source_sha256_after_execution": source_manifest()["source_sha256"],
        "test_sha256_after_execution": sha256(
            Path("tests/test_postgres.py").read_bytes()
        ).hexdigest(),
        "provenance_limit": "Source/test hashes were recorded after execution; no pre-execution snapshot or signed attestation was captured for this run.",
        "revision_at_recording": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True
        ).strip(),
        "working_tree_dirty_at_recording": bool(
            subprocess.check_output(["git", "status", "--porcelain"], text=True)
        ),
        "results": [
            {"id": c.get("name"), "passed": True, "duration_seconds": float(c.get("time", "0"))}
            for c in cases
        ],
    }
    publish_report(Path("reports/model-job-postgres.json"), report)
    print(json.dumps({"groups_passed": len(cases), "server_version": version}))


if __name__ == "__main__":
    main()
