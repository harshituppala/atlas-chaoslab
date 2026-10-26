"""Export a complete frozen test run only after independent score and receipt checks."""

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from record_contract_model import private_run, usage_summary

from atlas.models.contract_evaluation import ADAPTER
from atlas.models.provenance import source_manifest
from chaoslab.__main__ import source_digest
from chaoslab.artifacts import publish_report
from chaoslab.contract_holdout import POLICY, TASK, check_protocol, load_test, replay_result
from chaoslab.contract_journal import read_observations
from chaoslab.contractnli import adapter_input, always_not_mentioned, evaluate


def build_report(run, run_sha256, data, provenance, protocol, fingerprint, observations):
    source = source_manifest()["source_sha256"]
    recipe = protocol["recipe"]
    if (
        run.get("status") != "complete"
        or run.get("live_model") is not True
        or run.get("task") != TASK
        or run.get("protocol_sha256") != fingerprint
        or run.get("dataset") != provenance
        or run.get("adapter") != ADAPTER
        or run.get("scorer_sha256") != source_digest()
        or run.get("source_manifest", {}).get("source_sha256") != source
        or recipe["execution_source_sha256"] != source
        or "continuation" in run
    ):
        raise ValueError("A complete unchanged frozen test run is required")
    header, _, _ = read_observations(
        observations,
        dataset=provenance,
        inputs={d["id"]: adapter_input(d, data["labels"], task=TASK) for d in data["documents"]},
        task=TASK,
    )
    if header["adapter"] != ADAPTER or header["scorer_sha256"] != run["scorer_sha256"]:
        raise ValueError("Journal execution identity differs")
    result, receipt = replay_result(data, provenance, observations, task=TASK)
    if result != run["results"] or receipt != run["observations"]:
        raise ValueError("Independent replay differs from run evidence")
    usage = usage_summary(run["usage"], len(data["documents"]))
    if (usage["model_id"], usage["region"]) != (recipe["model_id"], recipe["region"]) or any(
        r["reserved_input_tokens"] != recipe["max_input_tokens"]
        or r["reserved_output_tokens"] != recipe["max_output_tokens"]
        for r in run["usage"]["receipts"]
    ):
        raise ValueError("Receipt identity or limits differ from frozen recipe")
    reference = evaluate(
        data,
        "chaoslab.contractnli:always_not_mentioned",
        invoke_adapter=lambda _, body: always_not_mentioned(body),
        task=TASK,
    )
    return {
        "recorded_at": datetime.now(UTC).isoformat(),
        "task": TASK,
        "source": "https://stanfordnlp.github.io/contract-nli/",
        "citation": "Yuta Koreeda and Christopher D. Manning. ContractNLI. Findings of EMNLP 2021.",
        "license": "CC BY 4.0; notices retained with private archive",
        "dataset": provenance,
        "protocol_sha256": fingerprint,
        "protocol_created_at": protocol["created_at"],
        "model_run_recorded_at": run["recorded_at"],
        "private_run_sha256": run_sha256,
        "model_run_source_sha256": source,
        "scorer_sha256": run["scorer_sha256"],
        "recorder_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "observations": receipt,
        "replay_matches_recorded_results": True,
        "results": result,
        "constant_not_mentioned_reference": reference,
        "usage": usage,
        "wall_seconds": run["wall_seconds"],
        "timing_scope": run["timing_scope"],
        "min_interval_seconds": run["min_interval_seconds"],
        "limits": POLICY["limits"]
        + " Complete test cohort under rules frozen before test JSON was loaded. No post-test tuning or selected subset. Local files and SDK receipts are not signed provider attestations or invoices. Wall time includes token preflight, pacing, recording and scoring; it is not per-request latency. Raw contracts and predictions remain private.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--protocol", required=True, type=Path)
    parser.add_argument("--protocol-sha256", required=True)
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        directory = args.run_dir.resolve()
        if not directory.is_relative_to(Path("var").resolve()):
            raise ValueError("Keep original run private")
        if args.output.resolve().is_relative_to(directory) or args.output.resolve() in {
            args.archive.resolve(),
            args.protocol.resolve(),
        }:
            raise ValueError("Report cannot replace source evidence")
        protocol = check_protocol(args.protocol, args.protocol_sha256)
        data, provenance = load_test(args.archive, args.protocol, args.protocol_sha256)
        run, fingerprint = private_run(directory / "run.json")
        report = build_report(
            run,
            fingerprint,
            data,
            provenance,
            protocol,
            args.protocol_sha256,
            directory / "observations.jsonl",
        )
        check_protocol(args.protocol, args.protocol_sha256)
        # Reread the run receipt before publication, not just the larger journal.
        if private_run(directory / "run.json")[1] != fingerprint:
            raise ValueError("Run changed during export")
        publish_report(args.output, report)
    except (ValueError, OSError, KeyError):
        raise SystemExit("Frozen test export rejected; no result published") from None
    print(
        json.dumps(
            {
                "documents": report["results"]["documents"],
                "claims": report["results"]["claims"],
                "replay_matches": True,
            }
        )
    )


if __name__ == "__main__":
    main()
