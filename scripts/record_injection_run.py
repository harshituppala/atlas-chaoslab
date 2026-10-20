"""Project independently scored paired diagnostics and bounded provider metadata."""

import argparse
import json
from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
from pathlib import Path

from atlas.models.provenance import source_manifest
from chaoslab.artifacts import publish_report
from chaoslab.injection import evaluate

STATUSES = {
    "reserved",
    "usage_unknown",
    "usage_overrun",
    "received",
    "invocation_unknown",
    "incomplete_output",
    "invalid_schema",
    "validated",
}


def prepare_report(raw, data_raw, *, expected_source):
    bundle = json.loads(raw)
    if (
        bundle.get("live_model") is not True
        or bundle.get("source_unchanged_at_completion") is not True
    ):
        raise ValueError("Expected completed live artifact without detected source drift")
    if bundle["source_manifest"]["source_sha256"] != expected_source:
        raise ValueError("Original execution source differs from recorder's current source")
    usage = bundle["usage"]
    if (
        usage["provider"] != "bedrock"
        or usage["region"] != "us-east-1"
        or usage["model_id"] != "us.anthropic.claude-haiku-4-5-20251001-v1:0"
    ):
        raise ValueError("Unexpected reviewed provider/model/region")
    statuses = [row["status"] for row in usage["receipts"]]
    if any(status not in STATUSES for status in statuses):
        raise ValueError("Unknown receipt status")
    cost = usage["estimated_model_cost_usd"]
    if cost is not None:
        cost = Decimal(cost)
        if not cost.is_finite() or not 0 <= cost <= 10:
            raise ValueError("Invalid model cost estimate")
        cost = str(cost)
    versions = {
        row["output"]["pipeline_version"]
        for row in bundle["results"]
        if row["status"] == "succeeded"
    }
    if versions and versions != {"source-selection-v4"}:
        raise ValueError("Unexpected pipeline identity")
    report = evaluate(json.loads(data_raw), data_raw, bundle)
    report["execution"] = {
        "provider": "bedrock",
        "model_id": usage["model_id"],
        "region": "us-east-1",
        "pipeline_version": next(iter(versions), None),
        "source_sha256": expected_source,
        "input_artifact_sha256": sha256(raw).hexdigest(),
        "call_status_counts": dict(Counter(statuses)),
        "estimated_model_cost_usd": cost,
        "cost_is_invoice": False,
        "limitations": "One execution per authored synthetic clean/hostile case. Artifact/host source identity is not signed provider or loaded-code attestation. No real tools, credentials, exfiltration channel, production prevalence or general injection-resistance claim. Strict errors include extraction, relation and evidence selection.",
    }
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    artifact, dataset = Path(args.artifact), Path("datasets/injection-pairs.json")
    if Path(args.output).resolve() in {artifact.resolve(), dataset.resolve()}:
        parser.error("Output must not overwrite inputs")
    raw, data_raw = artifact.read_bytes(), dataset.read_bytes()
    frozen = source_manifest()["source_sha256"]
    scorer_raw = Path("src/chaoslab/injection.py").read_bytes()
    recorder_raw = Path(__file__).read_bytes()
    report = prepare_report(raw, data_raw, expected_source=frozen)
    if (
        source_manifest()["source_sha256"] != frozen
        or artifact.read_bytes() != raw
        or dataset.read_bytes() != data_raw
        or Path(__file__).read_bytes() != recorder_raw
    ):
        raise ValueError("Source or artifact changed during scoring")
    report.update(
        {
            "recorded_at": datetime.now(UTC).isoformat(),
            "scoring_module_sha256": sha256(scorer_raw).hexdigest(),
            "recorder_sha256": sha256(recorder_raw).hexdigest(),
        }
    )
    publish_report(Path(args.output), report)
    print(
        json.dumps(
            {
                "strict_passed": report["requirements_passed"],
                "evaluated": report["requirements_evaluated"],
                "forbidden_source_cases": report["paired"][
                    "attack_cases_with_forbidden_source_citation"
                ],
            }
        )
    )


if __name__ == "__main__":
    main()
