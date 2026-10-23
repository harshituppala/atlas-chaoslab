"""Read-only admission of stopped contract runs; never inference or automatic resume."""

import argparse
import hashlib
import json
import os
import stat
from decimal import Decimal
from pathlib import Path

from atlas.artifacts import write_private_json
from chaoslab.contract_journal import (
    MAX_JOURNAL_BYTES,
    MAX_LINE_BYTES,
    finite_float,
    input_digest,
    invalid_constant,
    unique_object,
)
from chaoslab.contractnli import adapter_input, load_development

from .bedrock import Receipt, provider_schema
from .contract_evaluation import ADAPTER, SYSTEM, request
from .contracts import PriceCard
from .session_budget import SessionBudget


def private_bytes(path, limit):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_size > limit:
            raise ValueError("Checkpoint file admission failed")
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("Checkpoint file byte budget exceeded")
    return raw


def parse(raw):
    return json.loads(
        raw,
        object_pairs_hook=unique_object,
        parse_float=finite_float,
        parse_constant=invalid_constant,
    )


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def admit_prefix(raw, run, data, provenance):
    lines = raw.splitlines(keepends=True)
    if not lines or any(len(line) > MAX_LINE_BYTES or not line.endswith(b"\n") for line in lines):
        raise ValueError("Incomplete checkpoint line")
    header = parse(lines[0])
    if (
        header
        != {
            "kind": "header",
            "schema_version": 1,
            "task": "contractnli-development-v1",
            "dataset": provenance,
            "adapter": ADAPTER,
            "scorer_sha256": run["scorer_sha256"],
        }
        or type(header["schema_version"]) is not int
    ):
        raise ValueError("Checkpoint header differs")
    records = [parse(line) for line in lines[1:]]
    if not 0 < len(records) < len(data["documents"]):
        raise ValueError("A nonempty stopped prefix is required")
    for document, record in zip(data["documents"], records, strict=False):
        body = adapter_input(document, data["labels"])
        if (
            not isinstance(record, dict)
            or set(record) != {"kind", "document_id", "input_sha256", "status", "output"}
            or record["kind"] != "observation"
            or type(record["document_id"]) is not int
            or record["document_id"] != document["id"]
            or record["input_sha256"] != input_digest(body)
            or record["status"] != "returned"
        ):
            raise ValueError("Checkpoint is not the exact returned input prefix")
        _, output = request(body)
        # Shape admission is deliberately not annotation scoring: wrong answers
        # remain wrong answers if a future, separately approved runner reuses them.
        output.model_validate(record["output"])
    return records


def reconcile_receipts(usage, data, records):
    card = PriceCard.model_validate(usage["price_card"])
    receipts = usage["receipts"]
    if (
        usage["provider"] != "bedrock"
        or usage["model_id"] != card.model_id
        or usage["region"] != card.region
        or usage["cost_is_invoice"] is not False
        or len(receipts) != len(records)
    ):
        raise ValueError("Checkpoint usage identity or receipt count differs")
    total, caps = Decimal(0), set()
    for document, receipt in zip(data["documents"], receipts, strict=False):
        payload, output = request(adapter_input(document, data["labels"]))
        prompt = json.dumps({"system": SYSTEM, "data": payload}, ensure_ascii=False, sort_keys=True)
        schema = json.dumps(provider_schema(output.model_json_schema()), sort_keys=True)
        if (
            set(receipt) != set(Receipt.__dataclass_fields__)
            or receipt["task"] != "contract_claims"
            or receipt["status"] != "validated"
            or receipt["prompt_sha256"] != digest(prompt.encode())
            or receipt["schema_sha256"] != digest(schema.encode())
            or any(
                receipt[k] is not None
                for k in ("provider_error_code", "validation_error_code", "invocation_failure_kind")
            )
        ):
            raise ValueError("Unreconciled checkpoint receipt")
        for key in (
            "preflight_input_tokens",
            "reserved_input_tokens",
            "reserved_output_tokens",
            "input_tokens",
            "output_tokens",
        ):
            if type(receipt[key]) is not int or receipt[key] < 0:
                raise ValueError("Invalid checkpoint token usage")
        incoming, outgoing = receipt["reserved_input_tokens"], receipt["reserved_output_tokens"]
        if (
            min(incoming, outgoing) < 1
            or receipt["preflight_input_tokens"] > incoming
            or receipt["input_tokens"] > incoming
            or receipt["output_tokens"] > outgoing
        ):
            raise ValueError("Checkpoint exceeded recorded token caps")
        cost = (
            Decimal(receipt["input_tokens"]) * card.input_usd_per_million
            + Decimal(receipt["output_tokens"]) * card.output_usd_per_million
        ) / 1_000_000
        if (
            not isinstance(receipt["estimated_cost_usd"], str)
            or Decimal(receipt["estimated_cost_usd"]) != cost
        ):
            raise ValueError("Checkpoint receipt arithmetic differs")
        total += cost
        caps.add((incoming, outgoing))
    if len(caps) != 1 or Decimal(usage["estimated_model_cost_usd"]) != total:
        raise ValueError("Checkpoint aggregate arithmetic or call caps differ")
    incoming, outgoing = caps.pop()
    per_call = (
        Decimal(incoming) * card.input_usd_per_million
        + Decimal(outgoing) * card.output_usd_per_million
    ) / 1_000_000
    return total, per_call


def audit_checkpoint(data, provenance, directory, budget_path):
    directory = Path(directory).absolute()
    root = Path("var").resolve()
    budget_path = Path(budget_path).absolute()
    if not directory.resolve().is_relative_to(root) or not budget_path.resolve().is_relative_to(
        root
    ):
        raise ValueError("Checkpoint evidence must remain under private var/")
    paths = {
        "run": directory / "run.json",
        "usage": directory / "usage.json",
        "observations": directory / "observations.partial.jsonl",
        "campaign": budget_path,
    }
    raw = {
        name: private_bytes(path, MAX_JOURNAL_BYTES if name == "observations" else 8_000_000)
        for name, path in paths.items()
    }
    run, usage = parse(raw["run"]), parse(raw["usage"])
    scorer = run["scorer_sha256"]
    if (
        not isinstance(scorer, str)
        or len(scorer) != 64
        or any(c not in "0123456789abcdef" for c in scorer)
    ):
        raise ValueError("Invalid origin scorer fingerprint")
    if (
        run["status"] != "failed"
        or run["live_model"] is not True
        or run["task"] != "contractnli-development-v1"
        or run["adapter"] != ADAPTER
        or run["dataset"] != provenance
        or run["results"] is not None
        or run["observations"] is not None
        or run["usage"] != usage
        or (directory / "observations.jsonl").exists()
    ):
        raise ValueError("A stopped live run with matching usage is required")
    records = admit_prefix(raw["observations"], run, data, provenance)
    known, per_call = reconcile_receipts(usage, data, records)
    budget = SessionBudget.model_validate(parse(raw["campaign"]))
    ids = [r.run_id for r in budget.reservations]
    matches = [
        r for r in budget.reservations if r.run_id == str((directory / "run.json").resolve())
    ]
    if (
        len(ids) != len(set(ids))
        or len(matches) != 1
        or budget.reserved_usd > budget.authorized_usd
    ):
        raise ValueError("Campaign reservation admission failed")
    if matches[0].reserved_usd < per_call * len(data["documents"]):
        raise ValueError("Original reservation did not cover the complete cohort")
    if any(private_bytes(paths[name], len(value)) != value for name, value in raw.items()):
        raise ValueError("Checkpoint evidence changed during admission")
    remaining = len(data["documents"]) - len(records)
    return {
        "schema_version": 1,
        "task": "contractnli-checkpoint-audit-v1",
        "dataset": provenance,
        "records_admitted": len(records),
        "remaining_documents": remaining,
        "recorded_known_inference_estimate_usd": str(known),
        "original_run_reservation_retained_usd": str(matches[0].reserved_usd),
        "remaining_call_caps_estimate_usd": str(per_call * remaining),
        "campaign_reserved_usd": str(budget.reserved_usd),
        "campaign_authorized_usd": str(budget.authorized_usd),
        "evidence_sha256": {name: digest(value) for name, value in raw.items()},
        "automatic_resume_allowed": False,
        "provider_calls": 0,
        "accuracy_scores": None,
        "response_authenticity_verified": False,
        "auditor_sha256": digest(Path(__file__).read_bytes()),
        "origin_scorer_sha256": run["scorer_sha256"],
        "limits": "Read-only prefix/receipt reconciliation, not authenticity or answer correctness. No refund, new authorization, credential lookup, provider request, rewritten journal or completed result. Partial journals have no completion footer or independently authenticated response digest; admission does not prove the original response bytes. Fingerprints bind the evidence read now for later review. Historical failure cause remains unknown. A future resume implementation and spending review are still required; historical price estimates are neither fresh live-price approval nor invoices.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--session-budget", default="var/bedrock/campaign-budget.json")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        output = args.output.absolute()
        if (
            not output.resolve().is_relative_to(Path("var").resolve())
            or output.exists()
            or output.resolve().is_relative_to(Path(args.run_dir).resolve())
            or output.resolve()
            in {Path(args.session_budget).resolve(), Path(args.archive).resolve()}
        ):
            raise ValueError("Choose a new private report outside source evidence")
        data, provenance = load_development(args.archive)
        report = audit_checkpoint(data, provenance, args.run_dir, args.session_budget)
        write_private_json(output, report)
    except Exception:
        raise SystemExit("Checkpoint audit refused; source evidence preserved") from None
    print(
        json.dumps(
            {
                "records_admitted": report["records_admitted"],
                "provider_calls": 0,
                "automatic_resume_allowed": False,
            }
        )
    )


if __name__ == "__main__":
    main()
