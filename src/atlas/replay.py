"""Explicit public projection of synthetic recordings; never exports a workspace dump."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from .domain import Assessment, Document
from .execution import execute, validate_publication, validate_sources


def project_recording(payload, body, *, recording_id, title, recorded_at):
    documents = [Document.model_validate(d) for d in payload["documents"]]
    assessments = [
        Assessment.model_validate({k: a[k] for k in Assessment.model_fields})
        for a in payload["assessments"]
    ]
    expected = [Document.model_validate(d) for d in [body["rfp"], *body["knowledge"]]]
    if documents != expected:
        raise ValueError("Recording source snapshot differs from fixture")
    validate_sources(body, SimpleNamespace(documents=documents, assessments=assessments))
    return {
        "id": recording_id,
        "title": title,
        "recorded_at": recorded_at,
        "provider": payload["provider"],
        "pipeline_version": payload["pipeline_version"],
        "documents": [d.model_dump() for d in documents],
        "assessments": [a.model_dump() for a in assessments],
    }


def historical_recording(raw, report):
    if hashlib.sha256(raw).hexdigest() != report["artifact_sha256"] or not report["passed"]:
        raise ValueError("Historical recording does not match executed validation report")
    saved = json.loads(raw)
    result = saved["result"]
    for key in ("provider", "pipeline_version", "model_config_sha256"):
        if result[key] != report[key]:
            raise ValueError("Historical provider identity mismatch")
    # Explicit fixture boundary: this exporter is for the two approved synthetic sentences only.
    body = saved["submitted_input"]
    if body["rfp"]["text"] != "Customer data must remain in Canada." or [
        d["text"] for d in body["knowledge"]
    ] != ["Customer data remains in Canada."]:
        raise ValueError("Historical recording is not the allowlisted synthetic fixture")
    return project_recording(
        result,
        body,
        recording_id="recorded-residency",
        title="Recorded model · residency",
        recorded_at=result["created"],
    )


def prepare(root=Path(".")):
    body = json.loads((root / "datasets/demo.json").read_text())
    baseline = validate_publication(body, execute(body))
    baseline_recording = project_recording(
        baseline,
        body,
        recording_id="recorded-baseline",
        title="Extractive baseline · municipal RFP",
        recorded_at=datetime.now(UTC).isoformat(),
    )
    historical_report = json.loads((root / "reports/browser-model-validation.json").read_text())
    historical = historical_recording(
        (root / "var/browser-model/live-browser-01/result.json").read_bytes(),
        historical_report,
    )
    benchmark = json.loads((root / "reports/baseline.json").read_text())
    injection = json.loads((root / "reports/injection-pairs-baseline.json").read_text())
    inputs = [
        "datasets/demo.json",
        "reports/browser-model-validation.json",
        "reports/baseline.json",
        "reports/injection-pairs-baseline.json",
        "src/atlas/replay.py",
    ]
    return {
        "schema_version": 1,
        "scope": "Read-only recorded synthetic demo. No live inference, uploads, credentials or approvals.",
        "recordings": [baseline_recording, historical],
        "benchmarks": [
            {
                "name": "Baseline contract suite",
                "passed": sum(benchmark["case_outcomes"].values()),
                "total": benchmark["unique_cases"],
                "cases": benchmark["case_outcomes"],
                "scope": benchmark["scope"],
            },
            {
                "name": "Paired hostile-evidence baseline",
                "passed": injection["scenarios_passed"],
                "total": injection["evaluated_scenarios"],
                "cases": {r["id"]: r["passed"] for r in injection["results"]},
                "scope": "Authored synthetic paired diagnostics; not a live-model attack success rate.",
            },
        ],
        "model_evidence": {
            k: historical_report[k]
            for k in ("model_id", "region", "estimated_model_cost_usd", "scope", "artifact_sha256")
        },
        "input_sha256": {p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in inputs},
    }


if __name__ == "__main__":
    target = Path("apps/web/src/replay-data.json")
    target.write_text(json.dumps(prepare(), indent=2, ensure_ascii=False) + "\n")
