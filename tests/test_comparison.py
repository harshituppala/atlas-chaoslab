"""Mutation tests for paired evidence and missing-case semantics, not model accuracy."""

import json
from copy import deepcopy
from pathlib import Path

import pytest
from test_scenarios import perfect

from chaoslab.comparison import compare, read_json
from chaoslab.scenarios import export_inputs


def fixtures():
    raw = Path("datasets/scenarios.json").read_bytes()
    dataset = json.loads(raw)
    exported = export_inputs(dataset, raw)
    bundle = {
        "dataset_sha256": exported["dataset_sha256"],
        "results": [
            {**row, "status": "succeeded", "output": perfect(case)}
            for case, row in zip(dataset["cases"], exported["cases"], strict=True)
        ],
    }
    return dataset, raw, bundle


def test_identical_complete_runs_have_no_invented_improvements():
    dataset, raw, bundle = fixtures()
    report = compare(dataset, raw, bundle, deepcopy(bundle))
    assert report["scenario_transitions"] == {
        "both_passed": 3,
        "both_failed": 0,
        "improved": 0,
        "regressed": 0,
        "unpaired": 0,
    }
    assert report["requirement_transitions"]["both_passed"] == 9
    assert report["fixture_gate_passed"] is True


def test_one_bad_obligation_can_regress_within_an_already_failing_scenario():
    dataset, raw, before = fixtures()
    before["results"][0]["output"]["assessments"][0]["draft"] = "invented draft"
    after = deepcopy(before)
    after["results"][0]["output"]["assessments"][1]["review_state"] = "approved"
    report = compare(dataset, raw, before, after)
    assert report["scenario_transitions"]["both_failed"] == 1
    assert report["scenario_transitions"]["regressed"] == 0
    assert report["requirement_transitions"]["regressed"] == 1
    assert report["fixture_gate_passed"] is False


def test_improvements_and_regressions_cannot_cancel_to_a_passing_gate():
    dataset, raw, before = fixtures()
    before["results"][0]["output"]["assessments"][0]["draft"] = "unsupported"
    after = fixtures()[2]
    after["results"][1]["output"]["assessments"][0]["evidence"][0]["digest"] = "bad"
    report = compare(dataset, raw, before, after)
    assert report["scenario_transitions"]["improved"] == 1
    assert report["scenario_transitions"]["regressed"] == 1
    assert not report["fixture_gate_passed"]


@pytest.mark.parametrize("side", ["reference", "candidate", "both"])
def test_missing_attempts_are_unpaired_not_failures_or_improvements(side):
    dataset, raw, before = fixtures()
    after = deepcopy(before)
    if side in {"reference", "both"}:
        before["results"] = []
    if side in {"candidate", "both"}:
        after["results"] = []
    report = compare(dataset, raw, before, after)
    assert report["scenario_transitions"]["unpaired"] == 3
    assert report["requirement_transitions"]["unpaired"] == 9
    assert not report["fixture_gate_passed"]
    assert report["scenario_transitions"]["improved"] == 0
    assert (
        all(s["reference_passed"] is None for s in report["scenarios"])
        if side != "candidate"
        else True
    )


def test_attempted_execution_failure_is_visible_and_blocks_gate_even_if_candidate_recovers():
    dataset, raw, after = fixtures()
    before = deepcopy(after)
    row = before["results"][0]
    row["status"] = "failed"
    del row["output"]
    row["error"] = "secret exception details"
    report = compare(dataset, raw, before, after)
    assert report["coverage"]["execution_failures"] == {"reference": 1, "candidate": 0}
    assert report["scenarios"][0]["reference_execution"] == "failed"
    assert report["scenario_transitions"]["improved"] == 1
    assert not report["fixture_gate_passed"]
    assert "secret exception" not in json.dumps(report)


@pytest.mark.parametrize(
    "mutation", ["dataset", "duplicate", "unknown", "input", "source", "status"]
)
def test_identity_confusion_is_rejected(mutation):
    dataset, raw, before = fixtures()
    after = deepcopy(before)
    row = after["results"][0]
    if mutation == "dataset":
        after["dataset_sha256"] = "0" * 64
    elif mutation == "duplicate":
        after["results"][1] = deepcopy(row)
    elif mutation == "unknown":
        row["id"] = "unknown"
    elif mutation == "input":
        row["input_sha256"] = "0" * 64
    elif mutation == "source":
        row["output"]["documents"][0]["text"] += " changed"
    else:
        row["status"] = "skipped"
    with pytest.raises(ValueError):
        compare(dataset, raw, before, after)


def test_row_order_does_not_change_pairing():
    dataset, raw, before = fixtures()
    after = deepcopy(before)
    after["results"].reverse()
    assert compare(dataset, raw, before, before) == compare(dataset, raw, before, after)


def test_aggregates_without_raw_outputs_are_rejected():
    dataset, raw, bundle = fixtures()
    with pytest.raises(ValueError, match="result coverage"):
        compare(dataset, raw, bundle, {"dataset_sha256": bundle["dataset_sha256"], "passed": 3})


@pytest.mark.parametrize("text", ['{"results":[],"results":[1]}', '{"value":NaN}'])
def test_ambiguous_or_nonfinite_artifacts_rejected(tmp_path, text):
    path = tmp_path / "artifact.json"
    path.write_text(text)
    with pytest.raises(ValueError):
        read_json(path)


def test_artifact_byte_budget_is_enforced_before_parsing(tmp_path, monkeypatch):
    import chaoslab.comparison as module

    monkeypatch.setattr(module, "MAX_BYTES", 12)
    path = tmp_path / "artifact.json"
    path.write_bytes(b" " * 13)
    with pytest.raises(ValueError, match="byte budget"):
        read_json(path)


def test_dataset_object_cannot_silently_change_bound_expectations():
    dataset, raw, before = fixtures()
    dataset["cases"][0]["expected"][0]["relation"] = "insufficient"
    with pytest.raises(ValueError, match="bound bytes"):
        compare(dataset, raw, before, before)


def test_cli_refuses_input_alias_without_touching_it(tmp_path, monkeypatch):
    import chaoslab.comparison as module

    dataset, raw, before = fixtures()
    path = tmp_path / "dataset.json"
    path.write_bytes(raw)
    bundle = tmp_path / "bundle.json"
    bundle.write_text(json.dumps(before))
    monkeypatch.setattr(
        "sys.argv",
        [
            "comparison",
            "--dataset",
            str(path),
            "--reference",
            str(bundle),
            "--candidate",
            str(bundle),
            "--output",
            str(path),
        ],
    )
    with pytest.raises(SystemExit):
        module.main()
    assert path.read_bytes() == raw


def test_drift_refusal_preserves_previous_report(tmp_path, monkeypatch):
    import chaoslab.comparison as module

    _, raw, before = fixtures()
    dataset = tmp_path / "dataset.json"
    dataset.write_bytes(raw)
    bundle = tmp_path / "bundle.json"
    bundle.write_text(json.dumps(before))
    output = tmp_path / "report.json"
    output.write_text('"existing measured evidence"')
    calls = iter([{"scorer": "original"}, {"scorer": "changed"}])
    monkeypatch.setattr(module, "scorer_hashes", lambda: next(calls))
    monkeypatch.setattr(
        "sys.argv",
        [
            "comparison",
            "--dataset",
            str(dataset),
            "--reference",
            str(bundle),
            "--candidate",
            str(bundle),
            "--output",
            str(output),
        ],
    )
    with pytest.raises(SystemExit, match="changed"):
        module.main()
    assert output.read_text() == '"existing measured evidence"'


def test_optional_fixture_gate_writes_failed_evidence_then_exits_nonzero(tmp_path, monkeypatch):
    import chaoslab.comparison as module

    _, raw, before = fixtures()
    before["results"][0]["status"] = "failed"
    dataset = tmp_path / "dataset.json"
    dataset.write_bytes(raw)
    bundle = tmp_path / "bundle.json"
    bundle.write_text(json.dumps(before))
    output = tmp_path / "comparison.json"
    monkeypatch.setattr(
        "sys.argv",
        [
            "comparison",
            "--dataset",
            str(dataset),
            "--reference",
            str(bundle),
            "--candidate",
            str(bundle),
            "--output",
            str(output),
            "--require-fixture-gate",
        ],
    )
    with pytest.raises(SystemExit) as error:
        module.main()
    assert error.value.code == 1
    report = json.loads(output.read_text())
    assert report["fixture_gate_passed"] is False
    assert report["coverage"]["execution_failures"]["candidate"] == 1
    assert "output" not in json.dumps(report["scenarios"])
