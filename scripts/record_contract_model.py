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

from atlas.models.contract_checkpoint import admit_prefix, audit_checkpoint, parse, private_bytes
from atlas.models.contracts import PriceCard
from atlas.models.provenance import source_manifest
from atlas.models.session_budget import SessionBudget
from chaoslab.__main__ import source_digest
from chaoslab.artifacts import publish_report
from chaoslab.contract_journal import (
    MAX_JOURNAL_BYTES,
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


def continuation_usage(run, data, provenance, records, origin, budget, run_path):
    if origin is None or budget is None:
        raise ValueError("Continuation export requires original evidence and retained campaign")
    audit = audit_checkpoint(data, provenance, origin, budget)
    lineage = run["continuation"]
    if (
        lineage["saved_documents"] != audit["records_admitted"]
        or lineage["new_documents"] != audit["remaining_documents"]
        or lineage["origin_scorer_sha256"] != audit["origin_scorer_sha256"]
        or lineage["old_reservation_retained"] is not True
        or lineage["response_authenticity_verified"] is not False
        or any(
            lineage["origin_evidence_sha256"][k] != audit["evidence_sha256"][k]
            for k in ("run", "usage", "observations")
        )
    ):
        raise ValueError("Continuation lineage differs from original evidence")
    raw_run = private_bytes(Path(origin) / "run.json", 8_000_000)
    raw_usage = private_bytes(Path(origin) / "usage.json", 8_000_000)
    raw_records = private_bytes(Path(origin) / "observations.partial.jsonl", MAX_JOURNAL_BYTES)
    for key, value in (("run", raw_run), ("usage", raw_usage), ("observations", raw_records)):
        if hashlib.sha256(value).hexdigest() != audit["evidence_sha256"][key]:
            raise ValueError("Origin changed during export")
    prefix = admit_prefix(raw_records, parse(raw_run), data, provenance)
    for saved in prefix:
        copied = records[saved["document_id"]]
        if any(copied[k] != saved[k] for k in ("document_id", "input_sha256", "status", "output")):
            raise ValueError("Copied prefix differs from original observations")
    old_usage = usage_summary(parse(raw_usage), len(prefix))
    new_usage = usage_summary(run["usage"], len(data["documents"]) - len(prefix))
    if (old_usage["model_id"], old_usage["region"]) != (new_usage["model_id"], new_usage["region"]):
        raise ValueError("Continuation provider identity differs")
    raw_campaign = private_bytes(budget, 2_000_000)
    if hashlib.sha256(raw_campaign).hexdigest() != audit["evidence_sha256"]["campaign"]:
        raise ValueError("Campaign changed during export")
    campaign = SessionBudget.model_validate(parse(raw_campaign))
    matches = [r for r in campaign.reservations if r.run_id == str(Path(run_path).resolve())]
    old_caps = parse(raw_usage)["receipts"][0]
    card = PriceCard.model_validate(run["usage"]["price_card"])
    per_call = (
        Decimal(old_caps["reserved_input_tokens"]) * card.input_usd_per_million
        + Decimal(old_caps["reserved_output_tokens"]) * card.output_usd_per_million
    ) / 1_000_000
    required = per_call * lineage["new_documents"]
    if (
        len(matches) != 1
        or matches[0].reserved_usd < required
        or Decimal(lineage["tail_reservation_plan"]["maximum_reserved_inference_usd"]) != required
        or any(
            r["reserved_input_tokens"] != old_caps["reserved_input_tokens"]
            or r["reserved_output_tokens"] != old_caps["reserved_output_tokens"]
            for r in run["usage"]["receipts"]
        )
    ):
        raise ValueError("New-tail reservation or call caps differ")
    return new_usage, old_usage


def build_report(run, run_sha256, data, provenance, observations, *, origin=None, budget=None):
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
    continued = "continuation" in run
    if continued:
        usage, prior_usage = continuation_usage(
            run, data, provenance, records, origin, budget, Path(observations).parent / "run.json"
        )
    else:
        usage, prior_usage = usage_summary(run["usage"], len(data["documents"])), None
    report = {
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
        "usage": usage,
        "wall_seconds": run["wall_seconds"],
        "timing_scope": run["timing_scope"],
        "min_interval_seconds": run["min_interval_seconds"],
        "limits": "One development run, not blinded or untouched-test performance, RFP accuracy or legal validation. The public corpus may be in model pretraining. Evidence metrics exclude NotMentioned gold labels. Raw contracts and responses remain private. SDK receipts and local checksums are not signed provider attestations or invoices. Batch wall time includes configured pacing, not per-request latency. Separate stopped attempts are excluded from these scores and usage totals; their full campaign reservations remain retained.",
    }
    if continued:
        report["continuation"] = run["continuation"]
        report["saved_prefix_usage"] = prior_usage
        report["limits"] = (
            "Complete development scoring assembled from saved predictions and new calls. "
            "Not an uninterrupted model run, blinded test, RFP accuracy or legal validation. "
            "Usage and wall time cover only new calls; saved-prefix token estimates are "
            "separate. Other stopped attempts are excluded and all old reservations retained. "
            "The public corpus may be in pretraining. Saved responses are not independently "
            "provider-authenticated; local checksums and SDK receipts are not attestations or invoices."
        )
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--origin", type=Path)
    parser.add_argument("--session-budget", type=Path)
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
        result = build_report(
            run,
            fingerprint,
            data,
            provenance,
            run_dir / "observations.jsonl",
            origin=args.origin,
            budget=args.session_budget,
        )
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
