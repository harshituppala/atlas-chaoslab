"""Explicit new run from an audited prefix; old journals and reservations are retained."""

import argparse
import copy
import json
from pathlib import Path

from atlas.artifacts import write_private_json
from chaoslab.contract_journal import MAX_JOURNAL_BYTES, input_digest
from chaoslab.contractnli import adapter_input, load_development

from .bedrock import BedrockGateway
from .contract_checkpoint import admit_prefix, audit_checkpoint, digest, parse, private_bytes
from .contract_evaluation import (
    ContractModelAdapter,
    execute_development,
    read_config,
    request,
)
from .contracts import BedrockConfig
from .session_budget import reserve_configured_run


class ContinuationIntegrityError(RuntimeError):
    """Evidence admission failure must escape the judge's wrong-answer handling."""


def prepare(data, provenance, directory, budget, config):
    """No credential lookup, reservation or inference. Admit a stable private snapshot."""
    audit = audit_checkpoint(data, provenance, directory, budget)
    directory = Path(directory).resolve()
    snapshots = {}
    for key, name in (
        ("run", "run.json"),
        ("usage", "usage.json"),
        ("observations", "observations.partial.jsonl"),
    ):
        raw = private_bytes(directory / name, MAX_JOURNAL_BYTES)
        if digest(raw) != audit["evidence_sha256"][key]:
            raise ValueError("Checkpoint changed after audit")
        snapshots[name] = raw
    run = parse(snapshots["run.json"])
    usage = parse(snapshots["usage.json"])
    records = admit_prefix(snapshots["observations.partial.jsonl"], run, data, provenance)
    caps = usage["receipts"][0]
    config.validate_price_identity()
    if (
        config.model_id != usage["model_id"]
        or config.region != usage["region"]
        or config.limits.max_input_tokens != caps["reserved_input_tokens"]
        or config.limits.max_output_tokens != caps["reserved_output_tokens"]
    ):
        raise ValueError("Continuation model identity or call caps differ")
    remaining = audit["remaining_documents"]
    # Reserve only the new tail, at the current reviewed price. Never release an
    # old reservation or reinterpret estimated token usage as an AWS invoice.
    value = config.model_dump(mode="json")
    value["limits"]["max_calls"] = remaining
    value["limits"]["max_reserved_tokens"] = remaining * (
        config.limits.max_input_tokens + config.limits.max_output_tokens
    )
    tail_config = BedrockConfig.model_validate(value)
    from .contract_evaluation import complete_plan

    complete_plan(config, remaining)
    tail_plan = complete_plan(tail_config, remaining)
    for document in data["documents"]:
        request(adapter_input(document, data["labels"]))
    lineage = {
        "schema_version": 1,
        "saved_documents": len(records),
        "new_documents": remaining,
        "origin_evidence_sha256": audit["evidence_sha256"],
        "origin_scorer_sha256": audit["origin_scorer_sha256"],
        "recorded_prior_known_inference_estimate_usd": audit[
            "recorded_known_inference_estimate_usd"
        ],
        "tail_reservation_plan": tail_plan,
        "old_reservation_retained": True,
        "response_authenticity_verified": False,
        "limits": (
            "Saved prefix was shape/input/receipt checked, not authenticated by the provider. "
            "Its answers may be wrong and are rescored without correction. Usage and wall time "
            "on this new run cover only new calls; prior usage is recorded separately. "
            "A failed continuation is preserved, not automatically resumed."
        ),
    }
    return tail_config, records, snapshots, lineage


class PrefixThenModel:
    """Exact ordered, label-free inputs; saved predictions cannot be silently edited."""

    def __init__(self, data, records, model):
        self.expected = [input_digest(adapter_input(d, data["labels"])) for d in data["documents"]]
        self.records = copy.deepcopy(records)
        self.model = model
        self.position = 0

    def __call__(self, adapter, body):
        index = self.position
        if index >= len(self.expected) or input_digest(body) != self.expected[index]:
            raise ContinuationIntegrityError("Continuation input order or content changed")
        self.position += 1
        if index < len(self.records):
            return copy.deepcopy(self.records[index]["output"])
        return self.model(adapter, body)


def verify_origin(directory, snapshots):
    for name, expected in snapshots.items():
        if private_bytes(Path(directory) / name, MAX_JOURNAL_BYTES) != expected:
            raise ContinuationIntegrityError("Origin checkpoint changed")


def run(data, provenance, gateway, directory, origin, records, snapshots, lineage, *, interval=10):
    verify_origin(origin, snapshots)
    model = ContractModelAdapter(gateway, min_interval_seconds=interval)
    adapter = PrefixThenModel(data, records, model)

    def guarded(name, body):
        verify_origin(origin, snapshots)
        try:
            return adapter(name, body)
        finally:
            verify_origin(origin, snapshots)

    report = execute_development(
        data,
        provenance,
        gateway,
        directory,
        guarded,
        min_interval_seconds=interval,
        continuation=lineage,
    )
    try:
        verify_origin(origin, snapshots)
    except ContinuationIntegrityError:
        # A changed origin invalidates publication even if all calls completed.
        report.update(
            status="failed", results=None, observations=None, failure_kind="origin_evidence_changed"
        )
        write_private_json(Path(directory) / "run.json", report)
        raise
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--origin", required=True, type=Path)
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--session-budget", default="var/bedrock/campaign-budget.json")
    parser.add_argument("--min-interval-seconds", type=float, default=10)
    parser.add_argument("--allow-paid", action="store_true")
    args = parser.parse_args()
    try:
        directory = args.run_dir.resolve()
        if not directory.is_relative_to(Path("var").resolve()) or directory.exists():
            raise ValueError("Choose a new private run directory")
        if directory.is_relative_to(args.origin.resolve()):
            raise ValueError("Continuation must be outside original evidence")
        ContractModelAdapter(None, min_interval_seconds=args.min_interval_seconds)
        data, provenance = load_development(args.archive)
        config, records, snapshots, lineage = prepare(
            data, provenance, args.origin, args.session_budget, read_config(args.config)
        )
        if not args.allow_paid:
            print(json.dumps({"continuation": lineage, "inference_sent": False}))
            return
        config.validate_live_price()
        verify_origin(args.origin, snapshots)
        reserve_configured_run(args.session_budget, config, directory / "run.json")
        gateway = BedrockGateway.open(config, allow_paid=True)
        try:
            report = run(
                data,
                provenance,
                gateway,
                directory,
                args.origin,
                records,
                snapshots,
                lineage,
                interval=args.min_interval_seconds,
            )
        finally:
            gateway.client.close()
    except Exception:
        raise SystemExit("Continuation stopped; no complete result published") from None
    print(
        json.dumps(
            {
                "status": report["status"],
                "new_documents": lineage["new_documents"],
                "saved_documents": lineage["saved_documents"],
            }
        )
    )
    raise SystemExit(0 if report["status"] == "complete" else 1)


if __name__ == "__main__":
    main()
