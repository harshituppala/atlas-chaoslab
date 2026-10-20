"""Record an actual completed JUnit run and live server identity without credentials."""

import hashlib
import json
import platform
from datetime import UTC, datetime
from pathlib import Path

import psycopg
from defusedxml.ElementTree import fromstring

from chaoslab.artifacts import publish_report


def main():
    junit = Path("var/postgresql/integration.xml").read_bytes()
    root = fromstring(junit, forbid_dtd=True)
    manifest = json.loads(Path("var/postgresql/run-manifest.json").read_text())
    if (
        manifest["exit_status"] != 0
        or manifest["junit_sha256"] != hashlib.sha256(junit).hexdigest()
    ):
        raise SystemExit("JUnit evidence does not match a successful captured execution manifest")
    cases = list(root.iter("testcase"))
    if not cases or any(
        c.find("failure") is not None
        or c.find("error") is not None
        or c.find("skipped") is not None
        for c in cases
    ):
        raise SystemExit("Only a complete successful real PostgreSQL run can be recorded")
    config = json.loads(Path("var/postgresql/client.json").read_text())
    with psycopg.connect(**config) as connection:
        version = connection.execute("SHOW server_version").fetchone()[0]
        vector = connection.execute(
            "SELECT default_version FROM pg_available_extensions WHERE name='vector'"
        ).fetchone()[0]
    report = {
        "schema_version": 1,
        "kind": "postgres_integration",
        "generated_at": datetime.now(UTC).isoformat(),
        "server_version": version,
        "pgvector_available_version": vector,
        "scope": f"{len(cases)} authored local PostgreSQL test groups on disposable schemas; includes 24 jobs/eight concurrent consumers, transactional migration rollback, bounded persistent vector-cache correctness and a real CPU encoder/cache-reuse group when prepared. Synthetic encoders in correctness tests are not AI-quality evidence. Not a load SLA, RLS security proof, model faithfulness or cloud/container validation.",
        "postgres_source": json.loads(Path(".cache/postgresql/source-provenance.json").read_text()),
        "pgvector_source": json.loads(
            Path(".cache/postgresql/pgvector-provenance.json").read_text()
        ),
        "junit_sha256": hashlib.sha256(junit).hexdigest(),
        "source_sha256": manifest["source_sha256"],
        "test_file_sha256": manifest["test_file_sha256"],
        "execution_provenance": manifest,
        "revision": manifest["revision"],
        "working_tree_dirty": manifest["working_tree_dirty"],
        "environment": platform.platform(),
        "python": platform.python_version(),
        "groups_passed": len(cases),
        "results": [
            {"id": c.get("name"), "passed": True, "duration_seconds": float(c.get("time", "0"))}
            for c in cases
        ],
    }
    publish_report(Path("reports/postgres.json"), report)
    print(
        json.dumps(
            {
                "groups_passed": len(cases),
                "server_version": version,
                "pgvector_available_version": vector,
            }
        )
    )


if __name__ == "__main__":
    main()
