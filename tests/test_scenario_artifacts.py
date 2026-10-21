"""Malformed observations are invalid experiments; wrong answers remain failures."""

import json
from copy import deepcopy

import pytest
from test_comparison import fixtures

from chaoslab.comparison import compare, read_json
from chaoslab.scenarios import score_bundle


def malformed(bundle, mutation):
    if mutation == "array-root":
        return []
    if mutation == "missing-results":
        del bundle["results"]
        return bundle
    if mutation == "null-row":
        bundle["results"][0] = None
        return bundle
    row = bundle["results"][0]
    if mutation == "missing-input-hash":
        del row["input_sha256"]
    elif mutation == "unhashable-id":
        row["id"] = ["PRIVATE-SOURCE"]
    elif mutation == "missing-output":
        del row["output"]
    else:
        output = row["output"]
        if mutation == "null-documents":
            output["documents"] = None
        elif mutation == "null-document":
            output["documents"][0] = None
        elif mutation == "null-assessments":
            output["assessments"] = None
        elif mutation == "excess-assessments":
            output["assessments"] *= 1001
        elif mutation == "null-assessment":
            output["assessments"][0] = None
        else:
            item = output["assessments"][0]
            if mutation == "null-requirement":
                item["requirement"] = None
            elif mutation == "unhashable-requirement-id":
                item["requirement"]["id"] = {"PRIVATE-SOURCE": []}
            elif mutation == "missing-draft":
                del item["draft"]
            elif mutation == "null-evidence":
                item["evidence"] = None
            elif mutation == "excess-evidence":
                item["evidence"] *= 1001
            elif mutation == "null-citation":
                item["evidence"][0] = None
            elif mutation == "missing-source":
                del item["requirement"]["source"]
            elif mutation == "boolean-span":
                item["requirement"]["source"]["start"] = True
            else:
                raise AssertionError(mutation)
    return bundle


MUTATIONS = [
    "array-root",
    "missing-results",
    "null-row",
    "missing-input-hash",
    "unhashable-id",
    "missing-output",
    "null-documents",
    "null-document",
    "null-assessments",
    "excess-assessments",
    "null-assessment",
    "null-requirement",
    "unhashable-requirement-id",
    "missing-draft",
    "null-evidence",
    "excess-evidence",
    "null-citation",
    "missing-source",
    "boolean-span",
]


@pytest.mark.parametrize("mutation", MUTATIONS)
def test_malformed_observations_have_an_opaque_admission_error(mutation):
    dataset, raw, bundle = fixtures()
    broken = malformed(deepcopy(bundle), mutation)
    for evaluate in (
        lambda: compare(dataset, raw, bundle, broken),
        lambda: score_bundle(dataset, raw, broken),
    ):
        with pytest.raises(ValueError) as error:
            evaluate()
        assert "PRIVATE-SOURCE" not in str(error.value)


@pytest.mark.parametrize("mutation", MUTATIONS)
def test_cli_invalid_experiments_exit_two_and_preserve_the_previous_report(
    tmp_path, monkeypatch, capsys, mutation
):
    from chaoslab.comparison import main

    _, raw, bundle = fixtures()
    dataset, reference, candidate, output = [
        tmp_path / name
        for name in ("dataset.json", "reference.json", "candidate.json", "report.json")
    ]
    dataset.write_bytes(raw)
    reference.write_text(json.dumps(bundle))
    candidate.write_text(json.dumps(malformed(deepcopy(bundle), mutation)))
    output.write_bytes(b'{"previous":"measured evidence"}\n')
    monkeypatch.setattr(
        "sys.argv",
        [
            "chaoslab-compare",
            "--dataset",
            str(dataset),
            "--reference",
            str(reference),
            "--candidate",
            str(candidate),
            "--output",
            str(output),
        ],
    )
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2
    assert output.read_bytes() == b'{"previous":"measured evidence"}\n'
    assert "PRIVATE-SOURCE" not in capsys.readouterr().err


@pytest.mark.parametrize(
    "mutation", ["wrong-digest", "wrong-span", "unknown-relation", "approved-review", "omitted"]
)
def test_wrong_but_structurally_usable_answers_remain_scored_failures(mutation):
    dataset, raw, bundle = fixtures()
    candidate = deepcopy(bundle)
    item = candidate["results"][0]["output"]["assessments"][0]
    if mutation == "wrong-digest":
        item["evidence"][0]["digest"] = "wrong"
    elif mutation == "wrong-span":
        item["requirement"]["source"]["start"] = -1
    elif mutation == "unknown-relation":
        item["status"] = "unsupported-status"
    elif mutation == "approved-review":
        item["review_state"] = "approved"
    else:
        candidate["results"][0]["output"]["assessments"] = []
    report = compare(dataset, raw, bundle, candidate)
    assert not report["fixture_gate_passed"]
    assert report["scenario_transitions"]["regressed"] == 1


@pytest.mark.parametrize("body", [b'{"extra":1e9999}', b"[" * 2000 + b"]" * 2000, b"\xff"])
def test_overflow_nesting_and_encoding_refuse_cleanly(tmp_path, body):
    path = tmp_path / "invalid.json"
    path.write_bytes(body)
    with pytest.raises(ValueError):
        read_json(path)


def test_json_nesting_boundary_is_independent_of_python_recursion_limit(tmp_path):
    path = tmp_path / "nested.json"
    path.write_text("[" * 64 + "0" + "]" * 64)
    read_json(path)
    path.write_text("[" * 65 + "0" + "]" * 65)
    with pytest.raises(ValueError, match="nesting budget"):
        read_json(path)


@pytest.mark.parametrize("observed", [{}, {"assessments": [None]}])
def test_live_malformed_adapter_outputs_are_recorded_as_attempted_failures(
    tmp_path, monkeypatch, observed
):
    import chaoslab.scenarios as module

    output = tmp_path / "report.json"
    monkeypatch.setattr(module, "invoke", lambda *args: deepcopy(observed))
    monkeypatch.setattr(
        "sys.argv", ["scenarios", "--dataset", "datasets/scenarios.json", "--output", str(output)]
    )
    module.main()
    report = json.loads(output.read_text())
    assert report["evaluated_scenarios"] == 3
    assert report["not_run_scenarios"] == 0
    assert report["scenarios_passed"] == 0
    assert all(
        item["predicted"] == "error" for row in report["results"] for item in row["requirements"]
    )
