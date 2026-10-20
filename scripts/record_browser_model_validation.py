"""Recheck a completed synthetic live-browser review and publish bounded metadata."""

import argparse
import json
import sqlite3
from collections import Counter
from copy import deepcopy
from hashlib import sha256
from pathlib import Path

from atlas.execution import fingerprint, validate_model_snapshot
from atlas.models.job_spec import ModelJobSpec
from atlas.models.provenance import source_manifest
from chaoslab.artifacts import publish_report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True)
    args = parser.parse_args()
    if (
        not args.name
        or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789-" for c in args.name)
        or len(args.name) > 64
    ):
        parser.error("Expected a bounded validation name")
    private = Path("var/browser-model") / args.name
    raw = (private / "result.json").read_bytes()
    artifact = json.loads(raw)
    snapshot = json.loads(
        (Path("var/browser-services") / f"{args.name}-manifest.json").read_bytes()
    )
    assert source_manifest()["source_sha256"] == snapshot["source_sha256"]
    assert (
        sha256(Path("apps/web/live-validation/model-review.spec.ts").read_bytes()).hexdigest()
        == snapshot["browser_test_sha256"]
    )
    dataset_raw = Path("datasets/reasoning.json").read_bytes()
    assert sha256(dataset_raw).hexdigest() == snapshot["dataset_sha256"]
    case = json.loads(dataset_raw)["cases"][0]
    assert artifact["case_id"] == case["id"]
    with sqlite3.connect(Path("var/browser-services") / f"{args.name}.db") as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT tenant, status, attempts, input, result_id FROM jobs WHERE id=?",
            (artifact["job"]["id"],),
        ).fetchone()
    assert row["status"] == "succeeded" and row["attempts"] == 1
    assert row["result_id"] == artifact["result"]["id"]
    body = json.loads(row["input"])
    assert body["rfp"]["text"] == case["requirement"]
    assert len(body["knowledge"]) == 1 and body["knowledge"][0]["text"] == case["evidence"]
    assert artifact["submitted_input"]["execution_mode"] == "bedrock"
    expected_hash = ModelJobSpec.model_validate(body["_model_spec"]).digest()
    assert artifact["submitted_input"]["expected_model_config_sha256"] == expected_hash
    payload = deepcopy(artifact["result"])
    payload.pop("id")
    payload.pop("created")
    for item in payload["assessments"]:
        assert item.pop("review_note", "") == ""
    checked = validate_model_snapshot(body, payload)
    assert len(checked["assessments"]) == 1
    item = checked["assessments"][0]
    assert item["requirement"]["text"] == case["requirement"]
    assert item["status"] == "evidence_found" and case["relation"] == "supported"
    assert any(c["quote"] == case["evidence"] for c in item["evidence"])
    key = fingerprint({"tenant": row["tenant"], "job": artifact["job"]["id"]})
    ledger = json.loads((Path("var/model-jobs") / f"{key}.ledger.json").read_bytes())
    assert ledger["estimated_model_cost_usd"] is not None
    report = {
        "schema_version": 1,
        "scope": "One synthetic real browser→FastAPI→isolated Bedrock worker→SQLite→authenticated browser readback. No request mocks or provider stubs. Not production accuracy, PostgreSQL/live-model integration, cloud deployment or load validation.",
        "case_id": case["id"],
        "passed": True,
        "attempts": row["attempts"],
        "provider": checked["provider"],
        "model_id": ledger["model_id"],
        "region": ledger["region"],
        "pipeline_version": checked["pipeline_version"],
        "model_config_sha256": expected_hash,
        "estimated_model_cost_usd": ledger["estimated_model_cost_usd"],
        "cost_is_invoice": False,
        "call_status_counts": dict(Counter(r["status"] for r in ledger["receipts"])),
        "artifact_sha256": sha256(raw).hexdigest(),
        "source_sha256": snapshot["source_sha256"],
        "dataset_sha256": snapshot["dataset_sha256"],
        "browser_test_sha256": snapshot["browser_test_sha256"],
        "checks": [
            "explicit_mode",
            "displayed_config_binding",
            "single_attempt",
            "authenticated_readback",
            "source_snapshot",
            "exact_citations",
            "expected_support_label",
            "pending_review",
            "extractive_draft",
            "source_highlight_in_browser",
        ],
        "limitations": "Hashes identify selected on-disk Python source, test and dataset, not loaded code or a signed provider attestation. Frontend build identity was not separately captured. Browser screenshot/highlight checks come from the completed test; this recorder independently rechecks its saved payload and database state.",
    }
    publish_report(Path("reports/browser-model-validation.json"), report)
    print(
        json.dumps(
            {
                "passed": True,
                "estimated_model_cost_usd": report["estimated_model_cost_usd"],
                "call_status_counts": report["call_status_counts"],
            }
        )
    )


if __name__ == "__main__":
    main()
