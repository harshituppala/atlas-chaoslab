"""Run the deterministic PostgreSQL integration gate; publish no connection data or raw logs."""

import ast
import hashlib
import json
import math
import os
import stat
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import psycopg
from defusedxml.ElementTree import fromstring

from atlas.models.provenance import source_manifest

ROOT = Path(__file__).resolve().parents[1]
EMBEDDING_CASE = "test_postgres_real_cpu_encoder_retrieval_and_new_process_cache_reuse"
REQUIRED = {
    "test_postgres_restricted_login_row_policies_and_pool_reset",
    "test_postgres_restricted_membership_and_worker_grants",
    "test_postgres_runtime_role_guard_and_policy_drift",
    "test_postgres_competing_workers_publish_each_job_once",
    "test_postgres_index_migration_rollback_preserves_revision_and_rows",
    "test_postgres_http_upload_and_job_publication",
}


def admit_results(raw, expected):
    """An all-skipped, incomplete, duplicated or failing run cannot satisfy the gate."""
    if len(raw) > 4_000_000:
        raise ValueError("JUnit evidence exceeds its byte budget")
    cases = list(fromstring(raw, forbid_dtd=True).iter("testcase"))
    names = [case.get("name") for case in cases]
    if len(names) != len(expected) or set(names) != expected:
        raise ValueError("PostgreSQL execution inventory differs")
    for case in cases:
        if any(case.find(status) is not None for status in ("failure", "error", "skipped")):
            raise ValueError("PostgreSQL execution did not pass every selected group")
        seconds = float(case.get("time", "0"))
        if not math.isfinite(seconds) or seconds < 0:
            raise ValueError("Invalid test duration")
    return [{"id": case.get("name"), "passed": True} for case in cases]


def main():
    private = ROOT / "var/postgresql-ci" / uuid4().hex
    private.mkdir(parents=True, mode=0o700)
    output = ROOT / "reports/postgres-ci.json"
    try:
        test_file = ROOT / "tests/test_postgres.py"
        raw_test = test_file.read_bytes()
        names = {
            node.name
            for node in ast.parse(raw_test).body
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
        }
        expected = names - {EMBEDDING_CASE}
        if EMBEDDING_CASE not in names or not REQUIRED <= expected or len(expected) < 17:
            raise ValueError("PostgreSQL test inventory lost required acceptance groups")
        config_path = Path(
            os.environ.get("ATLAS_POSTGRES_CONFIG", ROOT / "var/postgresql/client.json")
        )
        if (
            config_path.is_symlink()
            or not config_path.resolve().is_relative_to(ROOT / "var")
            or stat.S_IMODE(config_path.stat().st_mode) & 0o077
        ):
            raise ValueError("Use a private integration configuration under var")
        config = json.loads(config_path.read_text())
        if config["host"] != "127.0.0.1" or config["dbname"] != "portfolio_integration":
            raise ValueError("Use the dedicated loopback integration database")
        source = source_manifest()
        with psycopg.connect(**config) as connection:
            version = connection.execute("SHOW server_version").fetchone()[0]
            vector = connection.execute(
                "SELECT default_version FROM pg_available_extensions WHERE name='vector'"
            ).fetchone()[0]
        started = time.perf_counter()
        junit = private / "integration.xml"
        env = {
            **os.environ,
            "ATLAS_POSTGRES_CONFIG": str(config_path.absolute()),
            "PYTHONPATH": str(ROOT / "src"),
        }
        with (private / "pytest.log").open("w") as log:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    "-q",
                    "tests/test_postgres.py",
                    "-m",
                    "not embeddings",
                    "--junitxml=" + str(junit),
                    "--basetemp=" + str(private / "pytest"),
                ],
                cwd=ROOT,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=300,
            )
        if result.returncode != 0:
            raise ValueError("PostgreSQL tests failed; private diagnostics retained")
        raw = junit.read_bytes()
        cases = admit_results(raw, expected)
        if source_manifest() != source or test_file.read_bytes() != raw_test:
            raise ValueError("PostgreSQL inputs changed during execution")
        report = {
            "recorded_at": datetime.now(UTC).isoformat(),
            "status": "passed",
            "scope": "Deterministic PostgreSQL integration groups on a dedicated loopback database with disposable schemas. Runtime-boundary groups use real restricted API/worker logins; other fixture/migration groups use an administrator. The trusted worker intentionally has BYPASSRLS. Not hosted acceptance, comprehensive security proof, model quality or an application latency benchmark.",
            "server_version": version,
            "pgvector_available_version": vector,
            "groups_passed": len(cases),
            "results": cases,
            "excluded": {
                "id": EMBEDDING_CASE,
                "reason": "Optional downloaded CPU encoder; excluded explicitly rather than silently skipped. Synthetic vectors still exercise pgvector persistence and isolation.",
            },
            "test_wall_seconds": time.perf_counter() - started,
            "source_sha256": source["source_sha256"],
            "test_file_sha256": hashlib.sha256(raw_test).hexdigest(),
            "verification_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "junit_sha256": hashlib.sha256(raw).hexdigest(),
            "github_run_id": os.getenv("GITHUB_RUN_ID"),
            "github_source_revision": os.getenv("GITHUB_SHA"),
            "privacy": "Only authored test identifiers, counts, versions and fingerprints are exported. Connection configuration, passwords, raw JUnit, logs and database contents remain private.",
            "new_model_provider_calls": 0,
        }
        output.write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps({"status": "passed", "groups": len(cases)}))
    except Exception:
        output.write_text(
            json.dumps(
                {
                    "status": "failed",
                    "diagnostic": "PostgreSQL execution or evidence admission failed; no successful acceptance recorded. Private diagnostics were not exported.",
                },
                indent=2,
            )
            + "\n"
        )
        raise SystemExit("PostgreSQL CI gate failed; inspect private diagnostics locally") from None


if __name__ == "__main__":
    main()
