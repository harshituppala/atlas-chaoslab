"""A malformed golden contract must never become a passing agent result."""

import json
from copy import deepcopy
from pathlib import Path

import pytest
from test_scenarios import perfect

from chaoslab.comparison import compare
from chaoslab.datasets import validate_dataset
from chaoslab.scenarios import export_inputs, score


def dataset():
    return json.loads(Path("datasets/scenarios.json").read_bytes())


def test_unknown_golden_relation_cannot_validate_an_unknown_agent_state():
    case = dataset()["cases"][0]
    output = perfect(case)
    case["expected"][0]["relation"] = "invalid"
    output["assessments"][0]["status"] = "unrecognized_status"
    with pytest.raises(ValueError, match="expected relation"):
        score(case, output)


@pytest.mark.parametrize(
    "mutation",
    [
        "unknown_relation",
        "relation_list",
        "unknown_evidence",
        "rfp_as_evidence",
        "duplicate_evidence",
        "evidence_list_inside_list",
        "empty_support",
        "insufficient_with_evidence",
        "duplicate_document",
        "empty_document",
        "wrong_document_kind",
        "invalid_document",
        "knowledge_not_list",
        "quote_outside_rfp",
        "empty_expectations",
        "duplicate_obligation",
        "invalid_expectation",
        "invalid_identity",
        "duplicate_scenario",
        "empty_cases",
        "cases_not_list",
        "empty_scope",
        "boolean_schema",
    ],
)
def test_malformed_golden_contract_is_rejected_before_comparison(mutation):
    data = dataset()
    case, expectation = data["cases"][0], data["cases"][0]["expected"][0]
    if mutation == "unknown_relation":
        expectation["relation"] = "supportted"
    elif mutation == "relation_list":
        expectation["relation"] = ["supported"]
    elif mutation == "unknown_evidence":
        expectation["evidence_ids"] = ["not-in-source"]
    elif mutation == "rfp_as_evidence":
        expectation["evidence_ids"] = [case["input"]["rfp"]["id"]]
    elif mutation == "duplicate_evidence":
        expectation["evidence_ids"] *= 2
    elif mutation == "evidence_list_inside_list":
        expectation["evidence_ids"] = [["nested"]]
    elif mutation == "empty_support":
        expectation["evidence_ids"] = []
    elif mutation == "insufficient_with_evidence":
        expectation["relation"] = "insufficient"
    elif mutation == "duplicate_document":
        case["input"]["knowledge"][0]["id"] = case["input"]["rfp"]["id"]
    elif mutation == "empty_document":
        case["input"]["knowledge"][0]["text"] = ""
    elif mutation == "wrong_document_kind":
        case["input"]["knowledge"][0]["kind"] = "rfp"
    elif mutation == "invalid_document":
        case["input"]["rfp"] = None
    elif mutation == "knowledge_not_list":
        case["input"]["knowledge"] = {}
    elif mutation == "quote_outside_rfp":
        expectation["text"] = "PRIVATE-CONTENT-CANARY not in the RFP"
    elif mutation == "empty_expectations":
        case["expected"] = []
    elif mutation == "duplicate_obligation":
        case["expected"].append(deepcopy(expectation))
    elif mutation == "invalid_expectation":
        case["expected"][0] = None
    elif mutation == "invalid_identity":
        case["id"] = True
    elif mutation == "duplicate_scenario":
        data["cases"].append(deepcopy(case))
    elif mutation == "empty_cases":
        data["cases"] = []
    elif mutation == "cases_not_list":
        data["cases"] = {}
    elif mutation == "empty_scope":
        data["scope"] = ""
    else:
        data["schema_version"] = True
    raw = json.dumps(data).encode()
    with pytest.raises(ValueError) as caught:
        compare(data, raw, {}, {})
    assert "PRIVATE-CONTENT-CANARY" not in str(caught.value)


def test_input_export_cannot_bind_a_different_parsed_dataset():
    data = dataset()
    raw = json.dumps(data).encode()
    data["scope"] += " changed"
    with pytest.raises(ValueError, match="bound bytes"):
        export_inputs(data, raw)


def test_both_existing_scenario_contracts_remain_valid():
    for file in ("datasets/scenarios.json", "datasets/injection-pairs.json"):
        data = json.loads(Path(file).read_bytes())
        validate_dataset(data)
        manifest = export_inputs(data, Path(file).read_bytes())
        assert all("expected" not in row["input"] for row in manifest["cases"])


def test_invalid_contract_cli_returns_usage_error_without_replacing_report(
    tmp_path, monkeypatch, capsys
):
    import chaoslab.comparison as module

    data = dataset()
    data["cases"][0]["expected"][0]["relation"] = "invalid"
    source = tmp_path / "dataset.json"
    source.write_text(json.dumps(data))
    bundle = tmp_path / "bundle.json"
    bundle.write_text("{}")
    report = tmp_path / "report.json"
    report.write_text("previous measured report")
    monkeypatch.setattr(
        "sys.argv",
        [
            "comparison",
            "--dataset",
            str(source),
            "--reference",
            str(bundle),
            "--candidate",
            str(bundle),
            "--output",
            str(report),
        ],
    )
    with pytest.raises(SystemExit) as caught:
        module.main()
    assert caught.value.code == 2
    assert "Invalid expected relation" in capsys.readouterr().err
    assert report.read_text() == "previous measured report"
