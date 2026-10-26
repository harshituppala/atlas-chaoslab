"""Aggregate admission uses fictional complete test observations, not external contracts."""

import copy
from pathlib import Path

import pytest
from test_contractnli import fixture, oracle

from atlas.models.contract_evaluation import ADAPTER
from atlas.models.provenance import source_manifest
from chaoslab.__main__ import source_digest
from chaoslab.contract_holdout import TASK
from chaoslab.contract_journal import ObservationJournal
from chaoslab.contractnli import evaluate

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def complete(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    import record_contract_test as recorder

    monkeypatch.chdir(tmp_path)
    data = fixture()
    provenance = {
        "archive_sha256": "a" * 64,
        "member": "contract-nli/test.json",
        "member_sha256": "b" * 64,
    }
    scorer, source = source_digest(), source_manifest()
    journal = ObservationJournal(
        "var/test", dataset=provenance, adapter=ADAPTER, scorer_sha256=scorer, task=TASK
    )
    results = evaluate(
        data, ADAPTER, invoke_adapter=lambda *_: oracle(), observer=journal.record, task=TASK
    )
    receipt = journal.finish()
    usage = {
        "provider": "bedrock",
        "model_id": "fixture",
        "region": "fixture",
        "price_card": {
            "model_id": "fixture",
            "region": "fixture",
            "input_usd_per_million": "1",
            "output_usd_per_million": "5",
            "verified_on": "2026-10-26",
            "source": "https://aws.amazon.com/bedrock/pricing/",
        },
        "receipts": [
            {
                "task": "contract_claims",
                "status": "validated",
                "input_tokens": 100,
                "output_tokens": 10,
                "estimated_cost_usd": "0.00015",
                "reserved_input_tokens": 24000,
                "reserved_output_tokens": 4096,
            }
        ],
        "estimated_model_cost_usd": "0.00015",
    }
    run = {
        "status": "complete",
        "live_model": True,
        "task": TASK,
        "protocol_sha256": "c" * 64,
        "dataset": provenance,
        "adapter": ADAPTER,
        "scorer_sha256": scorer,
        "source_manifest": source,
        "results": results,
        "observations": receipt,
        "usage": usage,
        "recorded_at": "2026-10-26T12:00:00+00:00",
        "wall_seconds": 1,
        "timing_scope": "fictional control",
        "min_interval_seconds": 0,
    }
    protocol = {
        "created_at": "2026-10-26T11:00:00+00:00",
        "recipe": {
            "execution_source_sha256": source["source_sha256"],
            "model_id": "fixture",
            "region": "fixture",
            "max_input_tokens": 24000,
            "max_output_tokens": 4096,
        },
    }
    return recorder, run, data, provenance, protocol, journal.final


def export(value):
    module, run, data, provenance, protocol, path = value
    return module.build_report(run, "d" * 64, data, provenance, protocol, "c" * 64, path)


def test_complete_test_export_replays_and_keeps_only_aggregates(complete):
    report = export(complete)
    assert report["results"]["label_accuracy"] == 1
    assert report["replay_matches_recorded_results"] is True
    assert report["usage"]["calls"] == 1 and report["usage"]["cost_is_invoice"] is False
    assert "predictions" not in report and "documents" not in report
    assert report["task"] == TASK


@pytest.mark.parametrize(
    "change",
    [
        "partial",
        "not_live",
        "development",
        "protocol",
        "source",
        "scores",
        "receipt",
        "model",
        "caps",
        "cost",
        "missing_usage",
        "continuation",
    ],
)
def test_changed_or_incomplete_test_evidence_is_not_exported(complete, change):
    module, original, data, provenance, original_protocol, path = complete
    run, protocol = copy.deepcopy(original), copy.deepcopy(original_protocol)
    if change == "partial":
        run["status"] = "failed"
    if change == "not_live":
        run["live_model"] = False
    if change == "development":
        run["task"] = "contractnli-development-v1"
    if change == "protocol":
        run["protocol_sha256"] = "0" * 64
    if change == "source":
        protocol["recipe"]["execution_source_sha256"] = "0" * 64
    if change == "scores":
        run["results"]["missing_predictions"] += 1
    if change == "receipt":
        run["observations"]["sha256"] = "0" * 64
    if change == "model":
        run["usage"]["model_id"] = "other-model"
    if change == "caps":
        run["usage"]["receipts"][0]["reserved_output_tokens"] = 8192
    if change == "cost":
        run["usage"]["estimated_model_cost_usd"] = "0"
    if change == "missing_usage":
        run["usage"]["receipts"] = []
    if change == "continuation":
        run["continuation"] = {}
    with pytest.raises(ValueError):
        export((module, run, data, provenance, protocol, path))
