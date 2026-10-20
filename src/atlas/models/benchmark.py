"""Private, shared-budget model runs from a label-free input manifest.

Default is an offline reservation plan. Live execution requires explicit opt-in.
One gateway/ledger covers the whole batch; provider failures always stop it.
"""

import argparse
import hashlib
import json
import re
from decimal import Decimal
from pathlib import Path

from atlas.artifacts import reserve_invocation_artifacts, write_private_json
from atlas.domain import Document

from .bedrock import BedrockGateway, InvalidModelOutput
from .contracts import BedrockConfig
from .intelligence import analyze_model
from .provenance import source_manifest
from .session_budget import reserve_configured_run


def digest(body):
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def validate_manifest(value):
    if (
        set(value) != {"schema_version", "dataset_sha256", "cases"}
        or type(value["schema_version"]) is not int
        or value["schema_version"] != 1
        or not re.fullmatch(r"[a-f0-9]{64}", value["dataset_sha256"])
    ):
        raise ValueError("Invalid input manifest contract")
    rows = value["cases"]
    if not 1 <= len(rows) <= 200 or len({row["id"] for row in rows}) != len(rows):
        raise ValueError("Manifest requires distinct bounded cases")
    for row in rows:
        if (
            set(row) != {"id", "input", "input_sha256"}
            or digest(row["input"]) != row["input_sha256"]
        ):
            raise ValueError("Input manifest identity differs")
        body = row["input"]
        if set(body) != {"rfp", "knowledge"}:
            raise ValueError("Unexpected model input fields")
        rfp = Document.model_validate(body["rfp"])
        knowledge = [Document.model_validate(doc) for doc in body["knowledge"]]
        if (
            rfp.kind != "rfp"
            or not 1 <= len(knowledge) <= 30
            or any(doc.kind != "knowledge" for doc in knowledge)
        ):
            raise ValueError("Invalid document kinds/count")
        if (
            len({doc.id for doc in [rfp, *knowledge]}) != 1 + len(knowledge)
            or sum(len(doc.text) for doc in [rfp, *knowledge]) > 300000
        ):
            raise ValueError("Input source budget exceeded")
    return rows


def reservation_plan(config, selected_cases):
    config.validate_price_identity()
    limits, price = config.limits, config.price_card
    per_call = (
        Decimal(limits.max_input_tokens) * price.input_usd_per_million
        + Decimal(limits.max_output_tokens) * price.output_usd_per_million
    ) / 1000000
    cap = min(
        limits.max_calls,
        limits.max_reserved_tokens // (limits.max_input_tokens + limits.max_output_tokens),
    )
    if per_call:
        cap = min(cap, int(limits.max_estimated_cost_usd // per_call))
    if cap < 1:
        raise ValueError("Budget cannot reserve a single call")
    return {
        "selected_cases": selected_cases,
        "call_cap": cap,
        "per_call_reserved_usd": str(per_call),
        "maximum_reserved_inference_usd": str(cap * per_call),
        "network_used": False,
        "scope": "Configured inference-token reservation bound, not a provider quote, invoice or total AWS cost. Model/region compatibility and prices require independent verification.",
    }


def run_batch(manifest, gateway, output, journal, *, max_cases, continue_invalid=False):
    if not 1 <= max_cases <= 200:
        raise ValueError("Invalid case budget")
    rows = validate_manifest(manifest)[:max_cases]
    result = {
        "schema_version": 1,
        "dataset_sha256": manifest["dataset_sha256"],
        "live_model": bool(gateway.live),
        "selected_cases": len(rows),
        "results": [],
        "continue_invalid_output": continue_invalid,
        "source_manifest": source_manifest(),
    }
    gateway.ledger.on_change = lambda value: write_private_json(journal, value)
    write_private_json(journal, gateway.ledger.report())
    write_private_json(output, result)
    for row in rows:
        invalid_output = False
        body = row["input"]
        entry = {"id": row["id"], "input_sha256": row["input_sha256"]}
        try:
            entry.update(
                status="succeeded",
                output=analyze_model(
                    Document.model_validate(body["rfp"]),
                    [Document.model_validate(doc) for doc in body["knowledge"]],
                    gateway,
                ),
            )
        except Exception as exc:
            entry.update(status="failed", error_type=type(exc).__name__)
            invalid_output = isinstance(exc, InvalidModelOutput)
        result["results"].append(entry)
        result["usage"] = gateway.ledger.report()
        write_private_json(output, result)
        if entry["status"] == "failed" and not (
            continue_invalid
            and invalid_output
            and all(r.status != "invocation_unknown" for r in gateway.ledger.receipts)
        ):
            break
    result["source_unchanged_at_completion"] = (
        source_manifest()["source_sha256"] == result["source_manifest"]["source_sha256"]
    )
    write_private_json(output, result)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--output", default="var/model-reasoning-smoke.json")
    parser.add_argument("--max-cases", type=int, default=1)
    parser.add_argument("--allow-paid", action="store_true")
    parser.add_argument("--session-budget", default="var/bedrock/campaign-budget.json")
    parser.add_argument("--continue-invalid-output", action="store_true")
    args = parser.parse_args()
    raw = Path(args.input).read_bytes()
    if len(raw) > 8_000_000 or not 1 <= args.max_cases <= 200:
        parser.error("Input/case budget exceeded")
    manifest = json.loads(raw)
    rows = validate_manifest(manifest)
    config = BedrockConfig.model_validate_json(Path(args.config).read_text())
    plan = reservation_plan(config, min(len(rows), args.max_cases))
    if not args.allow_paid:
        print(json.dumps(plan, indent=2))
        return
    config.validate_live_price()
    output = Path(args.output).resolve()
    if not output.is_relative_to(Path("var").resolve()):
        parser.error("Live artifacts must remain under ignored var/")
    journal = reserve_invocation_artifacts(output)
    config.validate_live_price()
    reserve_configured_run(args.session_budget, config, output)
    gateway = BedrockGateway.open(config, allow_paid=True)
    result = run_batch(
        manifest,
        gateway,
        output,
        journal,
        max_cases=args.max_cases,
        continue_invalid=args.continue_invalid_output,
    )
    print(
        json.dumps(
            {
                "cases_recorded": len(result["results"]),
                "live_model": result["live_model"],
                "estimated_model_cost_usd": result["usage"]["estimated_model_cost_usd"],
            }
        )
    )
    raise SystemExit(0 if all(row["status"] == "succeeded" for row in result["results"]) else 1)


if __name__ == "__main__":
    main()
