"""Independent factual-relation scoring with extraction omissions kept distinct.

The adapter returns the ordinary JSON assessment contract. This judge checks
labels, exact provenance and evidence selection; it cannot infer faithfulness
for arbitrary generated claims. Labels are authored outside ATLAS.
"""

import argparse
import hashlib
import json
import platform
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from .__main__ import citation_valid, source_digest
from .artifacts import publish_report
from .execution import invoke

RELATIONS = ("supported", "contradicted", "insufficient")
STATUS = {
    "evidence_found": "supported",
    "conflicting_evidence": "contradicted",
    "missing_evidence": "insufficient",
}


def inputs(case):
    return {
        "rfp": {
            "id": "obligation",
            "title": "Synthetic obligation",
            "kind": "rfp",
            "text": case["requirement"],
        },
        "knowledge": [
            {
                "id": "evidence",
                "title": "Synthetic capability",
                "kind": "knowledge",
                "text": case["evidence"],
            }
        ],
    }


def score(case, output):
    documents = {d["id"]: d for d in [inputs(case)["rfp"], *inputs(case)["knowledge"]]}
    assessments = output["assessments"]
    # Missing extraction is not a successful abstention.
    extracted = (
        len(assessments) == 1 and assessments[0]["requirement"]["text"] == case["requirement"]
    )
    if not extracted:
        return {
            "extracted": False,
            "predicted": "omitted" if not assessments else "invalid_extraction",
            "relation_correct": False,
            "citation_integrity": None,
            "source_scope": None,
            "evidence_gate": None,
            "passed": False,
        }
    item = assessments[0]
    source, evidence = item["requirement"]["source"], item["evidence"]
    citations = [source, *evidence]
    integrity = all(citation_valid(c, documents) for c in citations)
    scope = (
        source["document_id"] == "obligation"
        and source["quote"] == case["requirement"]
        and all(c["document_id"] == "evidence" for c in evidence)
    )
    predicted = STATUS.get(item["status"], "invalid")
    evidence_gate = (predicted == "insufficient" and not evidence) or (
        predicted in {"supported", "contradicted"} and bool(evidence)
    )
    # Positive relations must cite the complete authored capability record. This
    # conservative contract prevents scoring an unrelated fragment as faithful.
    complete = predicted == "insufficient" or any(c["quote"] == case["evidence"] for c in evidence)
    correct = predicted == case["relation"]
    human_pending = (
        item.get("review_state") == "pending"
        and type(item.get("version")) is int
        and item["version"] == 1
    )
    expected_draft = (
        "Evidence excerpts for human assessment:\n" + "\n".join(c["quote"] for c in evidence)
        if evidence
        else "No supporting evidence located. A reviewer must obtain evidence before responding."
    )
    extractive = item.get("draft") == expected_draft
    return {
        "extracted": True,
        "predicted": predicted,
        "relation_correct": correct,
        "citation_integrity": integrity,
        "source_scope": scope,
        "evidence_gate": bool(evidence_gate),
        "complete_reference": complete,
        "human_review_pending": human_pending,
        "extractive_draft": extractive,
        "passed": all(
            (correct, integrity, scope, evidence_gate, complete, human_pending, extractive)
        ),
    }


def summarize(results):
    matrix = {
        label: {
            prediction: 0
            for prediction in (*RELATIONS, "omitted", "invalid_extraction", "invalid", "error")
        }
        for label in RELATIONS
    }
    for row in results:
        matrix[row["expected"]][row["predicted"]] += 1
    extracted = sum(row["extracted"] for row in results)
    correct = sum(row["relation_correct"] for row in results)
    predicted_support = [row for row in results if row["predicted"] == "supported"]
    insufficient = [row for row in results if row["expected"] == "insufficient"]
    return {
        "cases": len(results),
        "cases_passed": sum(row["passed"] for row in results),
        "grounded_contract_pass_rate": sum(row["passed"] for row in results) / len(results),
        "extraction_coverage": extracted / len(results),
        "end_to_end_relation_accuracy": correct / len(results),
        "relation_accuracy_given_extraction": correct / extracted if extracted else None,
        "supported_precision": sum(row["expected"] == "supported" for row in predicted_support)
        / len(predicted_support)
        if predicted_support
        else None,
        "insufficient_recall": sum(row["predicted"] == "insufficient" for row in insufficient)
        / len(insufficient)
        if insufficient
        else None,
        "confusion_matrix": matrix,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="datasets/reasoning.json")
    parser.add_argument("--adapter", default="atlas.chaos_adapter:run")
    parser.add_argument("--output", default="reports/reasoning.json")
    parser.add_argument("--export-inputs")
    parser.add_argument("--artifacts")
    args = parser.parse_args()
    raw = Path(args.dataset).read_bytes()
    dataset = json.loads(raw)
    cases = dataset["cases"]
    if (
        not 1 <= len(cases) <= 200
        or len({case["id"] for case in cases}) != len(cases)
        or any(case["relation"] not in RELATIONS for case in cases)
    ):
        parser.error("Expected 1..200 distinctly identified cases with valid relation labels")
    if args.export_inputs or args.artifacts:
        if args.export_inputs and args.artifacts:
            parser.error("Choose input export or artifact scoring")
        destination = Path(args.export_inputs or args.output).resolve()
        if not destination.is_relative_to(Path("var").resolve()):
            parser.error("Provider artifacts and scores must remain under ignored var/")
        if destination.exists():
            parser.error("Preserve existing artifacts; choose a new output")
        if args.export_inputs:
            report = export_manifest(dataset, raw)
        else:
            artifact_path = Path(args.artifacts)
            artifact_raw = artifact_path.read_bytes()
            if len(artifact_raw) > 8_000_000:
                parser.error("Artifact byte budget exceeded")
            report = score_artifact(dataset, raw, json.loads(artifact_raw))
            report["artifact_sha256"] = hashlib.sha256(artifact_raw).hexdigest()
        publish_report(destination, report)
        print(
            json.dumps(
                {"artifact": str(destination), "mode": "export" if args.export_inputs else "score"}
            )
        )
        return
    frozen = source_digest()
    started = datetime.now(UTC).isoformat()
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], text=True).strip())
    results = []
    for case in cases:
        try:
            observed = score(case, invoke(args.adapter, inputs(case)))
        except Exception as exc:
            observed = {
                "extracted": False,
                "predicted": "error",
                "relation_correct": False,
                "passed": False,
                "error_type": type(exc).__name__,
            }
        results.append({"id": case["id"], "expected": case["relation"], **observed})
    if frozen != source_digest() or raw != Path(args.dataset).read_bytes():
        raise SystemExit("Source or dataset changed; report publication refused")
    report = {
        "schema_version": 1,
        "kind": "reasoning_quality",
        "scope": dataset["scope"],
        "adapter": args.adapter,
        "adapter_scope": "Deterministic lexical baseline; not live LLM quality."
        if args.adapter == "atlas.chaos_adapter:run"
        else "External adapter; live provider identity and usage need independent verification.",
        "started_at": started,
        "generated_at": datetime.now(UTC).isoformat(),
        "source_sha256": frozen,
        "dataset_sha256": hashlib.sha256(raw).hexdigest(),
        "revision": revision,
        "working_tree_dirty": dirty,
        "python": platform.python_version(),
        "environment": platform.platform(),
        "summary": summarize(results),
        "results": results,
        "reference_scope": "Whole capability record required for supported/contradicted evidence. Exact source identity and an authored relation label do not certify arbitrary claim-level faithfulness.",
        "execution_scope": "Trusted adapter subprocesses under the standard ten-second/byte budgets. No labels are passed to the adapter. Costs are not independently verified by this judge.",
    }
    publish_report(Path(args.output), report)
    print(json.dumps(report["summary"], indent=2))


def input_digest(body):
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def export_manifest(dataset, raw):
    dataset_hash = hashlib.sha256(raw).hexdigest()
    return {
        "schema_version": 1,
        "dataset_sha256": dataset_hash,
        "cases": [
            {
                "id": hashlib.sha256((dataset_hash + ":" + case["id"]).encode()).hexdigest(),
                "input": inputs(case),
                "input_sha256": input_digest(inputs(case)),
            }
            for case in dataset["cases"]
        ],
    }


def score_artifact(dataset, raw, bundle):
    expected = export_manifest(dataset, raw)
    if bundle.get("dataset_sha256") != expected["dataset_sha256"]:
        raise ValueError("Artifact dataset identity differs")
    known = {
        entry["id"]: (case, entry)
        for case, entry in zip(dataset["cases"], expected["cases"], strict=True)
    }
    results, seen = [], set()
    for row in bundle["results"]:
        identifier = row["id"]
        if identifier in seen or identifier not in known:
            raise ValueError("Duplicate or unknown artifact case")
        seen.add(identifier)
        case, entry = known[identifier]
        if row.get("input_sha256") != entry["input_sha256"]:
            raise ValueError("Artifact input identity differs")
        if row["status"] == "succeeded":
            output = row["output"]
            originals = [entry["input"]["rfp"], *entry["input"]["knowledge"]]
            fields = ("id", "title", "kind", "text", "source_map")
            if [{key: doc.get(key) for key in fields} for doc in output["documents"]] != [
                {key: doc.get(key) for key in fields} for doc in originals
            ]:
                raise ValueError("Artifact source snapshot differs")
            observed = score(case, output)
        elif row["status"] == "failed":
            observed = {
                "extracted": False,
                "predicted": "error",
                "relation_correct": False,
                "passed": False,
            }
        else:
            raise ValueError("Unknown artifact case status")
        results.append({"id": case["id"], "expected": case["relation"], **observed})
    if not results:
        raise ValueError("No evaluated cases; model quality is unmeasured")
    return {
        "schema_version": 1,
        "kind": "reasoning_quality",
        "scope": dataset["scope"],
        "adapter_scope": "Private provider artifact scoring; provider usage is reported, not an invoice or signed execution attestation.",
        "dataset_sha256": expected["dataset_sha256"],
        "planned_cases": len(known),
        "evaluated_cases": len(results),
        "not_run_cases": len(known) - len(results),
        "summary": summarize(results),
        "results": results,
    }


if __name__ == "__main__":
    main()
