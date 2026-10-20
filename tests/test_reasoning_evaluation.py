"""Authored semantic labels and deliberately corrupted outputs test the independent judge."""

import copy
import hashlib
import json
from pathlib import Path

import pytest

from atlas.chaos_adapter import run
from chaoslab.reasoning import inputs, score, summarize


def cases():
    return json.loads(Path("datasets/reasoning.json").read_text())["cases"]


def test_authored_reasoning_labels_keep_known_baseline_failures_visible():
    observed = [
        {"id": case["id"], "expected": case["relation"], **score(case, run(inputs(case)))}
        for case in cases()
    ]
    failed = {row["id"] for row in observed if not row["passed"]}
    assert failed == {
        "residency-conflict",
        "residency-backup-exception",
        "residency-partial",
        "recovery-aspiration",
        "retention-short",
        "saml-unrelated-negation",
        "encryption-partial",
        "paraphrased-obligation",
    }
    summary = summarize(observed)
    assert summary["cases"] == 18 and summary["cases_passed"] == 10
    assert summary["supported_precision"] == 0.5
    assert summary["insufficient_recall"] == 0.25
    assert summary["confusion_matrix"]["supported"]["omitted"] == 1
    assert sum(sum(row.values()) for row in summary["confusion_matrix"].values()) == 18


@pytest.mark.parametrize(
    "mutation",
    [
        "forged-hash",
        "foreign-source",
        "self-evidence",
        "approved",
        "unsupported-draft",
        "duplicate-extraction",
        "missing-extraction",
    ],
)
def test_matching_relation_does_not_hide_contract_failures(mutation):
    case = cases()[0]
    output = run(inputs(case))
    assert score(case, output)["passed"]
    changed = copy.deepcopy(output)
    item = changed["assessments"][0]
    if mutation == "forged-hash":
        item["evidence"][0]["digest"] = "0" * 64
    elif mutation == "foreign-source":
        item["evidence"][0]["document_id"] = "foreign-tenant"
    elif mutation == "self-evidence":
        item["evidence"] = [copy.deepcopy(item["requirement"]["source"])]
    elif mutation == "approved":
        item["review_state"] = "approved"
    elif mutation == "unsupported-draft":
        item["draft"] += " All contractual conditions have been satisfied."
    elif mutation == "duplicate-extraction":
        changed["assessments"].append(copy.deepcopy(item))
    else:
        changed["assessments"] = []
    result = score(case, changed)
    assert not result["passed"]
    if mutation == "duplicate-extraction":
        assert result["predicted"] == "invalid_extraction"
    if mutation == "missing-extraction":
        assert result["predicted"] == "omitted"


def test_accurate_substring_is_not_complete_reference_evidence():
    case = {
        "id": "subspan",
        "requirement": "Customer data and backups must remain in Canada.",
        "evidence": "Customer data remains in Canada. Backups are outside Canada.",
        "relation": "contradicted",
    }
    output = run(inputs(case))
    citation = output["assessments"][0]["evidence"][0]
    quote = "Customer data remains in Canada."
    citation.update(
        start=0,
        end=len(quote),
        quote=quote,
        digest=hashlib.sha256(case["evidence"].encode()).hexdigest(),
    )
    result = score(case, output)
    assert result["citation_integrity"] and not result["complete_reference"]


def test_no_extraction_does_not_become_successful_insufficient_prediction():
    case = next(case for case in cases() if case["relation"] == "insufficient")
    result = {"expected": "insufficient", **score(case, {"assessments": []})}
    summary = summarize([result])
    assert summary["extraction_coverage"] == 0
    assert summary["insufficient_recall"] == 0
    assert summary["relation_accuracy_given_extraction"] is None
    assert summary["supported_precision"] is None
