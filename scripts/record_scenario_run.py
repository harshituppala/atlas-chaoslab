"""Publish independently scored scenario outcomes plus bounded provider metadata."""

import argparse
import json
from collections import Counter
from hashlib import sha256
from pathlib import Path

from chaoslab.artifacts import publish_report
from chaoslab.scenarios import score_bundle


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    raw = Path(args.artifact).read_bytes()
    bundle = json.loads(raw)
    if (
        bundle.get("live_model") is not True
        or bundle.get("source_unchanged_at_completion") is not True
    ):
        raise ValueError("Expected completed live execution without detected source drift")
    data_raw = Path("datasets/scenarios.json").read_bytes()
    report = score_bundle(json.loads(data_raw), data_raw, bundle)
    report["scoring_module_sha256"] = sha256(
        Path("src/chaoslab/scenarios.py").read_bytes()
    ).hexdigest()
    usage = bundle["usage"]
    versions = {
        row["output"]["pipeline_version"]
        for row in bundle["results"]
        if row["status"] == "succeeded"
    }
    if len(versions) > 1:
        raise ValueError("Mixed pipeline versions")
    report["execution"] = {
        "provider": usage["provider"],
        "model_id": usage["model_id"],
        "region": usage["region"],
        "pipeline_version": next(iter(versions), None),
        "source_sha256": bundle["source_manifest"]["source_sha256"],
        "input_artifact_sha256": sha256(raw).hexdigest(),
        "call_status_counts": dict(Counter(r["status"] for r in usage["receipts"])),
        "estimated_model_cost_usd": usage["estimated_model_cost_usd"],
        "cost_is_invoice": False,
        "limitations": "Same-author synthetic diagnostics, not a blinded holdout. Exact full-record evidence and extraction gates are conservative. No loaded-code/provider attestation, production accuracy, deployment or billing reconciliation claim.",
    }
    publish_report(Path(args.output), report)
    print(
        json.dumps(
            {
                k: report[k]
                for k in (
                    "scenarios_passed",
                    "evaluated_scenarios",
                    "requirements_passed",
                    "requirements_evaluated",
                )
            }
        )
    )


if __name__ == "__main__":
    main()
