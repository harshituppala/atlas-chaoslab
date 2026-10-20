"""Public projection tests use controlled bundles, never paid provider calls."""

import json
from copy import deepcopy
from pathlib import Path

import pytest
from test_scenarios import perfect

from chaoslab.scenarios import export_inputs
from scripts.record_injection_run import prepare_report


def fixture():
    raw = Path("datasets/injection-pairs.json").read_bytes()
    data = json.loads(raw)
    manifest = export_inputs(data, raw)
    rows = []
    for case, row in zip(data["cases"], manifest["cases"], strict=True):
        result = perfect(case)
        result.update(pipeline_version="source-selection-v4", private_prompt="PRIVATE-CANARY")
        rows.append({**row, "status": "succeeded", "output": result})
    bundle = {
        "dataset_sha256": manifest["dataset_sha256"],
        "results": rows,
        "live_model": True,
        "source_unchanged_at_completion": True,
        "source_manifest": {"source_sha256": "a" * 64},
        "profile": "PRIVATE-CANARY",
        "usage": {
            "provider": "bedrock",
            "region": "us-east-1",
            "model_id": "us.anthropic.claude-haiku-4-5-20251001-v1:0",
            "estimated_model_cost_usd": "0.01",
            "receipts": [{"status": "validated", "prompt": "PRIVATE-CANARY"}],
        },
    }
    return raw, bundle


def test_public_recorder_preserves_scoring_without_private_payloads():
    data_raw, bundle = fixture()
    report = prepare_report(json.dumps(bundle).encode(), data_raw, expected_source="a" * 64)
    assert "PRIVATE-CANARY" not in json.dumps(report)
    assert report["requirements_passed"] == 12
    assert report["execution"]["call_status_counts"] == {"validated": 1}
    assert report["execution"]["cost_is_invoice"] is False


@pytest.mark.parametrize(
    "mutation", ["source", "drift", "not_live", "provider", "pipeline", "receipt", "cost"]
)
def test_incompatible_metadata_cannot_be_published(mutation):
    data_raw, original = fixture()
    bundle = deepcopy(original)
    if mutation == "source":
        bundle["source_manifest"]["source_sha256"] = "b" * 64
    elif mutation == "drift":
        bundle["source_unchanged_at_completion"] = False
    elif mutation == "not_live":
        bundle["live_model"] = False
    elif mutation == "provider":
        bundle["usage"]["region"] = "foreign"
    elif mutation == "pipeline":
        bundle["results"][0]["output"]["pipeline_version"] = "foreign"
    elif mutation == "receipt":
        bundle["usage"]["receipts"][0]["status"] = "PRIVATE-CANARY"
    else:
        bundle["usage"]["estimated_model_cost_usd"] = "NaN"
    with pytest.raises(ValueError):
        prepare_report(json.dumps(bundle).encode(), data_raw, expected_source="a" * 64)


def test_unknown_cost_remains_unknown_instead_of_zero():
    data_raw, bundle = fixture()
    bundle["usage"]["estimated_model_cost_usd"] = None
    report = prepare_report(json.dumps(bundle).encode(), data_raw, expected_source="a" * 64)
    assert report["execution"]["estimated_model_cost_usd"] is None
