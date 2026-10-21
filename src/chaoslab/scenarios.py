"""Independent multi-obligation/source contract diagnostics; exact evidence gates."""

import argparse
import hashlib
import json
from pathlib import Path

from .__main__ import citation_valid, source_digest
from .artifacts import publish_report
from .datasets import validate_case, validate_dataset
from .execution import invoke

RELATIONS = {
    "evidence_found": "supported",
    "conflicting_evidence": "contradicted",
    "missing_evidence": "insufficient",
}


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def export_inputs(dataset, raw):
    validate_dataset(dataset)
    if json.loads(raw) != dataset:
        raise ValueError("Parsed dataset differs from bound bytes")
    dataset_hash = hashlib.sha256(raw).hexdigest()
    return {
        "schema_version": 1,
        "dataset_sha256": dataset_hash,
        "cases": [
            {
                "id": hashlib.sha256((dataset_hash + ":" + c["id"]).encode()).hexdigest(),
                "input": c["input"],
                "input_sha256": digest(c["input"]),
            }
            for c in dataset["cases"]
        ],
    }


def score(case, output):
    validate_case(case)
    original = case["input"]
    documents = {d["id"]: d for d in [original["rfp"], *original["knowledge"]]}
    items = output["assessments"]
    identifiers = [a["requirement"]["id"] for a in items]
    unique_ids = len(identifiers) == len(set(identifiers))
    required = {r["text"] for r in case["expected"]}
    extras = sum(a["requirement"]["text"] not in required for a in items)
    results = []
    for expected in case["expected"]:
        matches = [a for a in items if a["requirement"]["text"] == expected["text"]]
        if len(matches) != 1:
            results.append(
                {
                    "expected": expected["relation"],
                    "predicted": "omitted" if not matches else "duplicate",
                    "passed": False,
                    "extracted": False,
                }
            )
            continue
        item = matches[0]
        evidence, source = item["evidence"], item["requirement"]["source"]
        predicted = RELATIONS.get(item["status"], "invalid")
        integrity = all(citation_valid(c, documents) for c in [source, *evidence])
        scope = (
            source["document_id"] == original["rfp"]["id"]
            and source["quote"] == expected["text"]
            and all(c["document_id"] in {d["id"] for d in original["knowledge"]} for c in evidence)
        )
        chosen = {c["document_id"] for c in evidence}
        # All authored supporting/contradicting records are required. Extra records fail.
        coverage = chosen == set(expected["evidence_ids"]) and all(
            c["quote"] == documents[c["document_id"]]["text"]
            for c in evidence
            if c["document_id"] in documents
        )
        unique_evidence = len(evidence) == len(
            {(c["document_id"], c["start"], c["end"]) for c in evidence}
        )
        pending = (
            item.get("review_state") == "pending"
            and type(item.get("version")) is int
            and item["version"] == 1
        )
        draft = (
            "Evidence excerpts for human assessment:\n" + "\n".join(c["quote"] for c in evidence)
            if evidence
            else "No supporting evidence located. A reviewer must obtain evidence before responding."
        )
        passed = all(
            (
                unique_ids,
                unique_evidence,
                predicted == expected["relation"],
                integrity,
                scope,
                coverage,
                pending,
                item["draft"] == draft,
            )
        )
        results.append(
            {
                "expected": expected["relation"],
                "predicted": predicted,
                "extracted": True,
                "citation_integrity": integrity,
                "source_scope": scope,
                "evidence_record_coverage": coverage,
                "pending_review": pending,
                "passed": passed,
            }
        )
    return {
        "id": case["id"],
        "unexpected_extractions": extras,
        "passed": not extras and all(r["passed"] for r in results),
        "requirements": results,
    }


def score_bundle(dataset, raw, bundle):
    exported = export_inputs(dataset, raw)
    if bundle.get("dataset_sha256") != exported["dataset_sha256"]:
        raise ValueError("Scenario artifact dataset differs")
    known = {
        row["id"]: (case, row)
        for case, row in zip(dataset["cases"], exported["cases"], strict=True)
    }
    seen, results = set(), []
    for row in bundle["results"]:
        if row["id"] in seen or row["id"] not in known:
            raise ValueError("Duplicate or unknown scenario")
        seen.add(row["id"])
        case, entry = known[row["id"]]
        if row["input_sha256"] != entry["input_sha256"]:
            raise ValueError("Scenario artifact input differs")
        if row["status"] == "succeeded":
            actual = row["output"]["documents"]
            expected = [entry["input"]["rfp"], *entry["input"]["knowledge"]]
            fields = ("id", "title", "text", "kind", "source_map")
            if [{k: d.get(k) for k in fields} for d in actual] != [
                {k: d.get(k) for k in fields} for d in expected
            ]:
                raise ValueError("Scenario source snapshot differs")
            results.append(score(case, row["output"]))
        elif row["status"] == "failed":
            results.append(
                {
                    "id": case["id"],
                    "passed": False,
                    "unexpected_extractions": 0,
                    "requirements": [
                        {
                            "expected": e["relation"],
                            "predicted": "error",
                            "extracted": False,
                            "passed": False,
                        }
                        for e in case["expected"]
                    ],
                }
            )
        else:
            raise ValueError("Unknown scenario execution status")
    if not results:
        raise ValueError("No evaluated scenarios")
    rows = [r for case in results for r in case["requirements"]]
    return {
        "schema_version": 1,
        "scope": dataset["scope"],
        "dataset_sha256": exported["dataset_sha256"],
        "planned_scenarios": len(known),
        "evaluated_scenarios": len(results),
        "not_run_scenarios": len(known) - len(results),
        "scenarios_passed": sum(r["passed"] for r in results),
        "requirements_evaluated": len(rows),
        "requirements_passed": sum(r["passed"] for r in rows),
        "results": results,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="datasets/scenarios.json")
    parser.add_argument("--output", default="reports/scenarios-baseline.json")
    parser.add_argument("--export-inputs")
    parser.add_argument("--artifact")
    args = parser.parse_args()
    raw = Path(args.dataset).read_bytes()
    dataset = json.loads(raw)
    frozen = source_digest()
    if args.export_inputs:
        destination = Path(args.export_inputs).resolve()
        if not destination.is_relative_to(Path("var").resolve()) or destination.exists():
            parser.error("Choose a new private input manifest under var/")
        publish_report(destination, export_inputs(dataset, raw))
        return
    if args.artifact:
        artifact_raw = Path(args.artifact).read_bytes()
        report = score_bundle(dataset, raw, json.loads(artifact_raw))
        report["artifact_sha256"] = hashlib.sha256(artifact_raw).hexdigest()
    else:
        manifest = export_inputs(dataset, raw)
        results = []
        for row in manifest["cases"]:
            try:
                observed = invoke("atlas.chaos_adapter:run", row["input"])
                observed["documents"] = [row["input"]["rfp"], *row["input"]["knowledge"]]
                results.append(
                    {
                        **row,
                        "status": "succeeded",
                        "output": observed,
                    }
                )
            except Exception:
                results.append({**row, "status": "failed"})
        report = score_bundle(
            dataset, raw, {"dataset_sha256": manifest["dataset_sha256"], "results": results}
        )
        report["adapter"] = "atlas.chaos_adapter:run"
    if source_digest() != frozen or Path(args.dataset).read_bytes() != raw:
        raise SystemExit("Source or dataset changed during evaluation")
    report["scoring_source_sha256"] = frozen
    publish_report(Path(args.output), report)
    print(
        json.dumps(
            {
                k: report[k]
                for k in (
                    "scenarios_passed",
                    "evaluated_scenarios",
                    "requirements_passed",
                    "requirements_evaluated",
                )
            }
        )
    )


if __name__ == "__main__":
    main()
