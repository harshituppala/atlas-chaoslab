"""Independent judge must catch plausible corrupt outputs, not just bad hashes."""

import copy
import json
from pathlib import Path

import pytest

from atlas.chaos_adapter import run
from chaoslab.__main__ import evaluate


@pytest.fixture
def scored():
    case = json.loads(Path("datasets/golden.json").read_text())["cases"][0]
    return case, run(case["input"])


@pytest.mark.parametrize(
    "mutation,check",
    [
        ("draft", "extractive_draft_binding"),
        ("approval", "human_review_pending"),
        ("wrong-source", "requirement_source_binding"),
        ("no-trace", "bounded_retrieval"),
        ("negative-attempts", "bounded_retrieval"),
        ("bool-attempts", "bounded_retrieval"),
        ("nan-time", "bounded_retrieval"),
        ("missing-validation", "bounded_retrieval"),
        ("missing-with-evidence", "evidence_gate"),
        ("self-evidence", "evidence_source_scope"),
    ],
)
def test_independent_judge_detects_contract_mutation(scored, mutation, check):
    case, original = scored
    assert evaluate(case, original)["passed"]
    output = copy.deepcopy(original)
    item = output["assessments"][0]
    if mutation == "draft":
        item["draft"] += "\nAll requirements are legally satisfied."
    elif mutation == "approval":
        item["review_state"] = "approved"
    elif mutation == "wrong-source":
        item["requirement"]["source"] = copy.deepcopy(item["evidence"][0])
    elif mutation == "self-evidence":
        item["evidence"] = [copy.deepcopy(item["requirement"]["source"])]
    elif mutation == "no-trace":
        output["trace"] = []
    elif mutation == "negative-attempts":
        output["trace"][1]["attempts"] = -1
    elif mutation == "bool-attempts":
        output["trace"][1]["attempts"] = True
    elif mutation == "nan-time":
        output["trace"][0]["duration_ms"] = float("nan")
    elif mutation == "missing-validation":
        output["trace"][2]["citations_valid"] = False
    elif mutation == "missing-with-evidence":
        item["status"] = "missing_evidence"
    scored = evaluate(case, output)
    assert not scored["passed"] and not scored["checks"][check]


def test_adversarial_blind_spots_remain_explicit():
    cases = json.loads(Path("datasets/adversarial.json").read_text())["cases"]
    outcomes = {case["id"]: evaluate(case, run(case["input"])) for case in cases}
    assert {name for name, result in outcomes.items() if not result["passed"]} == {
        "paraphrased-review-hijack",
        "zero-width-instruction",
        "benign-system-prompt-discussion",
    }
    # Valid offsets are insufficient to distinguish malicious evidence from benign discussion.
    assert all(result["checks"]["citation_integrity"] for result in outcomes.values())


def test_report_counts_all_repetitions_without_inflating_sample_size(scored, tmp_path, monkeypatch):
    from chaoslab import __main__ as runner

    case, output = scored
    dataset = tmp_path / "dataset.json"
    report = tmp_path / "report.json"
    dataset.write_text(json.dumps({"cases": [case]}))
    count = 0

    def adapter(*args, **kwargs):
        nonlocal count
        count += 1
        if count == 2:
            raise TimeoutError("private exception detail must not be recorded")
        return copy.deepcopy(output)

    monkeypatch.setattr(runner, "invoke", adapter)
    monkeypatch.setattr(
        "sys.argv",
        ["chaoslab", "--dataset", str(dataset), "--output", str(report), "--repeat", "2"],
    )
    runner.main()
    result = json.loads(report.read_text())
    assert result["unique_cases"] == 1 and result["case_pass_rate"] == 0
    assert result["repeat_inconsistent_cases"] == [case["id"]]
    assert result["case_outcomes"] == {case["id"]: False}
    assert result["external_model_cost_usd"] is None
    assert "private exception" not in report.read_text()


def test_report_refuses_changed_execution_source(scored, tmp_path, monkeypatch):
    from chaoslab import __main__ as runner

    case, output = scored
    dataset = tmp_path / "dataset.json"
    report = tmp_path / "report.json"
    dataset.write_text(json.dumps({"cases": [case]}))
    hashes = iter(["source-before", "source-after"])
    monkeypatch.setattr(runner, "source_digest", lambda: next(hashes))
    monkeypatch.setattr(runner, "invoke", lambda *args, **kwargs: copy.deepcopy(output))
    monkeypatch.setattr(
        "sys.argv",
        ["chaoslab", "--dataset", str(dataset), "--output", str(report), "--repeat", "1"],
    )
    with pytest.raises(SystemExit, match="changed during execution"):
        runner.main()
    assert not report.exists()


def test_report_without_git_preserves_source_identity(scored, tmp_path, monkeypatch):
    from chaoslab import __main__ as runner

    case, output = scored
    dataset, report = tmp_path / "dataset.json", tmp_path / "report.json"
    dataset.write_text(json.dumps({"cases": [case]}))

    def unavailable(*args, **kwargs):
        raise FileNotFoundError("git")

    monkeypatch.setattr(runner.subprocess, "check_output", unavailable)
    monkeypatch.setattr(runner, "invoke", lambda *args, **kwargs: copy.deepcopy(output))
    monkeypatch.setattr(
        "sys.argv",
        ["chaoslab", "--dataset", str(dataset), "--output", str(report), "--repeat", "1"],
    )
    runner.main()
    result = json.loads(report.read_text())
    assert result["revision"] is None and result["working_tree_dirty"] is None
    assert result["source_sha256"] == runner.source_digest()


def test_public_report_excludes_arbitrary_adapter_trace_fields(scored, tmp_path, monkeypatch):
    from chaoslab import __main__ as runner

    case, output = scored
    for entry in output["trace"]:
        entry["prompt"] = "PRIVATE-SOURCE-CANARY"
    output["trace"][2]["count"] = "PRIVATE-SOURCE-CANARY"
    output["pipeline_version"] = "PRIVATE-SOURCE-CANARY"
    output["external_model_cost_usd"] = -10
    dataset = tmp_path / "dataset.json"
    report = tmp_path / "report.json"
    dataset.write_text(json.dumps({"cases": [case]}))
    monkeypatch.setattr(runner, "invoke", lambda *args, **kwargs: copy.deepcopy(output))
    monkeypatch.setattr(
        "sys.argv",
        ["chaoslab", "--dataset", str(dataset), "--output", str(report), "--repeat", "1"],
    )
    runner.main()
    result = json.loads(report.read_text())
    assert "PRIVATE-SOURCE-CANARY" not in report.read_text()
    assert result["external_model_cost_usd"] is None
    assert result["results"][0]["pipeline_version"] is None


def test_empty_quality_denominators_remain_unknown(tmp_path, monkeypatch):
    from chaoslab import __main__ as runner

    case = {
        "id": "no-mandatory-control",
        "input": {
            "rfp": {
                "id": "r",
                "title": "r",
                "kind": "rfp",
                "text": "An optional feature would be useful.",
            },
            "knowledge": [
                {
                    "id": "k",
                    "title": "k",
                    "kind": "knowledge",
                    "text": "A general capability register.",
                }
            ],
        },
        "expected": [],
    }
    output = run(case["input"])
    dataset = tmp_path / "dataset.json"
    report = tmp_path / "report.json"
    dataset.write_text(json.dumps({"cases": [case]}))
    monkeypatch.setattr(runner, "invoke", lambda *args, **kwargs: copy.deepcopy(output))
    monkeypatch.setattr(
        "sys.argv",
        ["chaoslab", "--dataset", str(dataset), "--output", str(report), "--repeat", "1"],
    )
    runner.main()
    result = json.loads(report.read_text())
    assert result["case_pass_rate"] == 1
    assert all(
        result[name] is None
        for name in [
            "extraction_precision",
            "extraction_recall",
            "assessment_accuracy",
            "citation_integrity",
        ]
    )
