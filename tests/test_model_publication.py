from copy import deepcopy

import pytest

from atlas.execution import execute, prepare_model_publication, validate_publication
from atlas.models.intelligence import MODEL_PIPELINE_VERSION


@pytest.fixture
def publication():
    body = {
        "rfp": {
            "id": "r",
            "title": "RFP",
            "kind": "rfp",
            "text": "The platform must support SAML federation.",
        },
        "knowledge": [
            {
                "id": "k",
                "title": "Policy",
                "kind": "knowledge",
                "text": "The platform supports SAML federation.",
            }
        ],
    }
    baseline = execute(body)
    report = deepcopy(baseline)
    report.update(pipeline_version=MODEL_PIPELINE_VERSION, live_model=True)
    report["provisional_relations"] = {
        a["requirement"]["id"]: "supported" for a in report["assessments"]
    }
    return body, report


def test_model_publication_preserves_unknown_cost_and_keeps_baseline_gate(publication):
    body, report = publication
    result = prepare_model_publication(body, report, estimated_cost_usd=None)
    assert result["model_cost_usd"] is None
    assert result["assessments"][0]["review_state"] == "pending"
    with pytest.raises(ValueError):
        validate_publication(body, result)


@pytest.mark.parametrize(
    "attack",
    [
        "approve",
        "draft",
        "source",
        "relation",
        "missing_relation",
        "evidence",
        "duplicate",
        "version",
    ],
)
def test_model_publication_rejects_forged_results(publication, attack):
    body, report = publication
    item = report["assessments"][0]
    if attack == "approve":
        item["review_state"] = "approved"
    elif attack == "draft":
        item["draft"] = "Guaranteed compliant"
    elif attack == "source":
        report["documents"][0]["text"] += " forged"
    elif attack == "relation":
        report["provisional_relations"][item["requirement"]["id"]] = "insufficient"
    elif attack == "missing_relation":
        report["provisional_relations"] = {}
    elif attack == "evidence":
        item["evidence"][0]["quote"] = "forged"
    elif attack == "duplicate":
        report["assessments"].append(deepcopy(item))
    elif attack == "version":
        report["pipeline_version"] = "unapproved-model"
    with pytest.raises(ValueError):
        prepare_model_publication(body, report, estimated_cost_usd="0.01")


@pytest.mark.parametrize("cost", [-1, float("nan"), float("inf")])
def test_model_publication_rejects_invalid_cost(publication, cost):
    with pytest.raises(ValueError):
        prepare_model_publication(*publication, estimated_cost_usd=cost)
