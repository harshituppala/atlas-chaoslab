"""Rescore a complete private model run before exporting reviewed aggregates.

No adapter execution, provider calls, contract excerpts or per-document outputs.
Checksums identify local evidence; they are not signed provider attestations.
"""

import argparse
import hashlib
import json
import os
import stat
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from atlas.models.contracts import PriceCard
from atlas.models.provenance import source_manifest
from chaoslab.__main__ import source_digest
from chaoslab.artifacts import publish_report
from chaoslab.contract_journal import (
    finite_float,
    invalid_constant,
    read_observations,
    unique_object,
)
from chaoslab.contractnli import adapter_input, always_not_mentioned, evaluate, load_development
from chaoslab.execution import AdapterFailure


def private_run(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_size > 8_000_000:
            raise ValueError("Private run admission failed")
        raw = stream.read(8_000_001)
    if len(raw) > 8_000_000:
        raise ValueError("Private run byte budget exceeded")
    return json.loads(
        raw,
        object_pairs_hook=unique_object,
        parse_float=finite_float,
        parse_constant=invalid_constant,
    ), hashlib.sha256(raw).hexdigest()


def usage_summary(usage, documents):
    card = PriceCard.model_validate(usage["price_card"])
    receipts = usage["receipts"]
    if (
        usage["provider"] != "bedrock"
        or usage["model_id"] != card.model_id
        or usage["region"] != card.region
        or len(receipts) != documents
    ):
        raise ValueError("Usage identity or complete-cohort receipt count differs")
    tokens_in, tokens_out, total, statuses = 0, 0, Decimal(0), {}
    for receipt in receipts:
        if receipt["task"] != "contract_claims" or receipt["status"] not in {
            "validated",
            "invalid_schema",
            "incomplete_output",
        }:
            raise ValueError("Unreconciled provider receipt")
        incoming, outgoing = receipt["input_tokens"], receipt["output_tokens"]
        if type(incoming) is not int or type(outgoing) is not int or min(incoming, outgoing) < 0:
            raise ValueError("Invalid recorded token usage")
        expected = (
            Decimal(incoming) * card.input_usd_per_million
            + Decimal(outgoing) * card.output_usd_per_million
        ) / 1_000_000
        if Decimal(receipt["estimated_cost_usd"]) != expected:
            raise ValueError("Receipt cost differs from price card")
        total += expected
        tokens_in += incoming
        tokens_out += outgoing
        statuses[receipt["status"]] = statuses.get(receipt["status"], 0) + 1
    if Decimal(usage["estimated_model_cost_usd"]) != total:
        raise ValueError("Aggregate cost differs from receipts")
    return {
        "provider": "bedrock",
        "model_id": card.model_id,
        "region": card.region,
        "calls": len(receipts),
        "receipt_statuses": statuses,
        "input_tokens": tokens_in,
        "output_tokens": tokens_out,
        "estimated_inference_cost_usd": str(total),
        "cost_is_invoice": False,
        "price_card": card.model_dump(mode="json"),
    }


def build_report(run, run_sha256, data, provenance, observations):
    if (
        run["status"] != "complete"
        or run["live_model"] is not True
        or run["dataset"] != provenance
        or run["scorer_sha256"] != source_digest()
        or run["source_manifest"]["source_sha256"] != source_manifest()["source_sha256"]
    ):
        raise ValueError("A complete live run with unchanged source and inputs is required")
    header, records, receipt = read_observations(
        observations,
        dataset=provenance,
        inputs={d["id"]: adapter_input(d, data["labels"]) for d in data["documents"]},
    )
    if receipt != run["observations"] or header["adapter"] != run["adapter"]:
        raise ValueError("Saved observations differ from run receipt")

    def replay(_, body):
        record = records[body["document"]["id"]]
        if record["status"] == "failed":
            raise AdapterFailure("Saved invocation failure")
        return record["output"]

    result = evaluate(data, header["adapter"], invoke_adapter=replay)
    if result != run["results"]:
        raise ValueError("Replay differs from recorded scores")
    baseline = evaluate(
        data,
        "chaoslab.contractnli:always_not_mentioned",
        invoke_adapter=lambda _, body: always_not_mentioned(body),
    )
    return {
        "recorded_at": datetime.now(UTC).isoformat(),
        "task": "ContractNLI complete development split, fixed claims and evidence spans",
        "source": "https://stanfordnlp.github.io/contract-nli/",
        "citation": "Yuta Koreeda and Christopher D. Manning. ContractNLI. Findings of EMNLP 2021.",
        "license": "CC BY 4.0; original license and terms retained with private archive",
        "dataset": provenance,
        "split": "All development contracts; training and test JSON remain unloaded.",
        "scorer_sha256": run["scorer_sha256"],
        "model_run_source_sha256": run["source_manifest"]["source_sha256"],
        "private_run_sha256": run_sha256,
        "recorder_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "observations": receipt,
        "replay_matches_recorded_results": True,
        "results": result,
        "constant_not_mentioned_reference": baseline,
        "usage": usage_summary(run["usage"], len(data["documents"])),
        "wall_seconds": run["wall_seconds"],
        "timing_scope": run["timing_scope"],
        "min_interval_seconds": run["min_interval_seconds"],
        "limits": "One development run, not blinded or untouched-test performance, RFP accuracy or legal validation. The public corpus may be in model pretraining. Evidence metrics exclude NotMentioned gold labels. Raw contracts and responses remain private. SDK receipts and local checksums are not signed provider attestations or invoices. Batch wall time includes configured pacing, not per-request latency. Separate stopped attempts are excluded from these scores and usage totals; their full campaign reservations remain retained.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--output", type=Path, default=Path("var/contract-model-development.json"))
    args = parser.parse_args()
    try:
        run_dir = args.run_dir.resolve()
        if not run_dir.is_relative_to(Path("var").resolve()):
            raise ValueError("Run must remain private")
        if (
            args.output.resolve().is_relative_to(run_dir)
            or args.output.resolve() == args.archive.resolve()
        ):
            raise ValueError("Report cannot overwrite source evidence")
        data, provenance = load_development(args.archive)
        run, fingerprint = private_run(run_dir / "run.json")
        result = build_report(run, fingerprint, data, provenance, run_dir / "observations.jsonl")
        if private_run(run_dir / "run.json")[1] != fingerprint:
            raise ValueError("Run changed during export")
        publish_report(args.output, result)
    except Exception:
        raise SystemExit("Contract model export refused; previous report preserved") from None
    print(
        json.dumps(
            {
                "documents": result["results"]["documents"],
                "claims": result["results"]["claims"],
                "replay_matches": True,
            }
        )
    )


if __name__ == "__main__":
    main()
