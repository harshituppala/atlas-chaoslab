"""Destructive only to the verifier's uniquely named synthetic Compose project.

Copy a logical archive out, delete its source volume, restore into a fresh cluster,
reprovision global roles, compare all application table rows, and resume queued work.
"""

import hashlib
import json
import subprocess
import time
from datetime import UTC, datetime


def exercise(compose, private, root, request):
    def fixture(action):
        return json.loads(
            compose(
                "run",
                "--rm",
                "--no-deps",
                "-T",
                "--volume",
                f"{root / 'scripts/backup_fixture.py'}:/app/backup_fixture.py:ro",
                "initialize",
                "python",
                "/app/backup_fixture.py",
                action,
                capture=True,
            )
        )

    compose("stop", "worker")
    seeded = fixture("seed")
    body = json.loads((root / "datasets/demo.json").read_text())
    code, queued = request("/api/jobs", "analyst", body, key="backup-pending-job-001")
    assert code == 202 and queued["status"] == "queued"
    compose("stop", "api")  # Quiesce writers for row equality; pg_dump also owns its MVCC snapshot.
    before = fixture("manifest")
    assert before and all(table["rows"] > 0 for table in before.values())
    started = datetime.now(UTC).isoformat()
    compose(
        "exec",
        "-T",
        "postgres",
        "pg_dump",
        "--username=atlas_owner",
        "--dbname=atlas",
        "--format=custom",
        "--file=/tmp/atlas-recovery.dump",
    )
    archive = private / "atlas-recovery.dump"
    compose("cp", "postgres:/tmp/atlas-recovery.dump", str(archive))
    archive.chmod(0o600)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    assert archive.stat().st_size > 0
    broken = private / "truncated.dump"
    broken.write_bytes(archive.read_bytes()[:32])
    broken.chmod(0o600)
    # Destroy original database storage before restoring, rather than merely reattaching it.
    compose("down", "--volumes")
    compose("up", "-d", "--no-build", "--wait", "--wait-timeout", "120", "postgres")
    empty = compose(
        "exec",
        "-T",
        "postgres",
        "psql",
        "--username=atlas_owner",
        "--dbname=atlas",
        "--tuples-only",
        "--no-align",
        "--command",
        "SELECT (SELECT count(*) FROM information_schema.tables WHERE table_schema='atlas'), "
        "(SELECT count(*) FROM pg_roles WHERE rolname IN ('atlas_api','atlas_worker'))",
        capture=True,
    ).strip()
    assert empty == "0|0", "Restoration destination is not an empty freshly provisioned cluster"
    if hashlib.sha256(archive.read_bytes()).hexdigest() != digest:
        raise RuntimeError("Archive changed before restoration")
    compose("cp", str(archive), "postgres:/tmp/atlas-recovery.dump")
    compose(
        "exec",
        "-T",
        "postgres",
        "pg_restore",
        "--username=atlas_owner",
        "--dbname=atlas",
        "--exit-on-error",
        "--single-transaction",
        "--no-owner",
        "--no-acl",
        "/tmp/atlas-recovery.dump",
    )
    compose("cp", str(broken), "postgres:/tmp/truncated.dump")
    rejected = False
    try:
        compose(
            "exec",
            "-T",
            "postgres",
            "pg_restore",
            "--username=atlas_owner",
            "--dbname=atlas",
            "--exit-on-error",
            "--single-transaction",
            "--no-owner",
            "--no-acl",
            "/tmp/truncated.dump",
        )
    except subprocess.CalledProcessError:
        rejected = True
    assert rejected
    # Database archives omit global roles; provision fresh credentials/grants explicitly.
    compose("up", "-d", "--no-build", "--wait", "--wait-timeout", "120", "api")
    after = fixture("manifest")
    assert after == before, "Restored table counts/content differ from the backup snapshot"
    checks = fixture("verify")
    assert request("/api/jobs/" + queued["id"])[1]["status"] == "queued"
    assert request("/api/jobs/" + queued["id"], "foreign")[0] == 404
    # The worker was removed with the volume; recreate it explicitly.
    compose("up", "-d", "--no-build", "--no-deps", "worker")
    deadline = time.monotonic() + 40
    while time.monotonic() < deadline:
        job = request("/api/jobs/" + queued["id"])[1]
        if job["status"] in {"succeeded", "failed"}:
            break
        time.sleep(0.1)
    assert job["status"] == "succeeded" and job["attempts"] == 1
    result = {
        "started_at": started,
        "completed_at": datetime.now(UTC).isoformat(),
        "archive_sha256": digest,
        "archive_bytes": archive.stat().st_size,
        "source_database_volume_deleted": True,
        "fresh_cluster_restored": True,
        "empty_destination_and_absent_runtime_roles_verified": True,
        "restore_exit_on_error_and_single_transaction": True,
        "global_roles_reprovisioned": True,
        "table_content_before": before,
        "all_table_digests_match": True,
        "truncated_archive_rejected": rejected,
        "seeded": seeded,
        "functional_checks": checks,
        "restored_queue_resumed_once": True,
        "tenant_isolation": True,
        "scope": "Quiesced synthetic logical pg_dump/pg_restore into a new local cluster. "
        "Row digests cover all atlas tables before resuming writes. Controlled vectors "
        "prove cache persistence, not embedding quality. Archive is private plaintext, "
        "not encrypted or offsite. No WAL/PITR, continuous backup, production RPO/RTO, "
        "live model, external identity login or AWS recovery claim.",
    }
    return result
