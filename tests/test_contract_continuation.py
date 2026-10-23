"""Saved wrong answers stay wrong; only unobserved inputs reach a stubbed provider."""

import json
from decimal import Decimal
from pathlib import Path

import pytest
from botocore.stub import Stubber
from test_contract_checkpoint import stopped as stopped
from test_contract_model import PROVENANCE, enqueue
from test_model_gateway import client as client
from test_model_gateway import config as config

from atlas.models import contract_continuation as task
from atlas.models.bedrock import BedrockGateway
from atlas.models.session_budget import SessionBudget, reserve_configured_run
from chaoslab.contract_journal import input_digest, read_observations
from chaoslab.contractnli import adapter_input, evaluate


def prepared(stopped, config):
    data, origin, budget = stopped
    return task.prepare(data, PROVENANCE, origin, budget, config)


def test_plan_counts_only_new_calls_and_does_not_touch_origin_or_campaign(stopped, config):
    data, origin, budget = stopped
    before = {p: p.read_bytes() for p in [*origin.iterdir(), budget]}
    tail, records, snapshots, lineage = prepared(stopped, config)
    assert tail.limits.max_calls == len(records) == 1
    assert lineage["saved_documents"] == lineage["new_documents"] == 1
    assert lineage["old_reservation_retained"] is True
    assert lineage["response_authenticity_verified"] is False
    assert lineage["tail_reservation_plan"]["call_cap"] == 1
    assert snapshots["run.json"] == before[origin / "run.json"]
    assert before == {p: p.read_bytes() for p in before}


def test_one_new_call_completes_full_cohort_and_replays_without_model(stopped, config, client):
    data, origin, budget = stopped
    tail, records, snapshots, lineage = prepared(stopped, config)
    before = {p: p.read_bytes() for p in origin.iterdir()}
    reserve_configured_run(budget, tail, Path("var/continued/run.json"))
    balance = SessionBudget.model_validate_json(budget.read_bytes())
    assert len(balance.reservations) == 2
    assert balance.reservations[0].reserved_usd == Decimal("0.0036")
    with Stubber(client) as stub:
        enqueue(stub)
        report = task.run(
            data,
            PROVENANCE,
            BedrockGateway(client, tail),
            "var/continued",
            origin,
            records,
            snapshots,
            lineage,
            interval=0,
        )
        stub.assert_no_pending_responses()
    assert report["status"] == "complete" and report["results"]["claims"] == 6
    assert len(report["usage"]["receipts"]) == 1
    assert report["continuation"] == lineage
    assert before == {p: p.read_bytes() for p in before}
    header, replay, receipt = read_observations(
        "var/continued/observations.jsonl",
        dataset=PROVENANCE,
        inputs={d["id"]: adapter_input(d, data["labels"]) for d in data["documents"]},
    )
    rescored = evaluate(
        data,
        header["adapter"],
        invoke_adapter=lambda _, body: replay[body["document"]["id"]]["output"],
    )
    assert report["results"] == rescored and report["observations"] == receipt
    assert "A fictional promise" not in Path("var/continued/run.json").read_text()


def test_saved_wrong_prediction_is_not_repaired_or_sent_again(stopped, config, client):
    data, origin, _ = stopped
    # Output shapes and receipt fingerprints cannot attest to a prior answer's truth.
    path = origin / "observations.partial.jsonl"
    lines = path.read_text().splitlines()
    record = json.loads(lines[1])
    record["output"]["predictions"][0]["choice"] = "Contradiction"
    lines[1] = json.dumps(record)
    path.write_text("\n".join(lines) + "\n")
    tail, records, snapshots, lineage = prepared(stopped, config)
    with Stubber(client) as stub:
        enqueue(stub)
        report = task.run(
            data,
            PROVENANCE,
            BedrockGateway(client, tail),
            "var/wrong-prefix",
            origin,
            records,
            snapshots,
            lineage,
            interval=0,
        )
        stub.assert_no_pending_responses()
    assert report["status"] == "complete"
    assert report["results"]["label_accuracy"] < 1
    assert len(report["usage"]["receipts"]) == 1


@pytest.mark.parametrize("kind", ["model", "region", "input_cap", "output_cap"])
def test_changed_model_or_caps_are_rejected_before_new_call(stopped, config, kind):
    raw = config.model_dump(mode="json")
    if kind in ("model", "region"):
        field = "model_id" if kind == "model" else "region"
        raw[field] = "different"
        raw["price_card"][field] = "different"
    else:
        raw["limits"]["max_input_tokens" if kind == "input_cap" else "max_output_tokens"] += 1
    with pytest.raises(ValueError):
        prepared(stopped, config.model_validate(raw))


def test_input_order_and_content_changes_fail_before_any_model_call(stopped, config):
    data, _, _ = stopped
    _, records, _, _ = prepared(stopped, config)
    called = []
    adapter = task.PrefixThenModel(data, records, lambda *_: called.append(True))
    second = adapter_input(data["documents"][1], data["labels"])
    with pytest.raises(task.ContinuationIntegrityError):
        adapter(None, second)
    assert not called
    first = adapter_input(data["documents"][0], data["labels"])
    out = adapter(None, first)
    out["predictions"].clear()
    assert records[0]["output"]["predictions"]
    assert input_digest(first) == adapter.expected[0]


def test_changed_origin_before_execution_creates_no_new_run(stopped, config, client):
    data, origin, _ = stopped
    tail, records, snapshots, lineage = prepared(stopped, config)
    (origin / "run.json").write_text("{}")
    with pytest.raises(task.ContinuationIntegrityError):
        task.run(
            data,
            PROVENANCE,
            BedrockGateway(client, tail),
            "var/changed",
            origin,
            records,
            snapshots,
            lineage,
            interval=0,
        )
    assert not Path("var/changed").exists()


def test_changed_origin_during_call_stops_publication(stopped, config):
    data, origin, _ = stopped
    tail, records, snapshots, lineage = prepared(stopped, config)
    from test_contractnli import oracle

    class Gateway:
        live = False

        def __init__(self):
            from atlas.models.bedrock import Ledger

            self.config = tail
            self.ledger = Ledger(tail)

        def structured(self, *, output, **_):
            (origin / "run.json").write_text("{}")
            return output.model_validate(oracle())

    with pytest.raises(task.ContinuationIntegrityError):
        task.run(
            data,
            PROVENANCE,
            Gateway(),
            "var/changed-during",
            origin,
            records,
            snapshots,
            lineage,
            interval=0,
        )
    report = json.loads(Path("var/changed-during/run.json").read_text())
    assert report["status"] == "failed" and report["results"] is None
    assert not Path("var/changed-during/observations.jsonl").exists()


def test_dry_run_does_not_open_credentials_or_mutate_campaign(stopped, config, monkeypatch, capsys):
    data, origin, budget = stopped
    before = budget.read_bytes()
    monkeypatch.setattr(task, "load_development", lambda _: (data, PROVENANCE))
    monkeypatch.setattr(task, "read_config", lambda _: config)
    monkeypatch.setattr(
        task.BedrockGateway, "open", lambda *_a, **_kw: pytest.fail("No SDK opening in dry run")
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "continuation",
            "--archive",
            "unused",
            "--config",
            "unused",
            "--origin",
            str(origin),
            "--run-dir",
            "var/plan-only",
            "--session-budget",
            str(budget),
        ],
    )
    task.main()
    plan = json.loads(capsys.readouterr().out)
    assert plan["inference_sent"] is False
    assert plan["continuation"]["new_documents"] == 1
    assert not Path("var/plan-only").exists() and budget.read_bytes() == before


def test_tail_reservation_refusal_preserves_old_authorization(stopped, config):
    _, _, budget = stopped
    tail, _, _, _ = prepared(stopped, config)
    raw = json.loads(budget.read_text())
    raw["authorized_usd"] = "0.0036"
    budget.write_text(json.dumps(raw))
    before = budget.read_bytes()
    with pytest.raises(ValueError):
        reserve_configured_run(budget, tail, Path("var/no-funds/run.json"))
    assert budget.read_bytes() == before
    assert not Path("var/no-funds").exists()


def test_preflight_failure_in_tail_does_not_publish_partial_cohort(stopped, config, client):
    data, origin, _ = stopped
    tail, records, snapshots, lineage = prepared(stopped, config)
    before = {p: p.read_bytes() for p in origin.iterdir()}
    from botocore.stub import ANY

    with Stubber(client) as stub:
        stub.add_client_error(
            "count_tokens",
            service_error_code="ThrottlingException",
            expected_params={"modelId": "synthetic-model", "input": ANY},
        )
        report = task.run(
            data,
            PROVENANCE,
            BedrockGateway(client, tail),
            "var/stopped-again",
            origin,
            records,
            snapshots,
            lineage,
            interval=0,
        )
        stub.assert_no_pending_responses()
    assert report["status"] == "failed" and report["results"] is None
    assert report["observations"] is None
    assert not Path("var/stopped-again/observations.jsonl").exists()
    assert len(Path("var/stopped-again/observations.partial.jsonl").read_text().splitlines()) == 2
    assert before == {p: p.read_bytes() for p in before}


def test_original_limit_must_fund_the_tail_not_be_silently_increased(stopped, config):
    data, _, _ = stopped
    third = json.loads(json.dumps(data["documents"][1]))
    third["id"] = 3
    data["documents"].append(third)
    value = config.model_dump(mode="json")
    value["limits"]["max_calls"] = 1
    with pytest.raises(ValueError):
        prepared(stopped, config.model_validate(value))


@pytest.mark.parametrize(
    "mutation",
    ["none", "missing_origin", "lineage_count", "prefix_bytes", "missing_tail_reservation"],
)
def test_export_binds_copied_answers_and_both_reservations(stopped, config, client, mutation):
    from test_contract_model_export import export

    data, origin, budget = stopped
    tail, records, snapshots, lineage = prepared(stopped, config)
    if mutation != "missing_tail_reservation":
        reserve_configured_run(budget, tail, Path("var/exported/run.json"))
    with Stubber(client) as stub:
        enqueue(stub)
        report = task.run(
            data,
            PROVENANCE,
            BedrockGateway(client, tail),
            "var/exported",
            origin,
            records,
            snapshots,
            lineage,
            interval=0,
        )
    report["live_model"] = True  # Controlled admission check, not a live-provider claim.
    if mutation == "lineage_count":
        report["continuation"]["saved_documents"] = 99
    if mutation == "prefix_bytes":
        path = origin / "observations.partial.jsonl"
        path.write_bytes(path.read_bytes().replace(b"Entailment", b"NotMentioned"))

    def publish():
        return export.build_report(
            report,
            "a" * 64,
            data,
            PROVENANCE,
            "var/exported/observations.jsonl",
            origin=None if mutation == "missing_origin" else origin,
            budget=budget,
        )

    if mutation != "none":
        with pytest.raises(ValueError):
            publish()
    else:
        result = publish()
        assert result["results"]["claims"] == 6
        assert result["usage"]["calls"] == result["saved_prefix_usage"]["calls"] == 1
        assert result["continuation"]["saved_documents"] == 1
        assert "A fictional promise" not in json.dumps(result)
        assert "Not an uninterrupted model run" in result["limits"]
