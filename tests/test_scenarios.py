import json
from copy import deepcopy
from hashlib import sha256
from pathlib import Path

import pytest

from chaoslab.scenarios import export_inputs, score, score_bundle


def perfect(case):
    documents = {d["id"]: d for d in [case["input"]["rfp"], *case["input"]["knowledge"]]}

    def cite(id, quote):
        text = documents[id]["text"]
        start = text.index(quote)
        return {
            "document_id": id,
            "digest": sha256(text.encode()).hexdigest(),
            "start": start,
            "end": start + len(quote),
            "quote": quote,
        }

    items = []
    statuses = {
        "supported": "evidence_found",
        "contradicted": "conflicting_evidence",
        "insufficient": "missing_evidence",
    }
    for n, expected in enumerate(case["expected"]):
        evidence = [cite(id, documents[id]["text"]) for id in expected["evidence_ids"]]
        items.append(
            {
                "requirement": {
                    "id": f"r{n}",
                    "text": expected["text"],
                    "source": cite(case["input"]["rfp"]["id"], expected["text"]),
                },
                "status": statuses[expected["relation"]],
                "evidence": evidence,
                "review_state": "pending",
                "version": 1,
                "draft": "Evidence excerpts for human assessment:\n"
                + "\n".join(c["quote"] for c in evidence)
                if evidence
                else "No supporting evidence located. A reviewer must obtain evidence before responding.",
            }
        )
    return {"documents": deepcopy(list(documents.values())), "assessments": items}


def dataset():
    raw = Path("datasets/scenarios.json").read_bytes()
    return json.loads(raw), raw


def test_perfect_multi_record_contract_and_label_free_inputs():
    data, raw = dataset()
    manifest = export_inputs(data, raw)
    for case, row in zip(data["cases"], manifest["cases"], strict=True):
        assert score(case, perfect(case))["passed"]
        assert set(row["input"]) == {"rfp", "knowledge"}
        assert case["id"] not in row["id"]
        assert "expected" not in row["input"]
    report = score_bundle(
        data,
        raw,
        {
            "dataset_sha256": manifest["dataset_sha256"],
            "results": [
                {**row, "status": "succeeded", "output": perfect(case)}
                for case, row in zip(data["cases"], manifest["cases"], strict=True)
            ],
        },
    )
    assert report["requirements_passed"] == 9 and report["scenarios_passed"] == 3


@pytest.mark.parametrize(
    "mutation",
    [
        "omit",
        "duplicate",
        "missing_record",
        "approval",
        "draft",
        "span",
        "duplicate_id",
        "duplicate_evidence",
        "extra",
    ],
)
def test_scenario_judge_rejects_contract_mutations(mutation):
    case = dataset()[0]["cases"][2]
    output = perfect(case)
    item = output["assessments"][0]
    if mutation == "omit":
        output["assessments"].pop(0)
    elif mutation == "duplicate":
        output["assessments"].append(deepcopy(item))
    elif mutation == "missing_record":
        item["evidence"].pop()
    elif mutation == "approval":
        item["review_state"] = "approved"
    elif mutation == "draft":
        item["draft"] = "Guaranteed compliant"
    elif mutation == "span":
        item["evidence"][0]["start"] += 1
    elif mutation == "duplicate_id":
        output["assessments"][1]["requirement"]["id"] = item["requirement"]["id"]
    elif mutation == "duplicate_evidence":
        item["evidence"].append(deepcopy(item["evidence"][0]))
    else:
        extra = deepcopy(item)
        extra["requirement"]["text"] = "Invented obligation"
        output["assessments"].append(extra)
    assert not score(case, output)["passed"]


def test_scenario_bundle_rejects_source_drift_and_keeps_operational_failures():
    data, raw = dataset()
    manifest = export_inputs(data, raw)
    row = manifest["cases"][0]
    failed = score_bundle(
        data,
        raw,
        {"dataset_sha256": manifest["dataset_sha256"], "results": [{**row, "status": "failed"}]},
    )
    assert failed["requirements_evaluated"] == 3 and failed["requirements_passed"] == 0
    assert failed["not_run_scenarios"] == 2
    result = {**row, "status": "succeeded", "output": perfect(data["cases"][0])}
    result["output"]["documents"][0]["text"] += " changed"
    with pytest.raises(ValueError, match="snapshot"):
        score_bundle(data, raw, {"dataset_sha256": manifest["dataset_sha256"], "results": [result]})
