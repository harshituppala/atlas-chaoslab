"""Freeze first; inspect a complete test plan offline; require explicit opt-in for inference."""

import argparse
import hashlib
import json
from pathlib import Path

from atlas.artifacts import write_private_json
from chaoslab.contract_holdout import TASK, bounded_json, check_protocol, freeze, load_test
from chaoslab.contractnli import adapter_input

from .bedrock import BedrockGateway
from .contract_evaluation import (
    SYSTEM,
    ContractModelAdapter,
    complete_plan,
    execute_development,
    read_config,
    request,
)
from .contracts import BedrockConfig
from .provenance import source_manifest
from .session_budget import reserve_configured_run


class ProtocolChanged(RuntimeError):
    """A changed protocol stops the cohort rather than becoming a scored wrong answer."""


def recipe(config):
    return {
        "model_id": config.model_id,
        "count_tokens_model_id": config.count_tokens_model_id,
        "region": config.region,
        "max_input_tokens": config.limits.max_input_tokens,
        "max_output_tokens": config.limits.max_output_tokens,
        "system_prompt_sha256": hashlib.sha256(SYSTEM.encode()).hexdigest(),
        "execution_source_sha256": source_manifest()["source_sha256"],
        "request_policy": "Existing contract adapter and dynamic structured-output schema; no tools or retrieval. Gateway generation settings and schema construction are bound by execution source.",
    }


def guard(protocol_path, fingerprint, config):
    try:
        protocol = check_protocol(protocol_path, fingerprint)
        if protocol["recipe"] != recipe(config):
            raise ValueError("Execution recipe differs")
    except (ValueError, OSError):
        raise ProtocolChanged("Frozen recipe or protocol changed") from None
    return protocol


def prepare(archive, protocol_path, fingerprint, config):
    guard(protocol_path, fingerprint, config)
    data, provenance = load_test(archive, protocol_path, fingerprint)
    for document in data["documents"]:
        request(adapter_input(document, data["labels"], task=TASK))
    documents = len(data["documents"])
    complete_plan(config, documents)
    # Narrow the authorized configuration to exactly this full cohort. Capacity
    # is not permission to reserve or send unused calls from a larger ceiling.
    value = config.model_dump(mode="json")
    value["limits"]["max_calls"] = documents
    value["limits"]["max_reserved_tokens"] = documents * (
        config.limits.max_input_tokens + config.limits.max_output_tokens
    )
    selected = BedrockConfig.model_validate(value)
    plan = complete_plan(selected, documents)
    guard(protocol_path, fingerprint, selected)
    return data, provenance, plan, selected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--protocol", required=True, type=Path)
    parser.add_argument("--protocol-sha256")
    parser.add_argument("--development-report", type=Path)
    parser.add_argument("--development-observations", type=Path)
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--session-budget", default="var/bedrock/campaign-budget.json")
    parser.add_argument("--min-interval-seconds", type=float, default=10)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--freeze", action="store_true")
    mode.add_argument("--allow-paid", action="store_true")
    args = parser.parse_args()
    try:
        config = read_config(args.config)
        config.validate_price_identity()
        ContractModelAdapter(None, min_interval_seconds=args.min_interval_seconds)
        if args.freeze:
            if not args.development_report or not args.development_observations:
                raise ValueError("Freeze needs complete development evidence")
            report, _ = bounded_json(args.development_report)
            if (report["usage"]["model_id"], report["usage"]["region"]) != (
                config.model_id,
                config.region,
            ):
                raise ValueError("Development model identity differs")
            fingerprint = freeze(
                args.archive,
                args.development_report,
                args.development_observations,
                recipe(config),
                args.protocol,
            )
            guard(args.protocol, fingerprint, config)
            print(
                json.dumps(
                    {
                        "protocol_sha256": fingerprint,
                        "test_split_read": False,
                        "provider_requests": 0,
                    }
                )
            )
            return
        if not args.protocol_sha256 or args.run_dir is None:
            raise ValueError("A pinned protocol and new private run directory are required")
        directory = args.run_dir.resolve()
        if not directory.is_relative_to(Path("var").resolve()) or directory.exists():
            raise ValueError("Choose a new private run directory")
        data, provenance, plan, config = prepare(
            args.archive, args.protocol, args.protocol_sha256, config
        )
        if not args.allow_paid:
            print(
                json.dumps(
                    {
                        "plan": plan,
                        "dataset": provenance,
                        "protocol_sha256": args.protocol_sha256,
                        "provider_requests": 0,
                    }
                )
            )
            return
        config.validate_live_price()
        guard(args.protocol, args.protocol_sha256, config)
        reserve_configured_run(args.session_budget, config, directory / "run.json")
        gateway = BedrockGateway.open(config, allow_paid=True)
        adapter = ContractModelAdapter(gateway, min_interval_seconds=args.min_interval_seconds)

        def pinned(name, body):
            guard(args.protocol, args.protocol_sha256, config)
            try:
                return adapter(name, body)
            finally:
                guard(args.protocol, args.protocol_sha256, config)

        try:
            report = execute_development(
                data,
                provenance,
                gateway,
                directory,
                pinned,
                min_interval_seconds=args.min_interval_seconds,
                task=TASK,
                protocol_sha256=args.protocol_sha256,
            )
        finally:
            gateway.client.close()
        # An unchanged source is checked by the executor; pin the protocol itself too.
        try:
            guard(args.protocol, args.protocol_sha256, config)
        except ProtocolChanged:
            report.update(
                status="failed",
                results=None,
                observations=None,
                failure_kind="frozen_protocol_changed",
            )
            write_private_json(directory / "run.json", report)
            raise
    except Exception:
        raise SystemExit(
            "Frozen contract evaluation stopped; no complete result published"
        ) from None
    print(json.dumps({"status": report["status"], "protocol_sha256": args.protocol_sha256}))
    raise SystemExit(0 if report["status"] == "complete" else 1)


if __name__ == "__main__":
    main()
