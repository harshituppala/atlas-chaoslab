"""Record real child-supervision checks plus fresh SQLite queue recovery, offline only."""

import hashlib
import json
import tempfile
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path

from atlas.jobs import JobQueue
from atlas.store import Store
from atlas.worker import execute_isolated, process_once
from chaoslab.artifacts import publish_report


def main():
    junit_path = Path("var/worker-supervision-tests.xml")
    junit = junit_path.read_bytes()
    cases = list(ET.fromstring(junit).iter("testcase"))
    focused = [c for c in cases if c.attrib.get("classname", "").endswith("test_child_process")]
    if len(focused) != 18 or any(
        c.find(tag) is not None for c in focused for tag in ("failure", "error", "skipped")
    ):
        raise ValueError("Expected all eighteen actually executed child-supervision checks")
    if any(c.find(tag) is not None for c in cases for tag in ("failure", "error")):
        raise ValueError("Native regression gate failed")
    paths = [
        "src/atlas/child_process.py",
        "src/atlas/worker.py",
        "scripts/verify_worker_supervision.py",
        "datasets/demo.json",
    ]
    frozen = {p: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in paths}
    body = json.loads(Path("datasets/demo.json").read_text())
    root = Path("var/worker-supervision")
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.TemporaryDirectory(dir=root) as directory:
        store = Store("sqlite:///" + str(Path(directory).resolve() / "jobs.db"))
        try:
            queue = JobQueue(store)
            failed = queue.submit("synthetic", "analyst", "timeout-first", body, max_attempts=1)
            assert process_once(
                queue, executor=lambda payload: execute_isolated(payload, timeout_seconds=0.001)
            )
            assert queue.get("synthetic", failed["id"])["status"] == "failed"
            assert len(store.list("synthetic")) == 0
            next_job = queue.submit("synthetic", "analyst", "following-job", body)
            assert process_once(queue)
            completed = queue.get("synthetic", next_job["id"])
            assert completed["status"] == "succeeded" and completed["attempts"] == 1
            result = store.get("synthetic", completed["result_id"])
            assert len(result["assessments"]) == 8
            assert all(a["review_state"] == "pending" for a in result["assessments"])
            citations = sum(1 + len(a["evidence"]) for a in result["assessments"])
        finally:
            store.engine.dispose()
    if frozen != {p: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in paths}:
        raise ValueError("Worker verification source changed during queue exercise")
    report = {
        "schema_version": 1,
        "recorded_at": datetime.now(UTC).isoformat(),
        "scope": "Native POSIX child-process tests and a fresh real SQLite queue/worker timeout-followed-by-success exercise. Model wiring checks use a controlled result, not live inference. Not hostile-code containment, total RSS protection, Linux image or cloud validation.",
        "supervision_cases_passed": len(focused),
        "native_suite": {
            "passed": sum(c.find("skipped") is None for c in cases),
            "skipped": sum(c.find("skipped") is not None for c in cases),
        },
        "queue": {
            "deadline_job_failed_without_result": True,
            "following_job_succeeded": True,
            "following_attempts": completed["attempts"],
            "requirements": 8,
            "validated_citations": citations,
            "all_reviews_pending": True,
        },
        "checks": [
            "concurrent_stdin_stdout_stderr_progress",
            "inclusive_byte_boundaries",
            "stdout_and_stderr_overflow_early_stop",
            "root_reaped_after_timeout_or_overflow",
            "same_group_descendant_heartbeat_stops_on_deadline_and_success",
            "closed_pipe_deadline",
            "input_budget_before_spawn",
            "early_stdin_close",
            "actual_baseline_worker_protocol",
            "controlled_model_supervisor_wiring",
            "uncertain_model_billing_timeout_message",
        ],
        "queue_exercise_source_sha256": frozen,
        "test_source_sha256": hashlib.sha256(
            Path("tests/test_child_process.py").read_bytes()
        ).hexdigest(),
        "junit_sha256": hashlib.sha256(junit).hexdigest(),
        "test_hash_scope": "Test source/JUnit hashes captured after execution; no frozen test-run or signed loaded-code attestation. Queue exercise source hashes separately captured before and checked after.",
        "new_provider_calls": 0,
    }
    publish_report(Path("reports/worker-supervision.json"), report)
    print(json.dumps({"supervision_cases_passed": len(focused), "queue": report["queue"]}))


if __name__ == "__main__":
    main()
