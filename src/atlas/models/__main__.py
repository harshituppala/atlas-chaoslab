"""Explicit opt-in CLI for future approved live validation. Offline is default."""

import argparse
import json
from pathlib import Path

from atlas.artifacts import reserve_invocation_artifacts, write_private_json
from atlas.domain import Document

from .bedrock import BedrockGateway
from .contracts import BedrockConfig
from .intelligence import analyze_model
from .session_budget import reserve_configured_run


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="datasets/demo.json")
    parser.add_argument("--config", required=True)
    parser.add_argument("--output", default="var/model-validation.json")
    parser.add_argument("--allow-paid", action="store_true")
    parser.add_argument("--session-budget", default="var/bedrock/campaign-budget.json")
    parser.add_argument("--retrieval", choices=["lexical", "hybrid"], default="lexical")
    args = parser.parse_args()
    if not args.allow_paid:
        parser.error("Live validation requires explicit --allow-paid spending approval")
    config = BedrockConfig.model_validate_json(Path(args.config).read_text())
    body = json.loads(Path(args.input).read_text())
    rfp = Document.model_validate(body["rfp"])
    knowledge = [Document.model_validate(d) for d in body["knowledge"]]
    if rfp.kind != "rfp" or any(d.kind != "knowledge" for d in knowledge):
        parser.error("Invalid document kinds")
    if len({d.id for d in [rfp, *knowledge]}) != len(knowledge) + 1:
        parser.error("Duplicate document IDs")
    output = Path(args.output).resolve()
    root = Path.cwd().resolve()
    if not output.is_relative_to(root / "var"):
        parser.error("Live source-bearing artifacts must be saved under ignored var/")
    retriever = None
    if args.retrieval == "hybrid":
        from atlas.semantic import HybridIndex, LocalEncoder

        retriever = HybridIndex(knowledge, LocalEncoder())
    try:
        journal = reserve_invocation_artifacts(output)
    except FileExistsError:
        parser.error("Existing invocation artifacts must be preserved; choose a new --output name")
    config.validate_live_price()
    reserve_configured_run(args.session_budget, config, output)
    gateway = BedrockGateway.open(config, allow_paid=True)
    gateway.ledger.on_change = lambda value: write_private_json(journal, value)
    try:
        report = analyze_model(rfp, knowledge, gateway, retriever=retriever)
        exit_code = 0
    except Exception as exc:
        report = {"live_model": True, "status": "failed", "error_type": type(exc).__name__}
        exit_code = 1
    report["usage"] = gateway.ledger.report()
    write_private_json(output, report)
    print(
        json.dumps(
            {
                "status": "completed" if not exit_code else "failed",
                "artifact": str(output),
                "estimated_model_cost_usd": report["usage"]["estimated_model_cost_usd"],
            }
        )
    )
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
