import copy
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from chaoslab.qa import answer_scores, compare, questions

EXAMPLE = Path("examples/reading-qa")


def inputs():
    return [
        json.loads((EXAMPLE / (p + ".json")).read_text())
        for p in ["dataset", "reference", "reference", "reference-citations", "reference-citations"]
    ]


def test_reading_answers_and_source_integrity_are_distinct():
    data, reference, candidate, left, right = inputs()
    assert compare(data, reference, candidate, left, right)["fixture_gate_passed"]
    candidate["limit"] = "three"
    right["limit"] = {"start": 0, "end": 3, "sha256": "invalid"}
    result = compare(data, reference, candidate, left, right)
    assert result["candidate"]["exact"] == 0.75
    assert result["transitions"]["regressed"] == ["limit"]
    # A correct answer with the wrong source still fails the optional citation gate.
    candidate["limit"] = "two"
    result = compare(data, reference, candidate, left, right)
    assert result["candidate"]["exact"] == 1
    assert not result["candidate"]["rows"]["limit"]["citation_valid"]
    assert result["transitions"]["regressed"] == ["limit"]


def test_missing_abstention_is_not_a_correct_empty_answer():
    data, reference, candidate, *_ = inputs()
    del candidate["parking"]
    result = compare(data, reference, candidate)
    assert result["candidate"]["missing"] == 1
    assert result["candidate"]["exact"] == 0.75
    assert result["candidate"]["citation_validity"] is None
    assert result["transitions"]["unpaired"] == ["parking"]
    assert not result["fixture_gate_passed"]


def test_normalized_overlap_and_multiple_references():
    assert answer_scores("The RED box!", ["red box", "crate"]) == (1, 1)
    assert answer_scores("red", ["red box"]) == (0, 2 / 3)
    assert answer_scores("", [""]) == (1, 1)


@pytest.mark.parametrize(
    "mutation",
    [
        "duplicate",
        "wrong-span",
        "wrong-answerability",
        "unknown-prediction",
        "boolean-offset",
        "one-sided-citations",
    ],
)
def test_invalid_experiments_are_not_quality_failures(mutation):
    data, reference, candidate, left, right = inputs()
    if mutation == "duplicate":
        data["data"][0]["paragraphs"][0]["qas"].append(
            copy.deepcopy(data["data"][0]["paragraphs"][0]["qas"][0])
        )
    elif mutation == "wrong-span":
        data["data"][0]["paragraphs"][0]["qas"][0]["answers"][0]["answer_start"] = 0
    elif mutation == "wrong-answerability":
        data["data"][0]["paragraphs"][0]["qas"][0]["is_impossible"] = True
    elif mutation == "unknown-prediction":
        candidate["unknown"] = "answer"
    elif mutation == "boolean-offset":
        right["opening"]["start"] = True
    else:
        right = None
    with pytest.raises(ValueError):
        compare(data, reference, candidate, left, right)


def test_cli_writes_quality_failure_and_preserves_report_on_invalid_input(tmp_path):
    output = tmp_path / "report.json"
    args = [
        sys.executable,
        "-m",
        "chaoslab.qa",
        "--dataset",
        str(EXAMPLE / "dataset.json"),
        "--reference",
        str(EXAMPLE / "reference.json"),
        "--candidate",
        str(EXAMPLE / "wrong-answer.json"),
        "--output",
        str(output),
        "--require-fixture-gate",
    ]
    assert (
        subprocess.run(
            args,
            env={"PATH": os.defpath, "PYTHONPATH": str(Path("src").resolve())},
            capture_output=True,
        ).returncode
        == 1
    )
    raw = output.read_bytes()
    candidate = tmp_path / "invalid.json"
    candidate.write_text('{"opening":"09:00","opening":"wrong"}')
    args[args.index("--candidate") + 1] = str(candidate)
    assert (
        subprocess.run(
            args,
            env={"PATH": os.defpath, "PYTHONPATH": str(Path("src").resolve())},
            capture_output=True,
        ).returncode
        == 2
    )
    assert output.read_bytes() == raw


def test_question_budget():
    data = inputs()[0]
    paragraph = data["data"][0]["paragraphs"][0]
    template = paragraph["qas"][0]
    paragraph["qas"] = [{**template, "id": str(i)} for i in range(1001)]
    with pytest.raises(ValueError, match="Question budget"):
        questions(data)


def test_wrong_answer_can_have_a_valid_context_citation():
    data, reference, candidate, left, right = inputs()
    context = data["data"][0]["paragraphs"][0]["context"]
    candidate["opening"] = "two"
    start = context.index("two")
    right["opening"] = {**right["opening"], "start": start, "end": start + 3}
    result = compare(data, reference, candidate, left, right)
    row = result["candidate"]["rows"]["opening"]
    assert row["citation_valid"] is True and row["exact"] == 0 and not row["passed"]
    assert result["transitions"]["regressed"] == ["opening"]
