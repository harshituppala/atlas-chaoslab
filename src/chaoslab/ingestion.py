"""Independently verify extraction hashes, mapping and authored source locations."""

import argparse
import base64
import hashlib
import importlib
import json
import platform
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

from .__main__ import source_digest
from .artifacts import publish_report


def evaluate(raw, expected, observed):
    checks = {"status": observed.get("status") == expected["status"]}
    if expected["status"] == "rejected":
        checks["reason"] = observed.get("reason") == expected["reason"]
        checks["no_partial_document"] = "document" not in observed
        return checks
    document = observed.get("document", {})
    source = document.get("source_map", {})
    text, segments = document.get("text", ""), source.get("segments", [])
    checks["raw_identity"] = source.get("raw_sha256") == hashlib.sha256(raw).hexdigest()
    checks["segment_count"] = len(segments) == expected["segment_count"]
    checks["format"] = source.get("format") == expected["format"]
    if "text" in expected:
        checks["authored_text"] = text == expected["text"]
    previous_end, previous_number = 0, 0
    coherent = isinstance(text, str) and bool(text) and bool(segments)
    for segment in segments:
        start, end, number = segment.get("start"), segment.get("end"), segment.get("number")
        valid = (
            type(start) is int
            and type(end) is int
            and type(number) is int
            and previous_end <= start < end <= len(text)
            and number > previous_number
            and segment.get("unit") == ("page" if expected["format"] == "pdf" else "paragraph")
        )
        if not valid:
            coherent = False
            break
        coherent = coherent and not text[previous_end:start].strip()
        previous_end, previous_number = end, number
    checks["source_map_coverage"] = coherent and not text[previous_end:].strip()
    for index, location in enumerate(expected["locations"]):
        quote = location["quote"]
        # A footer or repeated clause can occur on several pages. Search the
        # authored segment, not only the first occurrence in the entire file.
        checks[f"authored_location_{index + 1}"] = (
            coherent
            and bool(quote)
            and any(
                s["unit"] == location["unit"]
                and s["number"] == location["number"]
                and quote in text[s["start"] : s["end"]]
                for s in segments
            )
        )
    return checks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="datasets/ingestion.json")
    parser.add_argument("--adapter", default="atlas.ingestion_adapter:run")
    parser.add_argument("--output", default="reports/ingestion.json")
    args = parser.parse_args()
    path = Path(args.dataset).resolve()
    dataset_raw = path.read_bytes()
    dataset = json.loads(dataset_raw)
    frozen_source = source_digest()
    module, function = args.adapter.split(":")
    adapter = getattr(importlib.import_module(module), function)
    results, artifacts, snapshots = [], {}, []
    for case in dataset["cases"]:
        inputs = case["input"]
        if "file" in inputs:
            file = (path.parent / inputs["file"]).resolve()
            if not file.is_relative_to(path.parent):
                parser.error("Fixture file must remain inside the dataset directory")
            raw = file.read_bytes()
            artifacts[inputs["file"]] = hashlib.sha256(raw).hexdigest()
        else:
            raw = inputs["raw_ascii"].encode("ascii")
        snapshots.append((case, raw, file if "file" in inputs else None))
    output = Path(args.output)
    if output.resolve() in {path, *(file for _, _, file in snapshots if file is not None)}:
        parser.error("Report output must not overwrite the dataset or a fixture")
    for case, raw, _ in snapshots:
        inputs = case["input"]
        started = time.perf_counter()
        try:
            observed = adapter(
                {
                    "raw_base64": base64.b64encode(raw).decode(),
                    "format": inputs["format"],
                    "kind": inputs["kind"],
                    "title": case["id"],
                }
            )
            checks = evaluate(raw, case["expected"], observed)
            result = {
                "id": case["id"],
                "passed": all(checks.values()),
                "checks": checks,
                "observed_status": observed.get("status"),
                "observed_reason": observed.get("reason"),
            }
        except Exception as exc:
            result = {"id": case["id"], "passed": False, "error_type": type(exc).__name__}
        result["latency_ms"] = (time.perf_counter() - started) * 1000
        results.append(result)
    if (
        source_digest() != frozen_source
        or path.read_bytes() != dataset_raw
        or any(file.read_bytes() != raw for _, raw, file in snapshots if file is not None)
    ):
        raise SystemExit("Ingestion source or inputs changed; report publication refused")
    report = {
        "schema_version": 1,
        "kind": "document_ingestion",
        "generated_at": datetime.now(UTC).isoformat(),
        "scope": dataset["scope"],
        "adapter": args.adapter,
        "dataset_sha256": hashlib.sha256(dataset_raw).hexdigest(),
        "fixture_sha256": artifacts,
        "source_sha256": frozen_source,
        "inputs_verified_unchanged": True,
        "provenance_scope": "Source and fixture bytes frozen before execution and checked before publication; not signed or loaded-bytecode attestation.",
        "revision": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "working_tree_dirty": bool(
            subprocess.check_output(["git", "status", "--porcelain"], text=True).strip()
        ),
        "environment": platform.platform(),
        "python": platform.python_version(),
        "unique_cases": len(results),
        "cases_passed": sum(r["passed"] for r in results),
        "external_inference_calls": 0,
        "results": results,
    }
    publish_report(output, report)
    print(json.dumps({"cases_passed": report["cases_passed"], "unique_cases": len(results)}))
    raise SystemExit(0 if all(r["passed"] for r in results) else 1)


if __name__ == "__main__":
    main()
