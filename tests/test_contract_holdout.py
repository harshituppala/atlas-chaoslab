"""Protocol and split-boundary controls use fictional archives, never the real test split."""

import copy
import hashlib
import json
import sys
import zipfile
from pathlib import Path

import pytest
from test_contractnli import fixture, oracle
from test_model_gateway import config as config

from atlas.models import contract_holdout as bridge
from chaoslab import contract_holdout as holdout
from chaoslab import contractnli
from chaoslab.contract_journal import ObservationJournal, canonical, read_observations
from chaoslab.contractnli import adapter_input, evaluate

ADAPTER = "unavailable.task:no_import"


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    data = fixture()
    archive = tmp_path / "fictional.zip"
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr("contract-nli/dev.json", json.dumps(data))
        zipped.writestr("contract-nli/test.json", json.dumps(data))
    fingerprint = hashlib.sha256(archive.read_bytes()).hexdigest()
    monkeypatch.setattr(holdout, "ARCHIVE_SHA256", fingerprint)
    monkeypatch.setattr(
        holdout,
        "load_development",
        lambda path: contractnli.load_development(path, expected_sha256=fingerprint),
    )
    _, provenance = holdout.load_development(archive)
    journal = ObservationJournal(
        "var/dev", dataset=provenance, adapter=ADAPTER, scorer_sha256="a" * 64
    )
    result = evaluate(data, ADAPTER, invoke_adapter=lambda *_: oracle(), observer=journal.record)
    receipt = journal.finish()
    report = tmp_path / "development.json"
    report.write_text(
        json.dumps(
            {
                "dataset": provenance,
                "results": result,
                "observations": receipt,
                "replay_matches_recorded_results": True,
            }
        )
    )
    return archive, journal.final, report


def frozen(prepared, recipe=None):
    archive, observations, report = prepared
    protocol = Path("var/protocol.json")
    checksum = holdout.freeze(archive, report, observations, recipe or {}, protocol)
    return protocol, checksum


def rewrite(protocol, mutate):
    value = json.loads(protocol.read_text())
    mutate(value)
    raw = canonical(value) + b"\n"
    protocol.write_bytes(raw)
    return holdout.sha(raw)


def test_freeze_replays_complete_development_without_reading_test(prepared, monkeypatch):
    opened = []
    original = zipfile.ZipFile.open

    def tracked(self, name, *args, **kwargs):
        opened.append(name.filename if isinstance(name, zipfile.ZipInfo) else name)
        return original(self, name, *args, **kwargs)

    monkeypatch.setattr(zipfile.ZipFile, "open", tracked)
    protocol, checksum = frozen(prepared)
    assert opened == ["contract-nli/dev.json"]
    assert protocol.stat().st_mode & 0o777 == 0o600
    assert holdout.check_protocol(protocol, checksum)["policy"]["primary"] == "macro_label_f1"
    with pytest.raises(FileExistsError):
        holdout.freeze(prepared[0], prepared[2], prepared[1], {}, protocol)


@pytest.mark.parametrize("kind", ["policy", "split", "archive", "scorer", "task", "schema"])
def test_modified_protocol_rejected_even_with_updated_checksum(prepared, kind, monkeypatch):
    protocol, _ = frozen(prepared)

    def mutate(value):
        if kind == "policy":
            value["policy"]["missing"] = "Drop omissions"
        if kind == "split":
            value["member"] = "contract-nli/dev.json"
        if kind == "archive":
            value["archive_sha256"] = "0" * 64
        if kind == "scorer":
            value["scorer_files"] = {}
        if kind == "task":
            value["task"] = "contractnli-development-v1"
        if kind == "schema":
            value["schema_version"] = True

    checksum = rewrite(protocol, mutate)
    monkeypatch.setattr(holdout, "_load_split", lambda *_a, **_k: pytest.fail("Test JSON was read"))
    with pytest.raises(ValueError):
        holdout.load_test(prepared[0], protocol, checksum)


def test_wrong_pin_and_changed_execution_settings_fail_before_test_read(
    prepared, config, monkeypatch
):
    protocol, checksum = frozen(prepared, bridge.recipe(config))
    monkeypatch.setattr(holdout, "_load_split", lambda *_a, **_k: pytest.fail("Test JSON was read"))
    with pytest.raises(bridge.ProtocolChanged):
        bridge.prepare(prepared[0], protocol, "0" * 64, config)
    changed = config.model_copy(deep=True)
    changed.limits.max_output_tokens += 1
    with pytest.raises(bridge.ProtocolChanged):
        bridge.prepare(prepared[0], protocol, checksum, changed)
    monkeypatch.setattr(bridge, "source_manifest", lambda: {"source_sha256": "0" * 64})
    with pytest.raises(bridge.ProtocolChanged):
        bridge.guard(protocol, checksum, config)


@pytest.mark.parametrize("kind", ["results", "receipt", "dataset", "partial"])
def test_freeze_rejects_incomplete_or_changed_development_evidence(prepared, kind):
    archive, observations, report = prepared
    value = json.loads(report.read_text())
    if kind == "results":
        value["results"]["missing_predictions"] += 1
    if kind == "receipt":
        value["observations"]["sha256"] = "0" * 64
    if kind == "dataset":
        value["dataset"]["member"] = "contract-nli/test.json"
    if kind == "partial":
        observations.write_bytes(b"\n".join(observations.read_bytes().splitlines()[:-1]) + b"\n")
    report.write_text(json.dumps(value))
    with pytest.raises(ValueError):
        frozen(prepared)
    assert not Path("var/protocol.json").exists()


def test_explicit_test_journal_replays_but_cannot_masquerade_as_development(prepared):
    protocol, checksum = frozen(prepared)
    data, provenance = holdout.load_test(prepared[0], protocol, checksum)
    journal = ObservationJournal(
        "var/test", dataset=provenance, adapter=ADAPTER, scorer_sha256="a" * 64, task=holdout.TASK
    )
    expected = evaluate(
        data,
        ADAPTER,
        invoke_adapter=lambda *_: oracle(),
        observer=journal.record,
        task=holdout.TASK,
    )
    receipt = journal.finish()
    result, restored = holdout.replay_result(data, provenance, journal.final, task=holdout.TASK)
    assert result == expected and restored == receipt
    with pytest.raises(ValueError):
        read_observations(
            journal.final,
            dataset=provenance,
            inputs={
                d["id"]: adapter_input(d, data["labels"], task=holdout.TASK)
                for d in data["documents"]
            },
        )
    with pytest.raises(ValueError):
        holdout.replay_result(data, provenance, prepared[1], task=holdout.TASK)


def test_test_replay_cli_writes_aggregates_without_adapter_or_provider(prepared, monkeypatch):
    protocol, checksum = frozen(prepared)
    data, provenance = holdout.load_test(prepared[0], protocol, checksum)
    journal = ObservationJournal(
        "var/test", dataset=provenance, adapter=ADAPTER, scorer_sha256="a" * 64, task=holdout.TASK
    )
    evaluate(
        data,
        ADAPTER,
        invoke_adapter=lambda *_: oracle(),
        observer=journal.record,
        task=holdout.TASK,
    )
    journal.finish()
    output = Path("var/replay.json")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "holdout",
            "--archive",
            str(prepared[0]),
            "--protocol",
            str(protocol),
            "--protocol-sha256",
            checksum,
            "--replay",
            str(journal.final),
            "--output",
            str(output),
        ],
    )
    holdout.main()
    value = json.loads(output.read_text())
    assert value["results"]["label_accuracy"] == 1
    assert value["task"] == holdout.TASK
    assert "predictions" not in value and "document" not in value


def test_model_receives_same_request_for_both_split_identities():
    from atlas.models.contract_evaluation import request

    data = fixture()
    development = adapter_input(data["documents"][0], data["labels"])
    test = copy.deepcopy(development)
    test["task"] = holdout.TASK
    dev_body, dev_schema = request(development)
    test_body, test_schema = request(test)
    assert (
        dev_body == test_body and dev_schema.model_json_schema() == test_schema.model_json_schema()
    )


def test_protocol_failure_escapes_wrong_answer_scoring():
    def changed(*_):
        raise bridge.ProtocolChanged("Protocol changed")

    with pytest.raises(bridge.ProtocolChanged):
        evaluate(fixture(), ADAPTER, invoke_adapter=changed, task=holdout.TASK)


def test_dry_plan_never_resolves_credentials_reserves_or_creates_run(
    prepared, config, monkeypatch, capsys
):
    protocol, checksum = frozen(prepared, bridge.recipe(config))
    path = Path("var/config.json")
    path.write_text(config.model_dump_json())
    path.chmod(0o600)
    monkeypatch.setattr(
        bridge.BedrockGateway, "open", lambda *_a, **_k: pytest.fail("Provider setup in dry plan")
    )
    monkeypatch.setattr(
        bridge, "reserve_configured_run", lambda *_a, **_k: pytest.fail("Reservation in dry plan")
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "holdout",
            "--archive",
            str(prepared[0]),
            "--config",
            str(path),
            "--protocol",
            str(protocol),
            "--protocol-sha256",
            checksum,
            "--run-dir",
            "var/new-run",
        ],
    )
    bridge.main()
    assert not Path("var/new-run").exists()
    result = json.loads(capsys.readouterr().out)
    assert result["provider_requests"] == 0
    assert result["dataset"]["member"] == "contract-nli/test.json"


@pytest.mark.parametrize("raw", [b"[]", b"42", b'{"schema_version":NaN}', b'{"a":1,"a":2}'])
def test_malformed_protocols_fail_closed(prepared, raw):
    protocol, _ = frozen(prepared)
    protocol.write_bytes(raw)
    with pytest.raises(ValueError):
        holdout.check_protocol(protocol, holdout.sha(raw))


def test_full_cohort_capacity_is_narrowed_not_over_reserved(prepared, config):
    config = config.model_copy(deep=True)
    config.limits.max_calls = 123
    config.limits.max_reserved_tokens = 123 * (
        config.limits.max_input_tokens + config.limits.max_output_tokens
    )
    protocol, checksum = frozen(prepared, bridge.recipe(config))
    data, _, plan, selected = bridge.prepare(prepared[0], protocol, checksum, config)
    assert plan["call_cap"] == len(data["documents"]) == selected.limits.max_calls == 1
    assert selected.limits.max_reserved_tokens < config.limits.max_reserved_tokens
    assert bridge.recipe(selected) == bridge.recipe(config)
