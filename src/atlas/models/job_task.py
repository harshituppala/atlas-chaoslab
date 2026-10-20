"""Operator-enabled paid job subprocess; never configured by document content."""

import argparse
import json
import sys
from pathlib import Path

from atlas.artifacts import reserve_invocation_artifacts, write_private_json
from atlas.domain import Document
from atlas.execution import fingerprint, prepare_model_publication

from .bedrock import BedrockGateway
from .contracts import BedrockConfig
from .intelligence import analyze_model
from .job_spec import ModelJobSpec, job_spec
from .session_budget import reserve_configured_run


def execute_claim(value, config, *, session_budget, allow_paid=False, gateway_factory=None):
    if not allow_paid:
        raise ValueError("Paid model worker requires explicit operator opt-in")
    body = value["input"]
    pinned = ModelJobSpec.model_validate(body.get("_model_spec"))
    if pinned.digest() != job_spec(config).digest():
        raise ValueError("Worker configuration differs from the pinned job")
    rfp = Document.model_validate(body["rfp"])
    knowledge = [Document.model_validate(d) for d in body["knowledge"]]
    if (
        rfp.kind != "rfp"
        or not 1 <= len(knowledge) <= 30
        or any(d.kind != "knowledge" for d in knowledge)
        or len({d.id for d in [rfp, *knowledge]}) != len(knowledge) + 1
        or sum(len(d.text) for d in [rfp, *knowledge]) > 300_000
    ):
        raise ValueError("Invalid model job source scope")
    config.validate_live_price()
    key = fingerprint({"tenant": value["tenant"], "job": value["id"]})
    output = Path("var/model-jobs") / f"{key}.json"
    journal = reserve_invocation_artifacts(output)
    # Both ownership and cumulative funding precede credential initialization.
    reserve_configured_run(session_budget, config, output)
    factory = gateway_factory or BedrockGateway.open
    try:
        gateway = factory(config, allow_paid=True)
        gateway.ledger.on_change = lambda usage: write_private_json(journal, usage)
        write_private_json(journal, gateway.ledger.report())
    except Exception:
        write_private_json(
            output, {"status": "failed", "phase": "setup", "error_code": "provider_setup_failed"}
        )
        raise
    try:
        report = analyze_model(rfp, knowledge, gateway)
        report["usage"] = gateway.ledger.report()
        payload = prepare_model_publication(
            body, report, estimated_cost_usd=report["usage"]["estimated_model_cost_usd"]
        )
        write_private_json(output, {"status": "completed", "report": report})
        return payload
    except Exception as exc:
        write_private_json(
            output,
            {
                "status": "failed",
                "error_type": type(exc).__name__,
                "usage": gateway.ledger.report(),
            },
        )
        raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--session-budget", required=True)
    parser.add_argument("--allow-paid", action="store_true")
    args = parser.parse_args()
    try:
        raw = sys.stdin.read(1_500_001)
        if len(raw.encode()) > 1_500_000:
            raise ValueError("Model job input budget exceeded")
        value = json.loads(raw)
        config = BedrockConfig.model_validate_json(Path(args.config).read_bytes())
        payload = execute_claim(
            value, config, session_budget=args.session_budget, allow_paid=args.allow_paid
        )
        print(json.dumps(payload))
    except Exception:
        # Parent sees only a fixed category; details and source-bearing receipts stay private.
        print(json.dumps({"worker_error": "model_execution_failed"}))
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
