"""Pair raw scenario outputs under one scorer; never compare incompatible aggregates."""

import argparse
import hashlib
import json
import math
from datetime import UTC, datetime
from pathlib import Path

from .artifacts import publish_report
from .datasets import validate_dataset
from .scenario_artifacts import validate_bundle
from .scenarios import export_inputs, score_bundle

MAX_BYTES = 8_000_000


def read_json(path):
    with Path(path).open("rb") as handle:
        raw = handle.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("Comparison artifact exceeds byte budget")

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result

    def invalid(_):
        raise ValueError("Non-finite JSON value")

    def finite(value):
        parsed = float(value)
        if not math.isfinite(parsed):
            raise ValueError("Non-finite JSON value")
        return parsed

    try:
        parsed = json.loads(
            raw, object_pairs_hook=unique, parse_constant=invalid, parse_float=finite
        )
        pending = [(parsed, 0)]
        while pending:
            value, depth = pending.pop()
            if depth > 64:
                raise ValueError("Comparison JSON exceeds nesting budget")
            if isinstance(value, dict):
                pending.extend((item, depth + 1) for item in value.values())
            elif isinstance(value, list):
                pending.extend((item, depth + 1) for item in value)
        return raw, parsed
    except (RecursionError, UnicodeError):
        raise ValueError("Comparison JSON encoding or nesting is invalid") from None


def normalized(dataset, raw, bundle):
    validate_bundle(bundle, len(dataset["cases"]))
    if bundle.get("dataset_sha256") != hashlib.sha256(raw).hexdigest():
        raise ValueError("Comparison dataset differs")
    rows = bundle["results"]
    if not isinstance(rows, list) or len(rows) > len(dataset["cases"]):
        raise ValueError("Invalid comparison result coverage")
    # Existing scorer binds IDs, input hashes, sources, exact citations, drafts and reviews.
    scored = score_bundle(dataset, raw, bundle)["results"] if rows else []
    names = {
        r["id"]: c["id"]
        for c, r in zip(dataset["cases"], export_inputs(dataset, raw)["cases"], strict=True)
    }
    statuses = {names[r["id"]]: r["status"] for r in rows}
    return {r["id"]: {**r, "execution_status": statuses[r["id"]]} for r in scored}


def matrix(pairs):
    counts = {"both_passed": 0, "both_failed": 0, "improved": 0, "regressed": 0, "unpaired": 0}
    for before, after in pairs:
        if before is None or after is None:
            key = "unpaired"
        elif before and after:
            key = "both_passed"
        elif not before and not after:
            key = "both_failed"
        else:
            key = "improved" if after else "regressed"
        counts[key] += 1
    return counts


def compare(dataset, raw, reference, candidate):
    if json.loads(raw) != dataset:
        raise ValueError("Parsed dataset differs from bound bytes")
    validate_dataset(dataset)
    before = normalized(dataset, raw, reference)
    after = normalized(dataset, raw, candidate)
    scenarios, requirements = [], []
    for case in dataset["cases"]:
        left, right = before.get(case["id"]), after.get(case["id"])
        pair = (left["passed"] if left else None, right["passed"] if right else None)
        rows = []
        for index, expected in enumerate(case["expected"]):
            first = left["requirements"][index] if left else None
            second = right["requirements"][index] if right else None
            requirement_pair = (
                first["passed"] if first else None,
                second["passed"] if second else None,
            )
            requirements.append(requirement_pair)
            rows.append(
                {
                    "obligation_index": index,
                    "obligation_sha256": hashlib.sha256(expected["text"].encode()).hexdigest(),
                    "reference_passed": requirement_pair[0],
                    "candidate_passed": requirement_pair[1],
                }
            )
        scenarios.append(
            {
                "id": case["id"],
                "reference_passed": pair[0],
                "candidate_passed": pair[1],
                "reference_execution": left["execution_status"] if left else "not_run",
                "candidate_execution": right["execution_status"] if right else "not_run",
                "requirements": rows,
            }
        )
    scenario_matrix = matrix([(s["reference_passed"], s["candidate_passed"]) for s in scenarios])
    requirement_matrix = matrix(requirements)
    failures = {
        side: sum(r["execution_status"] == "failed" for r in scored.values())
        for side, scored in (("reference", before), ("candidate", after))
    }
    full = len(before) == len(after) == len(scenarios)
    return {
        "schema_version": 1,
        "scope": "Descriptive paired rescoring of saved outputs, not new model inference or a production accuracy/significance claim. Strict outcomes count attempted execution failures as failures; missing attempts remain null/unpaired. Obligations within scenarios are correlated.",
        "dataset_sha256": hashlib.sha256(raw).hexdigest(),
        "planned_scenarios": len(scenarios),
        "planned_requirements": len(requirements),
        "coverage": {
            "reference_attempted": len(before),
            "candidate_attempted": len(after),
            "full_paired_coverage": full,
            "execution_failures": failures,
        },
        "scenario_transitions": scenario_matrix,
        "requirement_transitions": requirement_matrix,
        "fixture_gate_passed": full
        and not any(failures.values())
        and not scenario_matrix["regressed"]
        and not requirement_matrix["regressed"]
        and all(s["candidate_passed"] for s in scenarios),
        "gate_scope": "This authored fixture set only; no deployment, security, comparative latency/cost, blinded validation or broad model superiority decision.",
        "scenarios": scenarios,
    }


def scorer_hashes():
    return {
        name: hashlib.sha256((Path(__file__).parent / Path(name).name).read_bytes()).hexdigest()
        for name in (
            "src/chaoslab/comparison.py",
            "src/chaoslab/scenarios.py",
            "src/chaoslab/__main__.py",
            "src/chaoslab/datasets.py",
            "src/chaoslab/scenario_artifacts.py",
        )
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default="datasets/scenarios.json")
    parser.add_argument("--reference", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--require-fixture-gate", action="store_true")
    args = parser.parse_args()
    inputs = [Path(args.dataset), Path(args.reference), Path(args.candidate)]
    output = Path(args.output).resolve()
    if output in {p.resolve() for p in inputs}:
        parser.error("Comparison output must not overwrite an input")
    frozen = scorer_hashes()
    try:
        loaded = [read_json(p) for p in inputs]
        report = compare(loaded[0][1], loaded[0][0], loaded[1][1], loaded[2][1])
    except ValueError as exc:
        parser.error(str(exc))
    except OSError:
        parser.error("Could not read comparison input")
    if scorer_hashes() != frozen or any(
        p.read_bytes() != raw for p, (raw, _) in zip(inputs, loaded, strict=True)
    ):
        raise SystemExit("Comparison inputs/scorer changed; publication refused")
    report.update(
        {
            "recorded_at": datetime.now(UTC).isoformat(),
            "scorer_sha256": frozen,
            "input_sha256": {
                label: hashlib.sha256(raw).hexdigest()
                for label, (raw, _) in zip(
                    ("dataset", "reference", "candidate"), loaded, strict=True
                )
            },
            "provenance_scope": "Raw saved outputs rescored under the same current scorer. Hashes bound before and checked after comparison; not signed provider/loaded-code attestation. No original inference cost or timing is inferred.",
        }
    )
    publish_report(Path(args.output), report)
    print(
        json.dumps(
            {
                k: report[k]
                for k in ("scenario_transitions", "requirement_transitions", "fixture_gate_passed")
            }
        )
    )

    if args.require_fixture_gate and not report["fixture_gate_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
