"""Independent recovery scoring with bounded, disposable adapter processes."""

import argparse
import hashlib
import json
import math
import platform
import re
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

from .__main__ import source_digest
from .artifacts import publish_report
from .execution import AdapterDeadline, AdapterFailure, AdapterOutputBudget, invoke

COUNTERS = {"attempts", "results", "results_after_interruption", "owners"}
FLAGS = {
    "stale_worker_rejected",
    "premature_retry_blocked",
    "exhausted_retry_blocked",
    "self_approval_rejected",
}
STATES = {"status", "status_after_interruption"}
KNOWN_STATES = {"queued", "running", "retry_wait", "succeeded", "failed", "cancelled"}


def evaluate(expected, observed):
    return {
        key: type(observed.get(key)) is type(value) and observed.get(key) == value
        for key, value in expected.items()
    }


def allowed_value(key, value):
    if key in COUNTERS:
        return type(value) is int and 0 <= value <= 10_000
    if key in FLAGS:
        return type(value) is bool
    return key in STATES and type(value) is str and value in KNOWN_STATES


def read_dataset(path):
    with path.open("rb") as handle:
        raw = handle.read(8_000_001)
    if len(raw) > 8_000_000:
        raise ValueError("Recovery dataset exceeds byte budget")

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate recovery JSON field")
            result[key] = value
        return result

    def invalid(_):
        raise ValueError("Non-finite recovery JSON constant")

    dataset = json.loads(raw, object_pairs_hook=unique, parse_constant=invalid)
    if (
        not isinstance(dataset, dict)
        or set(dataset) != {"version", "scope", "cases"}
        or dataset["version"] != "1.0"
        or not isinstance(dataset["scope"], str)
        or not 1 <= len(dataset["scope"]) <= 2000
        or not isinstance(dataset["cases"], list)
        or not 1 <= len(dataset["cases"]) <= 32
    ):
        raise ValueError("Invalid recovery dataset envelope")
    seen = set()
    for case in dataset["cases"]:
        if (
            not isinstance(case, dict)
            or set(case) != {"id", "input", "expected"}
            or not isinstance(case["id"], str)
            or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", case["id"])
            or case["id"] in seen
            or not isinstance(case["input"], dict)
            or not isinstance(case["expected"], dict)
            or not case["expected"]
            or not all(allowed_value(k, v) for k, v in case["expected"].items())
        ):
            raise ValueError("Invalid recovery case contract")
        seen.add(case["id"])
    return raw, dataset


def run(dataset_path, adapter, output_path, *, deadline_seconds=10):
    dataset_path, output_path = Path(dataset_path), Path(output_path)
    if (
        type(deadline_seconds) not in {int, float}
        or not math.isfinite(deadline_seconds)
        or not 0 < deadline_seconds <= 120
    ):
        raise ValueError("Invalid recovery adapter deadline")
    if not re.fullmatch(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*:[A-Za-z_]\w*", adapter):
        raise ValueError("Adapter must be an explicit trusted module:function")
    if (
        output_path.resolve() == dataset_path.resolve()
        or output_path.suffix != ".json"
        or output_path.resolve().is_relative_to(Path("datasets").resolve())
    ):
        raise ValueError("Recovery output must not overwrite a dataset")
    raw, dataset = read_dataset(dataset_path)
    source_before = source_digest()
    cases = []
    for case in dataset["cases"]:
        started = time.perf_counter()
        try:
            output = invoke(adapter, case["input"], deadline_seconds=deadline_seconds)
            observed = output.get("observations")
            if not isinstance(observed, dict):
                raise ValueError("Invalid recovery observations")
            checks = evaluate(case["expected"], observed)
            result = {
                "id": case["id"],
                "passed": all(checks.values()),
                "checks": checks,
                # Only contract-owned keys and finite bounded values leave the adapter boundary.
                "observations": {
                    key: observed[key] if allowed_value(key, observed.get(key)) else None
                    for key in case["expected"]
                },
            }
        except Exception as exc:
            code = (
                "adapter_deadline"
                if isinstance(exc, AdapterDeadline)
                else "adapter_output_budget"
                if isinstance(exc, AdapterOutputBudget)
                else "adapter_failure"
                if isinstance(exc, AdapterFailure)
                else "invalid_observations"
                if isinstance(exc, ValueError)
                else "execution_error"
            )
            result = {"id": case["id"], "passed": False, "error_code": code}
        result["latency_ms"] = (time.perf_counter() - started) * 1000
        cases.append(result)
    if source_before != source_digest() or raw != dataset_path.read_bytes():
        raise ValueError("Recovery source or dataset changed during execution")
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    report = {
        "schema_version": 2,
        "kind": "workflow_recovery",
        "generated_at": datetime.now(UTC).isoformat(),
        "scope": dataset["scope"],
        "execution_scope": "One disposable trusted adapter process per case; bounded input/artifacts and parent deadline. Not a hostile-code sandbox. Cases use the fixture's simulated lease time unless stated otherwise.",
        "adapter": adapter,
        "adapter_deadline_seconds": deadline_seconds,
        "dataset_sha256": hashlib.sha256(raw).hexdigest(),
        "source_sha256": source_before,
        "source_unchanged": True,
        "source_scope": "On-disk src Python bytes checked before/after; not installed dependency or loaded-code attestation. External adapter code outside src is not covered.",
        "revision": revision,
        "working_tree_dirty": bool(
            subprocess.check_output(["git", "status", "--porcelain"], text=True).strip()
        ),
        "python": platform.python_version(),
        "environment": platform.platform(),
        "unique_cases": len(cases),
        "cases_passed": sum(c["passed"] for c in cases),
        "results": cases,
    }
    publish_report(output_path, report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default="datasets/recovery.json")
    parser.add_argument("--adapter", default="atlas.recovery_adapter:run")
    parser.add_argument("--output", default="reports/recovery.json")
    parser.add_argument("--deadline-seconds", type=float, default=10)
    args = parser.parse_args()
    report = run(args.dataset, args.adapter, args.output, deadline_seconds=args.deadline_seconds)
    print(
        json.dumps({"cases_passed": report["cases_passed"], "unique_cases": report["unique_cases"]})
    )
    raise SystemExit(0 if report["cases_passed"] == report["unique_cases"] else 1)


if __name__ == "__main__":
    main()
