"""Export controls use SDK stubs and fictional text, never a real model."""

import copy
import importlib.util
from pathlib import Path

import pytest
from botocore.stub import Stubber
from test_contract_model import PROVENANCE, enqueue
from test_contractnli import fixture
from test_model_gateway import client as client
from test_model_gateway import config as config

from atlas.models.bedrock import BedrockGateway
from atlas.models.contract_evaluation import run_development

spec = importlib.util.spec_from_file_location(
    "contract_model_export",
    Path(__file__).resolve().parents[1] / "scripts/record_contract_model.py",
)
export = importlib.util.module_from_spec(spec)
spec.loader.exec_module(export)


def saved(tmp_path, monkeypatch, client, config):
    monkeypatch.chdir(tmp_path)
    with Stubber(client) as stub:
        enqueue(stub)
        run_development(fixture(), PROVENANCE, BedrockGateway(client, config), "var/run")
    run, fingerprint = export.private_run(Path("var/run/run.json"))
    return run, fingerprint


def test_export_refuses_a_controlled_run_labelled_as_offline(tmp_path, monkeypatch, client, config):
    run, fingerprint = saved(tmp_path, monkeypatch, client, config)
    with pytest.raises(ValueError, match="complete live run"):
        export.build_report(run, fingerprint, fixture(), PROVENANCE, "var/run/observations.jsonl")


@pytest.mark.parametrize(
    "mutation", ["missing_receipt", "unknown_cost", "wrong_model", "forged_total", "invalid_tokens"]
)
def test_usage_must_reconcile_before_public_export(tmp_path, monkeypatch, client, config, mutation):
    run, _ = saved(tmp_path, monkeypatch, client, config)
    usage = copy.deepcopy(run["usage"])
    if mutation == "missing_receipt":
        usage["receipts"] = []
    elif mutation == "unknown_cost":
        usage["receipts"][0]["status"] = "invocation_unknown"
    elif mutation == "wrong_model":
        usage["model_id"] = "another-model"
    elif mutation == "forged_total":
        usage["estimated_model_cost_usd"] = "0"
    else:
        usage["receipts"][0]["input_tokens"] = True
    with pytest.raises(ValueError):
        export.usage_summary(usage, 1)


@pytest.mark.parametrize("tamper", [False, True])
def test_export_rescores_raw_observations_and_refuses_different_aggregate_scores(
    tmp_path, monkeypatch, client, config, tamper
):
    run, fingerprint = saved(tmp_path, monkeypatch, client, config)
    # A local flag is not proof of live inference. This fictional control tests
    # replay admission, which the report explicitly does not call attestation.
    run["live_model"] = True
    if tamper:
        run["results"]["label_accuracy"] = 0
        with pytest.raises(ValueError, match="Replay differs"):
            export.build_report(
                run, fingerprint, fixture(), PROVENANCE, "var/run/observations.jsonl"
            )
    else:
        result = export.build_report(
            run, fingerprint, fixture(), PROVENANCE, "var/run/observations.jsonl"
        )
        assert result["replay_matches_recorded_results"] is True
        assert result["results"] == run["results"]
        assert result["usage"]["calls"] == 1
        assert "A fictional promise" not in str(result)
        assert result["constant_not_mentioned_reference"]["label_accuracy"] == 1 / 3
