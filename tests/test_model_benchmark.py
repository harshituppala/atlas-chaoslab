"""Offline real SDK protocol stubs verify batch billing and independent artifact scoring."""

import copy
import json
from pathlib import Path

import pytest
from botocore.stub import ANY, Stubber
from test_model_gateway import client as client
from test_model_gateway import config as config
from test_model_gateway import response

from atlas.artifacts import reserve_invocation_artifacts
from atlas.domain import Document
from atlas.models.bedrock import BedrockGateway
from atlas.models.benchmark import reservation_plan, run_batch, validate_manifest
from atlas.models.intelligence import source_chunks
from chaoslab.reasoning import export_manifest, score_artifact


@pytest.fixture
def manifest():
    raw = Path("datasets/reasoning.json").read_bytes()
    return json.loads(raw), raw, export_manifest(json.loads(raw), raw)


def enqueue(stub, config, value):
    stub.add_response(
        "count_tokens", {"inputTokens": 50}, {"modelId": config.model_id, "input": ANY}
    )
    stub.add_response("converse", response(value))


def extraction(row):
    document = Document.model_validate(row["input"]["rfp"])
    chunk = source_chunks(document)[0]
    return {
        "requirements": [{"chunk_id": chunk.id, "quote": document.text, "category": "security"}]
    }


def test_manifest_hides_labels_and_descriptive_case_names(manifest):
    dataset, _, exported = manifest
    assert validate_manifest(exported)
    for case, row in zip(dataset["cases"], exported["cases"], strict=True):
        assert case["id"] not in row["id"]
        assert set(row) == {"id", "input", "input_sha256"}
        assert set(row["input"]) == {"rfp", "knowledge"}
    tampered = copy.deepcopy(exported)
    tampered["cases"][0]["input"]["rfp"]["text"] += " changed"
    with pytest.raises(ValueError, match="identity"):
        validate_manifest(tampered)


def test_shared_gateway_produces_bound_private_scoreable_artifact(
    manifest, config, client, tmp_path
):
    dataset, raw, exported = manifest
    output = tmp_path / "batch.json"
    journal = reserve_invocation_artifacts(output)
    with Stubber(client) as stub:
        enqueue(stub, config, extraction(exported["cases"][0]))
        enqueue(stub, config, {"choice": "supported:e1"})
        gateway = BedrockGateway(client, config, live=False)
        result = run_batch(exported, gateway, output, journal, max_cases=1)
        stub.assert_no_pending_responses()
    scored = score_artifact(dataset, raw, result)
    assert scored["evaluated_cases"] == 1 and scored["not_run_cases"] == 17
    assert scored["summary"]["cases_passed"] == 1
    assert result["source_unchanged_at_completion"] is True
    assert "src/atlas/models/intelligence.py" in result["source_manifest"]["files"]
    assert result["live_model"] is False
    assert len(json.loads(journal.read_text())["receipts"]) == 2
    assert output.stat().st_mode & 0o777 == 0o600
    forged = copy.deepcopy(result)
    forged["results"][0]["output"]["documents"][0]["text"] += " changed"
    with pytest.raises(ValueError, match="snapshot"):
        score_artifact(dataset, raw, forged)


def test_unknown_charge_stops_batch_and_preserves_reservation(manifest, config, client, tmp_path):
    _, _, exported = manifest
    output = tmp_path / "uncertain.json"
    journal = reserve_invocation_artifacts(output)
    with Stubber(client) as stub:
        stub.add_response("count_tokens", {"inputTokens": 50})
        stub.add_client_error("converse", service_error_code="ModelTimeoutException")
        result = run_batch(exported, BedrockGateway(client, config), output, journal, max_cases=2)
        stub.assert_no_pending_responses()
    assert len(result["results"]) == 1 and result["results"][0]["status"] == "failed"
    assert result["usage"]["estimated_model_cost_usd"] is None
    assert json.loads(journal.read_text())["receipts"][0]["status"] == "invocation_unknown"
    with pytest.raises(FileExistsError):
        reserve_invocation_artifacts(output)


def test_dry_plan_never_opens_provider(config, manifest, tmp_path, monkeypatch, capsys):
    from atlas.models import benchmark

    _, _, exported = manifest
    manifest_path = tmp_path / "input.json"
    config_path = tmp_path / "config.json"
    manifest_path.write_text(json.dumps(exported))
    config_path.write_text(config.model_dump_json())
    monkeypatch.setattr(
        "sys.argv", ["benchmark", "--input", str(manifest_path), "--config", str(config_path)]
    )

    def forbid(*args, **kwargs):
        pytest.fail("Dry planning must not initialize provider credentials")

    monkeypatch.setattr(BedrockGateway, "open", forbid)
    benchmark.main()
    assert json.loads(capsys.readouterr().out)["network_used"] is False
    plan = reservation_plan(config, 1)
    assert plan["call_cap"] == 3


@pytest.mark.parametrize("mutation", ["dataset", "input", "duplicate", "unknown"])
def test_artifact_binding_refuses_mismatches(manifest, mutation):
    dataset, raw, exported = manifest
    row = exported["cases"][0]
    bundle = {
        "dataset_sha256": exported["dataset_sha256"],
        "results": [{"id": row["id"], "input_sha256": row["input_sha256"], "status": "failed"}],
    }
    if mutation == "dataset":
        bundle["dataset_sha256"] = "0" * 64
    elif mutation == "input":
        bundle["results"][0]["input_sha256"] = "0" * 64
    elif mutation == "duplicate":
        bundle["results"].append(copy.deepcopy(bundle["results"][0]))
    else:
        bundle["results"][0]["id"] = "unknown"
    with pytest.raises(ValueError):
        score_artifact(dataset, raw, bundle)


def test_synthetic_prices_cannot_open_live_provider(config, monkeypatch):
    import boto3

    monkeypatch.setattr(
        boto3,
        "Session",
        lambda **kwargs: pytest.fail("Invalid price card must fail before credentials"),
    )
    with pytest.raises(ValueError, match="official Bedrock price"):
        BedrockGateway.open(config, allow_paid=True)


def test_live_price_card_expiry_and_source_are_checked(config):
    from datetime import UTC, datetime, timedelta

    from atlas.models.contracts import BedrockConfig

    raw = config.model_dump(mode="json")
    raw["price_card"].update(
        source="https://aws.amazon.com/bedrock/pricing/",
        verified_on=datetime.now(UTC).date().isoformat(),
    )
    BedrockConfig.model_validate(raw).validate_live_price()
    raw["price_card"]["verified_on"] = (datetime.now(UTC).date() - timedelta(days=8)).isoformat()
    with pytest.raises(ValueError):
        BedrockConfig.model_validate(raw).validate_live_price()


@pytest.mark.parametrize(
    "error,continue_invalid,expected",
    [
        ("invalid", True, 2),
        ("invalid", False, 1),
        ("provider", True, 1),
    ],
)
def test_diagnostic_continuation_only_allows_invalid_output(
    manifest, client, config, tmp_path, monkeypatch, error, continue_invalid, expected
):
    from atlas.models import benchmark
    from atlas.models.bedrock import InvalidModelOutput, ProviderFailure

    calls = []

    def analyze(*args):
        calls.append(1)
        if len(calls) == 1:
            raise (InvalidModelOutput if error == "invalid" else ProviderFailure)(
                "synthetic failure"
            )
        return {"synthetic": "completed"}

    monkeypatch.setattr(benchmark, "analyze_model", analyze)
    result = run_batch(
        manifest[2],
        BedrockGateway(client, config),
        tmp_path / "out.json",
        tmp_path / "journal.json",
        max_cases=2,
        continue_invalid=continue_invalid,
    )
    assert len(result["results"]) == expected
    assert result["results"][0]["status"] == "failed"
    assert result["continue_invalid_output"] is continue_invalid


def test_invalid_output_never_continues_with_uncertain_receipt(
    manifest, client, config, tmp_path, monkeypatch
):
    from atlas.models import benchmark
    from atlas.models.bedrock import InvalidModelOutput

    gateway = BedrockGateway(client, config)

    def analyze(*args):
        receipt = gateway.ledger.reserve("synthetic", "prompt-hash", "schema-hash", 20)
        receipt.status = "invocation_unknown"
        raise InvalidModelOutput("synthetic invalid response with uncertain usage")

    monkeypatch.setattr(benchmark, "analyze_model", analyze)
    result = run_batch(
        manifest[2],
        gateway,
        tmp_path / "out.json",
        tmp_path / "journal.json",
        max_cases=2,
        continue_invalid=True,
    )
    assert len(result["results"]) == 1
    assert result["usage"]["estimated_model_cost_usd"] is None


def test_batch_records_source_drift_without_hiding_results(
    manifest, config, client, tmp_path, monkeypatch
):
    import atlas.models.benchmark as benchmark

    snapshots = iter([{"source_sha256": "a" * 64}, {"source_sha256": "b" * 64}])
    monkeypatch.setattr(benchmark, "source_manifest", lambda: next(snapshots))
    monkeypatch.setattr(benchmark, "analyze_model", lambda *args: {"controlled": True})
    output = tmp_path / "drift.json"
    result = run_batch(
        manifest[2], BedrockGateway(client, config), output, tmp_path / "journal.json", max_cases=1
    )
    assert result["results"][0]["status"] == "succeeded"
    assert result["source_unchanged_at_completion"] is False
    assert json.loads(output.read_text())["source_unchanged_at_completion"] is False
