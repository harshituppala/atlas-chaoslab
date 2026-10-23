"""Fictional stopped SDK runs; checkpoint audit never performs inference."""

import copy
import json
from decimal import Decimal
from pathlib import Path

import pytest
from botocore.stub import ANY, Stubber
from test_contract_model import PROVENANCE, enqueue
from test_contractnli import fixture, oracle
from test_model_gateway import client as client
from test_model_gateway import config as config

from atlas.models import contract_checkpoint as checkpoint
from atlas.models.bedrock import BedrockGateway
from atlas.models.contract_evaluation import run_development
from atlas.models.session_budget import initialize, reserve_configured_run


@pytest.fixture
def stopped(tmp_path, monkeypatch, client, config):
    monkeypatch.chdir(tmp_path)
    data = fixture()
    second = copy.deepcopy(data["documents"][0])
    second["id"] = 2
    data["documents"].append(second)
    directory, budget = Path("var/run"), Path("var/campaign.json")
    initialize(budget, authorized_usd=Decimal("1"))
    reserve_configured_run(budget, config, directory / "run.json")
    with Stubber(client) as stub:
        enqueue(stub)
        stub.add_client_error(
            "count_tokens",
            service_error_code="ThrottlingException",
            expected_params={"modelId": "synthetic-model", "input": ANY},
        )
        # The live flag is a local field, not attestation. This remains a stubbed run.
        run_development(data, PROVENANCE, BedrockGateway(client, config, live=True), directory)
    return data, directory, budget


def audit(stopped):
    data, directory, budget = stopped
    return checkpoint.audit_checkpoint(data, PROVENANCE, directory, budget)


def rewrite(path, value):
    path.write_text(json.dumps(value) + "\n")
    path.chmod(0o600)


def mutate_usage(directory, change):
    run = json.loads((directory / "run.json").read_text())
    change(run["usage"])
    rewrite(directory / "usage.json", run["usage"])
    rewrite(directory / "run.json", run)


def test_prefix_admission_is_read_only_and_never_opens_credentials(stopped, monkeypatch):
    import boto3

    monkeypatch.setattr(boto3, "Session", lambda **_: pytest.fail("No credentials permitted"))
    _, directory, budget = stopped
    paths = list(directory.iterdir()) + [budget]
    before = {p: p.read_bytes() for p in paths}
    report = audit(stopped)
    assert report["records_admitted"] == report["remaining_documents"] == 1
    assert report["automatic_resume_allowed"] is False
    assert report["provider_calls"] == 0 and report["accuracy_scores"] is None
    assert report["original_run_reservation_retained_usd"] == "0.0036"
    assert "A fictional promise" not in json.dumps(report)
    assert before == {p: p.read_bytes() for p in paths}


@pytest.mark.parametrize(
    "mutation",
    ["truncated", "duplicate", "footer", "wrong_input", "boolean_id", "failed", "invalid_output"],
)
def test_partial_journal_ambiguity_cannot_become_a_checkpoint(stopped, mutation):
    _, directory, _ = stopped
    path = directory / "observations.partial.jsonl"
    lines = path.read_bytes().splitlines(keepends=True)
    record = json.loads(lines[1])
    if mutation == "truncated":
        path.write_bytes(b"".join(lines)[:-2])
        with pytest.raises(ValueError):
            audit(stopped)
        return
    if mutation == "duplicate":
        lines.append(lines[1])
    elif mutation == "footer":
        lines.append(b'{"kind":"complete"}\n')
    else:
        if mutation == "wrong_input":
            record["input_sha256"] = "0" * 64
        elif mutation == "boolean_id":
            record["document_id"] = True
        elif mutation == "failed":
            record.update(status="failed", output=None)
        else:
            record["output"] = {
                "predictions": [{"id": "invented", "choice": "Entailment", "spans": []}]
            }
        lines[1] = (json.dumps(record) + "\n").encode()
    path.write_bytes(b"".join(lines))
    with pytest.raises(ValueError):
        audit(stopped)


@pytest.mark.parametrize(
    "mutation", ["count", "unknown_usage", "prompt", "schema", "tokens", "cost", "model", "caps"]
)
def test_receipt_inconsistency_or_unknown_usage_is_rejected(stopped, mutation):
    _, directory, _ = stopped

    def change(usage):
        receipt = usage["receipts"][0]
        if mutation == "count":
            usage["receipts"].append(copy.deepcopy(receipt))
        elif mutation == "unknown_usage":
            receipt["status"] = "invocation_unknown"
        elif mutation == "prompt":
            receipt["prompt_sha256"] = "0" * 64
        elif mutation == "schema":
            receipt["schema_sha256"] = "0" * 64
        elif mutation == "tokens":
            receipt["input_tokens"] = True
        elif mutation == "cost":
            receipt["estimated_cost_usd"] = "999"
        elif mutation == "model":
            usage["model_id"] = "another-model"
        else:
            receipt["input_tokens"] = receipt["reserved_input_tokens"] + 1

    mutate_usage(directory, change)
    with pytest.raises(ValueError):
        audit(stopped)


@pytest.mark.parametrize(
    "mutation", ["missing", "duplicate", "over_authorization", "under_reserved"]
)
def test_campaign_must_still_retain_one_full_run_reservation(stopped, mutation):
    _, _, budget_path = stopped
    budget = json.loads(budget_path.read_text())
    if mutation == "missing":
        budget["reservations"] = []
    elif mutation == "duplicate":
        budget["reservations"].append(copy.deepcopy(budget["reservations"][0]))
    elif mutation == "over_authorization":
        budget["authorized_usd"] = "0.0001"
    else:
        budget["reservations"][0]["reserved_usd"] = "0.0001"
    rewrite(budget_path, budget)
    with pytest.raises(ValueError):
        audit(stopped)


def test_new_prompt_contract_refuses_the_old_receipt(stopped, monkeypatch):
    monkeypatch.setattr(checkpoint, "SYSTEM", "A changed task instruction")
    with pytest.raises(ValueError, match="receipt"):
        audit(stopped)


def test_valid_but_wrong_answers_are_not_filtered_by_gold_labels(stopped):
    _, directory, _ = stopped
    path = directory / "observations.partial.jsonl"
    lines = path.read_bytes().splitlines(keepends=True)
    record = json.loads(lines[1])
    wrong = oracle()
    wrong["predictions"][0]["choice"] = "Contradiction"
    record["output"] = wrong
    lines[1] = (json.dumps(record) + "\n").encode()
    path.write_bytes(b"".join(lines))
    assert audit(stopped)["records_admitted"] == 1


@pytest.mark.parametrize("mutation", ["permissions", "symlink", "usage_mismatch", "complete_run"])
def test_private_and_stopped_evidence_is_required(stopped, mutation):
    _, directory, _ = stopped
    path = directory / "usage.json"
    if mutation == "permissions":
        path.chmod(0o644)
    elif mutation == "symlink":
        target = directory / "usage-copy.json"
        path.rename(target)
        path.symlink_to(target.name)
    elif mutation == "complete_run":
        (directory / "observations.jsonl").write_text("not a complete run")
    else:
        value = json.loads(path.read_text())
        value["estimated_model_cost_usd"] = "999"
        rewrite(path, value)
    with pytest.raises((OSError, ValueError)):
        audit(stopped)


@pytest.mark.parametrize(
    "field,value",
    [("live_model", False), ("status", "complete"), ("scorer_sha256", "private-upstream-text")],
)
def test_run_provenance_must_be_a_stopped_live_contract_record(stopped, field, value):
    _, directory, _ = stopped
    path = directory / "run.json"
    run = json.loads(path.read_text())
    run[field] = value
    rewrite(path, run)
    with pytest.raises(ValueError):
        audit(stopped)


def test_existing_cli_report_is_preserved_before_any_archive_read(stopped, monkeypatch):
    import sys

    data, directory, _ = stopped
    path = Path("var/previous.json")
    path.write_text("preserved")
    monkeypatch.setattr(checkpoint, "load_development", lambda _: pytest.fail("No input read"))
    monkeypatch.setattr(
        sys,
        "argv",
        ["audit", "--archive", "unused", "--run-dir", str(directory), "--output", str(path)],
    )
    with pytest.raises(SystemExit, match="source evidence preserved"):
        checkpoint.main()
    assert path.read_text() == "preserved"


def test_evidence_change_during_read_refuses_the_snapshot(stopped, monkeypatch):
    original = checkpoint.private_bytes
    reads = {}

    def unstable(path, limit):
        reads[path] = reads.get(path, 0) + 1
        result = original(path, limit)
        return result if reads[path] == 1 else result + b" "

    monkeypatch.setattr(checkpoint, "private_bytes", unstable)
    with pytest.raises(ValueError, match="changed"):
        audit(stopped)
