"""Independent, JSON-contract evaluation runner with per-case artifacts."""

import argparse
import hashlib
import json
import math
import platform
import re
import statistics
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

from .artifacts import publish_report
from .execution import invoke


def citation_valid(citation, documents):
    try:
        doc = documents[citation["document_id"]]
        start, end = citation["start"], citation["end"]
        return (
            type(start) is int
            and type(end) is int
            and 0 <= start < end <= len(doc["text"])
            and citation["digest"] == hashlib.sha256(doc["text"].encode()).hexdigest()
            and doc["text"][start:end] == citation["quote"]
        )
    except (KeyError, TypeError):
        return False


def wilson(successes, total):
    if total == 0:
        return None
    z = 1.96
    p = successes / total
    denom = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denom
    radius = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denom
    return [max(0, center - radius), min(1, center + radius)]


def evaluate(case, result):
    documents = {d["id"]: d for d in [case["input"]["rfp"], *case["input"]["knowledge"]]}
    items = result["assessments"]
    expected = {e["text"]: e["status"] for e in case["expected"]}
    actual = {a["requirement"]["text"]: a["status"] for a in items}
    tp = len(set(expected) & set(actual))
    citations = [c for item in items for c in [item["requirement"]["source"], *item["evidence"]]]
    valid = sum(citation_valid(c, documents) for c in citations)
    forbidden = set(case.get("forbidden_citations", []))
    injection_safe = all(
        c["document_id"] not in forbidden for item in items for c in item["evidence"]
    )
    source_grounded = all(
        (item["status"] == "missing_evidence") == (not item["evidence"]) for item in items
    )
    trace = result["trace"]
    trace_valid = (
        len(trace) == 3
        and [entry.get("stage") for entry in trace]
        == ["extract", "retrieve_and_assess", "validate"]
        and type(trace[0].get("count")) is int
        and trace[0]["count"] == len(items)
        and type(trace[1].get("attempts")) is int
        and type(trace[1].get("failures")) is int
        and 0 <= trace[1]["failures"] <= trace[1]["attempts"]
        and len(items) <= trace[1]["attempts"] <= 2 * len(items)
        and trace[2].get("citations_valid") is True
        and all(
            type(entry.get("duration_ms")) in {int, float}
            and math.isfinite(entry["duration_ms"])
            and entry["duration_ms"] >= 0
            for entry in trace[:2]
        )
    )
    knowledge_ids = {document["id"] for document in case["input"]["knowledge"]}
    checks = {
        "no_duplicate_requirements": len(items) == len(actual),
        "expected_requirements": set(expected) == set(actual),
        "expected_assessments": actual == expected,
        "citation_integrity": valid == len(citations),
        "known_injection_excluded": injection_safe,
        "evidence_gate": source_grounded,
        "requirement_source_binding": all(
            item["requirement"]["source"]["document_id"] == case["input"]["rfp"]["id"]
            and item["requirement"]["source"]["quote"] == item["requirement"]["text"]
            for item in items
        ),
        "evidence_source_scope": all(
            citation["document_id"] in knowledge_ids
            for item in items
            for citation in item["evidence"]
        ),
        "human_review_pending": all(
            item.get("review_state") == "pending"
            and type(item.get("version")) is int
            and item["version"] == 1
            for item in items
        ),
        "extractive_draft_binding": all(
            item.get("draft")
            == (
                "Evidence excerpts for human assessment:\n"
                + "\n".join(c["quote"] for c in item["evidence"])
                if item["evidence"]
                else "No supporting evidence located. A reviewer must obtain evidence before responding."
            )
            for item in items
        ),
        "bounded_retrieval": trace_valid,
    }
    return {
        "checks": checks,
        "passed": all(checks.values()),
        "extraction_tp": tp,
        "extraction_expected": len(expected),
        "extraction_actual": len(items),
        "status_correct": sum(actual.get(k) == v for k, v in expected.items()),
        "citation_valid": valid,
        "citation_total": len(citations),
    }


def source_digest():
    digest = hashlib.sha256()
    for path in sorted(Path("src").rglob("*.py")):
        digest.update(str(path).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def public_trace(trace):
    fields = (
        ("stage", "duration_ms", "count"),
        ("stage", "duration_ms", "attempts", "failures"),
        ("stage", "citations_valid"),
    )
    return [
        {key: entry[key] for key in allowed} for entry, allowed in zip(trace, fields, strict=True)
    ]


def reported_model_cost(output):
    value = output.get("external_model_cost_usd")
    return (
        value
        if type(value) in {int, float} and math.isfinite(value) and 0 <= value <= 1_000_000
        else None
    )


def reported_pipeline(output):
    value = output.get("pipeline_version")
    return (
        value if isinstance(value, str) and re.fullmatch(r"extractive-v[0-9]{1,4}", value) else None
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="datasets/golden.json")
    parser.add_argument("--adapter", default="atlas.chaos_adapter:run")
    parser.add_argument("--output", default="reports/baseline.json")
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--deadline-seconds", type=float, default=10)
    args = parser.parse_args()
    if not 1 <= args.repeat <= 100:
        parser.error("repeat must be 1..100")
    raw = Path(args.dataset).read_bytes()
    dataset = json.loads(raw)
    cases = dataset["cases"]
    if not 1 <= len(cases) <= 200 or len({case["id"] for case in cases}) != len(cases):
        parser.error("Dataset requires 1..200 distinctly identified authored cases")
    started_at = datetime.now(UTC).isoformat()
    frozen_source = source_digest()
    try:
        revision = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
        dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], text=True).strip())
    except (subprocess.CalledProcessError, FileNotFoundError):
        # Packaged images intentionally omit Git and repository metadata.
        # The separately frozen source digest still binds this execution.
        revision, dirty = None, None
    if not 0 < args.deadline_seconds <= 120:
        parser.error("deadline must be greater than zero and at most 120 seconds")
    results = []
    for case in dataset["cases"]:
        for repeat in range(args.repeat):
            start = time.perf_counter()
            try:
                output = invoke(
                    args.adapter,
                    case["input"],
                    case.get("fault"),
                    deadline_seconds=args.deadline_seconds,
                )
                scored = evaluate(case, output)
                item = {
                    "id": case["id"],
                    "repeat": repeat,
                    **scored,
                    "trace": public_trace(output["trace"])
                    if scored["checks"]["bounded_retrieval"]
                    else [],
                    "pipeline_version": reported_pipeline(output),
                    "external_model_cost_usd": reported_model_cost(output),
                }
            except Exception as exc:
                item = {
                    "id": case["id"],
                    "repeat": repeat,
                    "passed": False,
                    "error_type": type(exc).__name__,
                }
            item["latency_ms"] = (time.perf_counter() - start) * 1000
            results.append(item)
    # Quality statistics use the first repetition of each case. Repeated timings
    # are NOT independent quality observations and do not increase sample size.
    unique = [r for r in results if r["repeat"] == 0]
    total_expected = sum(
        r.get("extraction_expected", len(dataset["cases"][i]["expected"]))
        for i, r in enumerate(unique)
    )
    tp = sum(r.get("extraction_tp", 0) for r in unique)
    total_actual = sum(r.get("extraction_actual", 0) for r in unique)
    citation_total = sum(r.get("citation_total", 0) for r in unique)
    citation_valid_count = sum(r.get("citation_valid", 0) for r in unique)
    case_success = {
        case["id"]: all(r["passed"] for r in results if r["id"] == case["id"])
        for case in dataset["cases"]
    }
    passed = sum(case_success.values())
    times = sorted(r["latency_ms"] for r in results)
    if source_digest() != frozen_source or Path(args.dataset).read_bytes() != raw:
        raise SystemExit("Source or dataset changed during execution; report publication refused")
    report = {
        "schema_version": 2,
        "started_at": started_at,
        "generated_at": datetime.now(UTC).isoformat(),
        "adapter": args.adapter,
        "dataset_sha256": hashlib.sha256(raw).hexdigest(),
        "source_sha256": frozen_source,
        "revision": revision,
        "working_tree_dirty": dirty,
        "environment": platform.platform(),
        "python": platform.python_version(),
        "scope": dataset.get(
            "scope",
            "Synthetic extractive baseline. No live LLM, semantic retrieval, legal judgement, or production SLA evaluated.",
        ),
        "unique_cases": len(unique),
        "timing_repetitions": args.repeat,
        "execution": {
            "isolation": "trusted adapter subprocess",
            "deadline_seconds": args.deadline_seconds,
            "input_byte_budget": 1500000,
            "output_byte_budget": 2000000,
            "hostile_code_sandbox": False,
        },
        "latency_scope": "End-to-end local child startup, adapter execution, serialization and scoring; not an API service SLA.",
        "case_pass_basis": "Every repetition must pass for a case; quality counts use first repetition only. Repetitions do not increase the authored sample size.",
        "repeat_inconsistent_cases": [
            case["id"]
            for case in dataset["cases"]
            if len({r["passed"] for r in results if r["id"] == case["id"]}) > 1
        ],
        "case_outcomes": case_success,
        "case_pass_rate": passed / len(unique),
        "case_pass_wilson_95": wilson(passed, len(unique)),
        "extraction_precision": tp / total_actual if total_actual else None,
        "extraction_recall": tp / total_expected if total_expected else None,
        "assessment_accuracy": sum(r.get("status_correct", 0) for r in unique) / total_expected
        if total_expected
        else None,
        "citation_integrity": citation_valid_count / citation_total if citation_total else None,
        "latency_median_ms": statistics.median(times),
        "latency_p95_ms": times[math.ceil(0.95 * len(times)) - 1],
        "external_model_cost_usd": sum(r["external_model_cost_usd"] for r in results)
        if all(r.get("external_model_cost_usd") is not None for r in results)
        else None,
        "cost_scope": "External model API calls only. Compute/storage/development cost excluded.",
        "results": results,
    }
    path = Path(args.output)
    publish_report(path, report)
    print(
        json.dumps(
            {
                k: report[k]
                for k in [
                    "unique_cases",
                    "case_pass_rate",
                    "extraction_precision",
                    "extraction_recall",
                    "citation_integrity",
                    "latency_median_ms",
                ]
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
