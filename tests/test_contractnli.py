"""Fictional schema/scoring controls; no external contracts are bundled here."""

import copy
import hashlib
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from chaoslab.contractnli import (
    MEMBER,
    adapter_input,
    always_not_mentioned,
    evaluate,
    load_development,
    validate_development,
)
from chaoslab.execution import AdapterDeadline


def fixture():
    return {
        "labels": {
            key: {"hypothesis": text}
            for key, text in {
                "one": "The promise continues.",
                "two": "The promise expires.",
                "three": "An audit is required.",
            }.items()
        },
        "documents": [
            {
                "id": 1,
                "text": "A fictional promise continues.",
                "spans": [[0, 30]],
                "annotation_sets": [
                    {
                        "annotations": {
                            "one": {"choice": "Entailment", "spans": [0]},
                            "two": {"choice": "Contradiction", "spans": [0]},
                            "three": {"choice": "NotMentioned", "spans": []},
                        }
                    }
                ],
            }
        ],
    }


def oracle():
    return {
        "predictions": [
            {"id": "one", "choice": "Entailment", "spans": [0]},
            {"id": "two", "choice": "Contradiction", "spans": [0]},
            {"id": "three", "choice": "NotMentioned", "spans": []},
        ]
    }


def archive_file(tmp_path, *, raw=None, extra=(), duplicate=False):
    path = tmp_path / "dataset.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(MEMBER, json.dumps(fixture()) if raw is None else raw)
        for name, value in extra:
            archive.writestr(name, value)
        if duplicate:
            with pytest.warns(UserWarning):
                archive.writestr(MEMBER, json.dumps(fixture()))
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


def test_loader_reads_only_fixed_member_and_never_extracts_paths(tmp_path):
    path, digest = archive_file(
        tmp_path,
        extra=[
            ("../../escape.txt", "PRIVATE-MARKER"),
            ("contract-nli/test.json", "TEST-MUST-NOT-BE-PARSED"),
            ("contract-nli/originals/nonportable\\name.pdf", "not used"),
        ],
    )
    loaded, provenance = load_development(path, expected_sha256=digest)
    assert loaded == fixture() and provenance["archive_sha256"] == digest
    assert provenance["member"] == MEMBER
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize(
    "kind", ["pin", "duplicate", "bad_json", "deep_json", "duplicate_json", "link", "directory"]
)
def test_archive_admission_refuses_unsafe_or_ambiguous_selected_input(tmp_path, kind):
    raw = {
        "bad_json": "PRIVATE-MARKER",
        "deep_json": "[" * 1100,
        "duplicate_json": '{"labels":1,"labels":2}',
    }.get(kind)
    path, digest = archive_file(tmp_path, raw=raw, duplicate=kind == "duplicate")
    if kind == "pin":
        digest = "0" * 64
    elif kind == "link":
        linked = tmp_path / "linked.zip"
        linked.symlink_to(path)
        path = linked
    elif kind == "directory":
        path = tmp_path
    with pytest.raises(ValueError, match="^ContractNLI archive or development split rejected$"):
        load_development(path, expected_sha256=digest)


@pytest.mark.parametrize(
    "kind",
    [
        "duplicate_id",
        "empty_labels",
        "missing_annotation",
        "bad_choice",
        "bad_span",
        "boolean_span",
        "duplicate_evidence",
        "unknown_evidence",
        "neutral_evidence",
        "missing_evidence",
        "multiple_annotations",
        "bad_text",
    ],
)
def test_invalid_gold_annotations_fail_before_an_adapter_runs(kind):
    data = fixture()
    doc = data["documents"][0]
    ann = doc["annotation_sets"][0]["annotations"]
    if kind == "duplicate_id":
        data["documents"].append(copy.deepcopy(doc))
    elif kind == "empty_labels":
        data["labels"] = {}
    elif kind == "missing_annotation":
        del ann["one"]
    elif kind == "bad_choice":
        ann["one"]["choice"] = "PRIVATE-MARKER"
    elif kind == "bad_span":
        doc["spans"][0][1] = 999
    elif kind == "boolean_span":
        doc["spans"][0][0] = False
    elif kind == "duplicate_evidence":
        ann["one"]["spans"] = [0, 0]
    elif kind == "unknown_evidence":
        ann["one"]["spans"] = [1]
    elif kind == "neutral_evidence":
        ann["three"]["spans"] = [0]
    elif kind == "missing_evidence":
        ann["one"]["spans"] = []
    elif kind == "multiple_annotations":
        doc["annotation_sets"].append(copy.deepcopy(doc["annotation_sets"][0]))
    else:
        doc["text"] = "\ud800"
    with pytest.raises(ValueError, match="^Invalid ContractNLI development annotations$"):
        evaluate(
            data, "unused:adapter", invoke_adapter=lambda *_: pytest.fail("Adapter must not run")
        )


def test_oracle_and_independent_evidence_checks():
    perfect = evaluate(fixture(), "controlled:oracle", invoke_adapter=lambda *_: oracle())
    assert perfect["label_accuracy"] == perfect["macro_label_f1"] == 1
    assert perfect["joint_label_and_exact_evidence"] == 1
    assert perfect["evidence"]["micro_precision"] == perfect["evidence"]["micro_recall"] == 1
    wrong = oracle()
    wrong["predictions"][0]["choice"] = "Contradiction"
    result = evaluate(fixture(), "controlled:wrong", invoke_adapter=lambda *_: wrong)
    assert result["label_accuracy"] == pytest.approx(2 / 3)
    assert result["evidence"]["exact_sets"] == 2
    assert result["joint_label_and_exact_evidence"] == pytest.approx(2 / 3)
    wrong = oracle()
    wrong["predictions"][0]["spans"] = []
    result = evaluate(fixture(), "controlled:missing_evidence", invoke_adapter=lambda *_: wrong)
    assert result["label_accuracy"] == 1
    assert result["joint_label_and_exact_evidence"] == pytest.approx(2 / 3)


def test_constant_baseline_claims_no_evidence_and_exposes_class_imbalance():
    data = fixture()
    result = evaluate(
        data, "controlled:baseline", invoke_adapter=lambda _, inputs: always_not_mentioned(inputs)
    )
    assert result["label_accuracy"] == pytest.approx(1 / 3)
    assert result["macro_label_f1"] == pytest.approx(1 / 6)
    assert result["evidence"]["micro_precision"] is None
    assert result["evidence"]["micro_recall"] == 0


def test_adapter_input_contains_no_annotation_or_source_metadata():
    data = fixture()
    doc = data["documents"][0]
    doc.update(url="PRIVATE-MARKER", file_name="PRIVATE-MARKER")
    value = adapter_input(doc, data["labels"])
    assert set(value) == {"task", "document", "hypotheses"}
    assert set(value["document"]) == {"id", "text", "spans"}
    assert all(set(item) == {"id", "text"} for item in value["hypotheses"])
    assert "annotations" not in json.dumps(value) and "PRIVATE-MARKER" not in json.dumps(value)
    value["document"]["spans"][0][0] = 999
    assert doc["spans"][0][0] == 0


@pytest.mark.parametrize(
    "kind",
    [
        "unknown",
        "duplicate",
        "bad_choice",
        "bad_index",
        "boolean_index",
        "extra_field",
        "neutral_evidence",
    ],
)
def test_unusable_prediction_marks_all_document_claims_failed(kind):
    output = oracle()
    first = output["predictions"][0]
    if kind == "unknown":
        first["id"] = "unknown"
    elif kind == "duplicate":
        output["predictions"][1]["id"] = "one"
    elif kind == "bad_choice":
        first["choice"] = "supported"
    elif kind == "bad_index":
        first["spans"] = [999]
    elif kind == "boolean_index":
        first["spans"] = [False]
    elif kind == "extra_field":
        output["private"] = "PRIVATE-MARKER"
    else:
        output["predictions"][2]["spans"] = [0]
    result = evaluate(fixture(), "controlled:invalid", invoke_adapter=lambda *_: output)
    assert result["failed_documents"] == 1 and result["label_accuracy"] == 0
    assert result["joint_label_and_exact_evidence"] == 0
    assert all(row == {"failed": 1} for row in result["confusion"].values())


def test_missing_outputs_and_deadlines_remain_in_denominators():
    result = evaluate(fixture(), "controlled:empty", invoke_adapter=lambda *_: {"predictions": []})
    assert result["missing_predictions"] == 3 and result["failed_documents"] == 0
    assert result["label_accuracy"] == 0

    def timeout(*_):
        raise AdapterDeadline("PRIVATE-MARKER")

    result = evaluate(fixture(), "controlled:timeout", invoke_adapter=timeout)
    assert result["failed_documents"] == 1 and result["claims"] == 3
    assert "PRIVATE-MARKER" not in json.dumps(result)


def test_runtime_validation_remains_enabled_under_python_optimization():
    code = "from chaoslab.contractnli import validate_development; validate_development({'labels':{},'documents':[]})"
    result = subprocess.run(
        [sys.executable, "-O", "-c", code],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")},
    )
    assert result.returncode != 0 and "Invalid ContractNLI" in result.stderr


def test_existing_adapter_process_boundary_runs_the_constant_baseline():
    result = evaluate(fixture(), "chaoslab.contractnli:always_not_mentioned")
    assert result["claims"] == 3 and result["failed_documents"] == 0
    assert result["label_accuracy"] == pytest.approx(1 / 3)


def test_valid_fixture_passes_admission():
    validate_development(fixture())


def test_bad_adapter_configuration_preserves_report_before_loading_data(tmp_path):
    report = tmp_path / "previous.json"
    report.write_text("previous evidence")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "chaoslab.contractnli",
            "--archive",
            str(tmp_path / "absent.zip"),
            "--adapter",
            "PRIVATE-MARKER",
            "--output",
            str(report),
        ],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")},
        timeout=15,
    )
    assert result.returncode != 0 and result.stdout == ""
    assert "explicit trusted module:function" in result.stderr
    assert "PRIVATE-MARKER" not in result.stderr and report.read_text() == "previous evidence"
