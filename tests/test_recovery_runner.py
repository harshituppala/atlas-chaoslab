"""Recovery evaluation must survive the adapter failures it is meant to measure."""

import copy
import json
import os
import sys
from pathlib import Path

import pytest

from chaoslab import recovery


@pytest.fixture
def adapter(tmp_path, monkeypatch):
    (tmp_path / "recovery_runner_fixture.py").write_text("""
import sys, time

def run(body, fault):
    if body["mode"] == "hang":
        while True:
            time.sleep(0.1)
    if body["mode"] == "oversize":
        sys.stdout.write("x" * 3000000)
        sys.stdout.flush()
    if body["mode"] == "crash":
        raise RuntimeError("PRIVATE-RECOVERY-CANARY")
    if body["mode"] == "malformed":
        return {"observations": []}
    if body["mode"] == "leak":
        return {"observations": {"status": "PRIVATE-RECOVERY-CANARY", "results": True,
            "private": "PRIVATE-RECOVERY-CANARY"},
            "events": [{"note": "PRIVATE-RECOVERY-CANARY"}],
            "exception": "PRIVATE-RECOVERY-CANARY"}
    body["mode"] = "changed-only-in-child"
    return {"observations": {"status": "succeeded", "results": 1}}
""")
    monkeypatch.setenv("PYTHONPATH", str(tmp_path) + os.pathsep + str(Path("src").resolve()))
    return "recovery_runner_fixture:run"


def dataset(modes):
    return {
        "version": "1.0",
        "scope": "Controlled adapter failure diagnostic, not application recovery accuracy.",
        "cases": [
            {
                "id": f"case-{i}",
                "input": {"mode": mode},
                "expected": {"status": "succeeded", "results": 1},
            }
            for i, mode in enumerate(modes)
        ],
    }


def write_dataset(tmp_path, value):
    path = tmp_path / "input.json"
    path.write_text(json.dumps(value))
    return path


def test_real_deadline_records_failure_and_next_case_still_runs(tmp_path, adapter):
    value = dataset(["hang", "ok"])
    path = write_dataset(tmp_path, value)
    report = recovery.run(path, adapter, tmp_path / "report.json", deadline_seconds=0.5)
    assert report["cases_passed"] == 1 and report["unique_cases"] == 2
    assert report["results"][0]["error_code"] == "adapter_deadline"
    assert not report["results"][0]["passed"]
    assert report["results"][1]["passed"] and report["source_unchanged"]
    assert json.loads(path.read_text()) == value


@pytest.mark.parametrize(
    "mode,code",
    [
        ("oversize", "adapter_output_budget"),
        ("crash", "adapter_failure"),
        ("malformed", "invalid_observations"),
    ],
)
def test_real_adapter_faults_are_fixed_failures_without_source_text(tmp_path, adapter, mode, code):
    path = write_dataset(tmp_path, dataset([mode]))
    output = tmp_path / "report.json"
    report = recovery.run(path, adapter, output)
    assert report["cases_passed"] == 0
    assert report["results"][0]["error_code"] == code
    assert "PRIVATE-RECOVERY-CANARY" not in output.read_text()


def test_private_adapter_fields_and_wrong_typed_counter_are_not_exported(tmp_path, adapter):
    path = write_dataset(tmp_path, dataset(["leak"]))
    output = tmp_path / "report.json"
    report = recovery.run(path, adapter, output)
    result = report["results"][0]
    assert result["checks"] == {"status": False, "results": False}
    assert result["observations"] == {"status": None, "results": None}
    assert "events" not in result
    assert "PRIVATE-RECOVERY-CANARY" not in output.read_text()


def test_failed_cli_writes_evidence_before_nonzero_exit(tmp_path, adapter, monkeypatch):
    path = write_dataset(tmp_path, dataset(["crash"]))
    output = tmp_path / "report.json"
    monkeypatch.setattr(
        sys,
        "argv",
        ["recovery", "--dataset", str(path), "--adapter", adapter, "--output", str(output)],
    )
    with pytest.raises(SystemExit) as caught:
        recovery.main()
    assert caught.value.code == 1
    assert json.loads(output.read_text())["cases_passed"] == 0


@pytest.mark.parametrize(
    "mutation",
    [
        "empty-cases",
        "empty-expectations",
        "duplicate-id",
        "bool-counter",
        "unknown-observation",
        "unknown-state",
        "bad-id",
        "extra-envelope",
    ],
)
def test_ambiguous_or_vacuous_dataset_refused_before_adapter(tmp_path, mutation):
    value = dataset(["ok"])
    if mutation == "empty-cases":
        value["cases"] = []
    elif mutation == "empty-expectations":
        value["cases"][0]["expected"] = {}
    elif mutation == "duplicate-id":
        value["cases"].append(copy.deepcopy(value["cases"][0]))
    elif mutation == "bool-counter":
        value["cases"][0]["expected"]["results"] = True
    elif mutation == "unknown-observation":
        value["cases"][0]["expected"]["private-name"] = "secret"
    elif mutation == "unknown-state":
        value["cases"][0]["expected"]["status"] = "unrecognized"
    elif mutation == "bad-id":
        value["cases"][0]["id"] = "private text / outside ID contract"
    else:
        value["unknown"] = True
    path = write_dataset(tmp_path, value)
    with pytest.raises(ValueError):
        recovery.run(path, "must_not_import:run", tmp_path / "report.json")
    assert not (tmp_path / "report.json").exists()


@pytest.mark.parametrize("raw", ['{"version":"1.0","version":"1.0"}', '{"number":NaN}'])
def test_duplicate_json_and_nonfinite_constants_refused(tmp_path, raw):
    path = tmp_path / "input.json"
    path.write_text(raw)
    with pytest.raises(ValueError):
        recovery.read_dataset(path)


@pytest.mark.parametrize("change", ["dataset", "source"])
def test_changed_execution_identity_preserves_previous_report(tmp_path, monkeypatch, change):
    path = write_dataset(tmp_path, dataset(["ok"]))
    output = tmp_path / "report.json"
    output.write_text("previous evidence")

    def invoke(*args, **kwargs):
        if change == "dataset":
            path.write_text("changed dataset")
        return {"observations": {"status": "succeeded", "results": 1}}

    monkeypatch.setattr(recovery, "invoke", invoke)
    if change == "source":
        digests = iter(["before", "after"])
        monkeypatch.setattr(recovery, "source_digest", lambda: next(digests))
    with pytest.raises(ValueError, match="changed during execution"):
        recovery.run(path, "fixture:run", output)
    assert output.read_text() == "previous evidence"


def test_output_cannot_replace_dataset_and_deadline_is_finite(tmp_path):
    path = write_dataset(tmp_path, dataset(["ok"]))
    original = path.read_bytes()
    with pytest.raises(ValueError, match="overwrite"):
        recovery.run(path, "fixture:run", path)
    for value in [True, 0, float("nan"), float("inf"), 121]:
        with pytest.raises(ValueError, match="deadline"):
            recovery.run(path, "fixture:run", tmp_path / "report.json", deadline_seconds=value)
    assert path.read_bytes() == original
