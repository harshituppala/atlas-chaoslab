"""Independent comparison of observed recovery behavior with authored fixtures."""

import argparse
import hashlib
import importlib
import json
import platform
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

from .artifacts import publish_report


def evaluate(expected, observed):
    return {
        key: type(observed.get(key)) is type(value) and observed.get(key) == value
        for key, value in expected.items()
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="datasets/recovery.json")
    parser.add_argument("--adapter", default="atlas.recovery_adapter:run")
    parser.add_argument("--output", default="reports/recovery.json")
    args = parser.parse_args()
    raw = Path(args.dataset).read_bytes()
    dataset = json.loads(raw)
    module, function = args.adapter.split(":")
    adapter = getattr(importlib.import_module(module), function)
    cases = []
    for case in dataset["cases"]:
        started = time.perf_counter()
        try:
            output = adapter(case["input"])
            checks = evaluate(case["expected"], output["observations"])
            result = {
                "id": case["id"],
                "passed": all(checks.values()),
                "checks": checks,
                "observations": output["observations"],
                "events": output.get("events", []),
            }
        except Exception as exc:
            result = {"id": case["id"], "passed": False, "error_type": type(exc).__name__}
        result["latency_ms"] = (time.perf_counter() - started) * 1000
        cases.append(result)
    source = hashlib.sha256()
    for path in sorted(Path("src").rglob("*.py")):
        source.update(str(path).encode())
        source.update(path.read_bytes())
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    report = {
        "schema_version": 1,
        "kind": "workflow_recovery",
        "generated_at": datetime.now(UTC).isoformat(),
        "scope": dataset["scope"],
        "adapter": args.adapter,
        "dataset_sha256": hashlib.sha256(raw).hexdigest(),
        "source_sha256": source.hexdigest(),
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
    path = Path(args.output)
    publish_report(path, report, default=str)
    print(
        json.dumps({"cases_passed": report["cases_passed"], "unique_cases": len(cases)}, indent=2)
    )
    raise SystemExit(0 if all(c["passed"] for c in cases) else 1)


if __name__ == "__main__":
    main()
