"""Publish only independently rescored synthetic outcomes and allowlisted usage.

Raw source-bearing provider artifacts remain private. No account/profile identifiers,
provider error messages, credentials or model prose are copied into the report.
"""

import argparse
import json
import re
from collections import Counter
from hashlib import sha256
from pathlib import Path

from chaoslab.artifacts import publish_report
from chaoslab.reasoning import score_artifact


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", required=True)
    parser.add_argument("--dataset", default="datasets/reasoning.json")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    raw = Path(args.artifact).read_bytes()
    bundle = json.loads(raw)
    dataset_raw = Path(args.dataset).read_bytes()
    score = score_artifact(json.loads(dataset_raw), dataset_raw, bundle)
    versions = {
        r["output"]["pipeline_version"] for r in bundle["results"] if r["status"] == "succeeded"
    }
    if bundle.get("live_model") is not True or len(versions) != 1:
        raise ValueError("Expected live artifact with one observed successful pipeline version")
    source = bundle.get("source_manifest")
    source_hash = None
    if source is not None:
        source_hash = source.get("source_sha256")
        if (
            not isinstance(source_hash, str)
            or re.fullmatch(r"[a-f0-9]{64}", source_hash) is None
            or bundle.get("source_unchanged_at_completion") is not True
        ):
            raise ValueError("Source identity is invalid, incomplete or changed during execution")
    usage = bundle["usage"]
    receipts = usage["receipts"]
    score["scope"] = json.loads(dataset_raw)["scope"]
    score["live_execution"] = {
        "pipeline_version": versions.pop(),
        "execution_source_sha256": source_hash,
        "provider": usage["provider"],
        "model_id": usage["model_id"],
        "region": usage["region"],
        "input_artifact_sha256": sha256(raw).hexdigest(),
        "successful_case_outputs": sum(r["status"] == "succeeded" for r in bundle["results"]),
        "call_status_counts": dict(Counter(r["status"] for r in receipts)),
        "invocation_failure_counts": dict(
            Counter(
                r.get("invocation_failure_kind")
                if r.get("invocation_failure_kind")
                in {
                    "service_error",
                    "read_timeout",
                    "connect_timeout",
                    "connection_closed",
                    "tls_error",
                    "endpoint_connection",
                    "unclassified",
                }
                else "unclassified"
                for r in receipts
                if r["status"] == "invocation_unknown"
            )
        ),
        "validation_failure_counts": dict(
            Counter(
                r.get("validation_error_code") or "unspecified"
                for r in receipts
                if r["status"] == "invalid_schema"
            )
        ),
        "estimated_model_cost_usd": usage["estimated_model_cost_usd"],
        "cost_is_invoice": False,
        "continue_invalid_output": bundle.get("continue_invalid_output", False),
        "limitations": [
            "Failed bundles are errors in end-to-end denominators; extraction_coverage reflects independently verifiable completed bundles, not raw extraction-call success.",
            "Same authored cases were used during development; later prompt revisions are evaluated on a seen diagnostic set.",
            "Artifact hashes bind local data, not signed provider attestations. On-disk source identity does not prove loaded code or installed dependencies; older runs have no source manifest.",
            "No general reliability, latency, AWS deployment or billing reconciliation claim follows from these results.",
        ],
    }
    publish_report(Path(args.output), score)
    print(
        json.dumps(
            {
                "cases": score["summary"]["cases"],
                "passed": score["summary"]["cases_passed"],
                "output": args.output,
            }
        )
    )


if __name__ == "__main__":
    main()
