import json
from copy import deepcopy
from pathlib import Path

import pytest
from test_scenarios import perfect

from chaoslab.injection import evaluate, validate_pairs
from chaoslab.scenarios import export_inputs


def bundle():
    raw = Path("datasets/injection-pairs.json").read_bytes()
    data = json.loads(raw)
    inputs = export_inputs(data, raw)
    output = {
        "dataset_sha256": inputs["dataset_sha256"],
        "results": [
            {**row, "status": "succeeded", "output": perfect(case)}
            for case, row in zip(data["cases"], inputs["cases"], strict=True)
        ],
    }
    return data, raw, output


def test_perfect_pairs_have_no_contamination_or_regressions():
    data, raw, output = bundle()
    report = evaluate(data, raw, output)
    assert report["scenarios_passed"] == 12
    assert report["paired"]["evaluated_pairs"] == 6
    assert report["paired"]["control_passed_complete_pairs"] == 6
    assert report["paired"]["conditional_strict_regression_rate"] == 0
    assert report["paired"]["attack_cases_with_forbidden_source_citation"] == 0
    # Neither the pair labels nor expected facts are forwarded to the adapter.
    for row in export_inputs(data, raw)["cases"]:
        assert set(row["input"]) == {"rfp", "knowledge"}
        assert set(row) == {"id", "input", "input_sha256"}


def test_valid_but_hostile_citation_is_contamination_not_integrity_failure():
    data, raw, output = bundle()
    item = output["results"][1]["output"]["assessments"][0]
    malicious = deepcopy(data["cases"][1])
    malicious["expected"][0]["evidence_ids"] = ["record-b"]
    forged = perfect(malicious)["assessments"][0]
    item["evidence"], item["draft"] = forged["evidence"], forged["draft"]
    report = evaluate(data, raw, output)
    assert report["results"][1]["requirements"][0]["citation_integrity"]
    assert not report["results"][1]["passed"]
    assert report["paired"]["attack_cases_with_forbidden_source_citation"] == 1
    assert report["paired"]["strict_pair_regressions"] == 1


def test_auto_approval_is_counted_separately_from_source_selection():
    data, raw, output = bundle()
    output["results"][1]["output"]["assessments"][0]["review_state"] = "approved"
    report = evaluate(data, raw, output)
    assert report["paired"]["attack_cases_with_unauthorized_review_state"] == 1
    assert report["paired"]["attack_cases_with_forbidden_source_citation"] == 0


def test_incomplete_pairs_have_unknown_conditional_rate():
    data, raw, output = bundle()
    output["results"] = output["results"][::2]
    report = evaluate(data, raw, output)
    assert report["not_run_scenarios"] == 6
    assert report["paired"]["evaluated_pairs"] == 0
    assert report["paired"]["conditional_strict_regression_rate"] is None


def test_failed_attack_is_regression_without_invented_contamination():
    data, raw, output = bundle()
    output["results"][1] = {k: v for k, v in output["results"][1].items() if k != "output"}
    output["results"][1]["status"] = "failed"
    report = evaluate(data, raw, output)
    assert report["paired"]["strict_pair_regressions"] == 1
    assert report["paired"]["attack_cases_with_forbidden_source_citation"] == 0


@pytest.mark.parametrize(
    "change",
    ["duplicate", "missing", "rfp", "fact", "expectation", "forbidden", "metadata", "case_id"],
)
def test_invalid_pair_contract_refused(change):
    data, _, _ = bundle()
    if change == "duplicate":
        data["cases"].append(deepcopy(data["cases"][0]))
    elif change == "missing":
        data["cases"].pop(1)
    elif change == "rfp":
        data["cases"][1]["input"]["rfp"]["text"] += " Changed."
    elif change == "fact":
        data["cases"][1]["input"]["knowledge"][0]["text"] += " Changed."
    elif change == "expectation":
        data["cases"][1]["expected"][0]["relation"] = "insufficient"
    elif change == "metadata":
        data["cases"][1]["input"]["knowledge"][-1]["title"] = "Different authority"
    elif change == "case_id":
        data["cases"][2]["id"] = data["cases"][0]["id"]
    else:
        data["cases"][1]["forbidden_citations"] = ["unknown"]
    with pytest.raises(ValueError):
        validate_pairs(data)
