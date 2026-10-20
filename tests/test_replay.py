"""Publication projection preserves provenance while excluding private workspace metadata."""

import copy
import hashlib
import json
from pathlib import Path

import pytest

from atlas.execution import execute
from atlas.replay import historical_recording, project_recording


def fixture():
    body = json.loads(Path("datasets/demo.json").read_text())
    return body, execute(body)


def project(body, payload):
    return project_recording(
        payload, body, recording_id="synthetic", title="Synthetic", recorded_at="2026-10-18"
    )


def test_projection_excludes_private_metadata_and_arbitrary_traces():
    body, payload = fixture()
    payload.update(actor="secret-actor", token="secret-token", trace=[{"prompt": "secret-prompt"}])
    for a in payload["assessments"]:
        a["review_note"] = "secret-note"
    result = project(body, payload)
    assert "secret-" not in json.dumps(result)
    assert len(result["assessments"]) == 8
    assert set(result) == {
        "id",
        "title",
        "recorded_at",
        "provider",
        "pipeline_version",
        "documents",
        "assessments",
    }


@pytest.mark.parametrize("mutation", ["quote", "digest", "approved", "version", "draft", "source"])
def test_replay_cannot_weaken_worker_provenance_or_review_gate(mutation):
    body, payload = fixture()
    a = payload["assessments"][0]
    if mutation == "quote":
        a["evidence"][0]["quote"] += " invented"
    elif mutation == "digest":
        a["requirement"]["source"]["digest"] = "0" * 64
    elif mutation == "approved":
        a["review_state"] = "approved"
    elif mutation == "version":
        a["version"] = 2
    elif mutation == "draft":
        a["draft"] = "Guaranteed compliant"
    else:
        payload["documents"][0]["text"] += " changed"
    with pytest.raises(ValueError):
        project(body, payload)


def test_historical_recording_requires_exact_executed_artifact():
    report = {"artifact_sha256": "0" * 64, "passed": True}
    with pytest.raises(ValueError, match="executed validation"):
        historical_recording(b"{}", report)


def historical_fixture():
    body = {
        "rfp": {
            "id": "r",
            "title": "Synthetic",
            "kind": "rfp",
            "text": "Customer data must remain in Canada.",
        },
        "knowledge": [
            {
                "id": "k",
                "title": "Synthetic",
                "kind": "knowledge",
                "text": "Customer data remains in Canada.",
            }
        ],
    }
    payload = execute(body)
    payload.update(
        provider="bedrock",
        pipeline_version="source-selection-v4",
        model_config_sha256="a" * 64,
        created="2026-10-16T00:00:00Z",
    )
    saved = {"submitted_input": body, "result": payload, "job": {"token": "private"}}
    report = {
        "passed": True,
        **{k: payload[k] for k in ("provider", "pipeline_version", "model_config_sha256")},
    }
    return saved, report


def test_historical_projection_does_not_export_job_or_storage_identity():
    saved, report = historical_fixture()
    raw = json.dumps(saved).encode()
    report["artifact_sha256"] = hashlib.sha256(raw).hexdigest()
    assert "private" not in json.dumps(historical_recording(raw, report))
    assert historical_recording(raw, report)["id"] == "recorded-residency"


def test_historical_fixture_allowlist_and_identity_are_enforced():
    saved, report = historical_fixture()
    changed = copy.deepcopy(saved)
    changed["submitted_input"]["rfp"]["text"] = "Private contract"
    raw = json.dumps(changed).encode()
    report["artifact_sha256"] = hashlib.sha256(raw).hexdigest()
    with pytest.raises(ValueError, match="allowlisted"):
        historical_recording(raw, report)
    raw = json.dumps(saved).encode()
    report["artifact_sha256"] = hashlib.sha256(raw).hexdigest()
    report["pipeline_version"] = "foreign"
    with pytest.raises(ValueError, match="identity"):
        historical_recording(raw, report)
