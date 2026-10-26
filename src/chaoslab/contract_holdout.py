"""A frozen protocol gates test-split access; saved test responses replay independently.

This protects against accidental drift, not a local owner able to rewrite code,
protocol and expected checksum. No provider or ATLAS import is needed for replay.
"""

import argparse
import hashlib
import json
import os
import stat
from datetime import UTC, datetime
from pathlib import Path

from .artifacts import publish_report
from .contract_journal import (
    canonical,
    finite_float,
    invalid_constant,
    read_observations,
    unique_object,
)
from .contractnli import (
    ARCHIVE_SHA256,
    _load_split,
    adapter_input,
    always_not_mentioned,
    evaluate,
    load_development,
)
from .execution import AdapterFailure

TASK = "contractnli-test-v1"
MEMBER = "contract-nli/test.json"
POLICY = {
    "selection": "Every test contract and fixed claim, in archive order; no filtering by answer or score",
    "primary": "macro_label_f1",
    "secondary": [
        "label_accuracy",
        "joint_label_and_exact_evidence",
        "evidence_micro_precision",
        "evidence_micro_recall",
        "per_class",
        "confusion",
    ],
    "reference": "constant NotMentioned with no evidence",
    "missing": "Keep every omitted claim in the denominator",
    "invalid_completed_response": "Count every claim in the document as failed; no retry",
    "provider_or_usage_failure": "Stop, preserve the reservation and incomplete journal; publish no cohort accuracy",
    "tuning": "No prompt, model, thresholds, schema or scorer changes after test exposure",
    "limits": "Public NDA annotations may be in pretraining. Not RFP accuracy, legal validation or evidence of unseen private-domain performance.",
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def bounded_json(path, *, private=False):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_size > 2_000_000
            or (private and info.st_mode & 0o077)
        ):
            raise ValueError("Protocol input must be regular, bounded and appropriately private")
        raw = stream.read(2_000_001)
    if len(raw) > 2_000_000:
        raise ValueError("Protocol input byte budget exceeded")
    return json.loads(
        raw,
        object_pairs_hook=unique_object,
        parse_float=finite_float,
        parse_constant=invalid_constant,
    ), sha(raw)


def scorer_files():
    root = Path(__file__).resolve().parent
    paths = sorted(root.glob("*.py"))
    if not paths or len(paths) > 128:
        raise ValueError("Scorer file budget exceeded")
    result = {}
    for path in paths:
        if path.is_symlink() or path.stat().st_size > 2_000_000:
            raise ValueError("Invalid scorer source")
        result[path.name] = sha(path.read_bytes())
    return result


def replay_result(data, provenance, observations, *, task):
    header, records, receipt = read_observations(
        observations,
        dataset=provenance,
        inputs={d["id"]: adapter_input(d, data["labels"], task=task) for d in data["documents"]},
        task=task,
    )

    def saved(_, body):
        record = records[body["document"]["id"]]
        if record["status"] == "failed":
            raise AdapterFailure("Saved invocation failure")
        return record["output"]

    return evaluate(data, header["adapter"], invoke_adapter=saved, task=task), receipt


def freeze(archive, development_report, observations, recipe, output):
    """Replay admitted development answers, then create a new protocol. Never read test JSON."""
    target = Path(output).absolute()
    if not target.resolve().is_relative_to(Path("var").resolve()) or target.is_symlink():
        raise ValueError("Choose a new private protocol under var")
    before = scorer_files()
    data, provenance = load_development(archive)
    report, report_sha = bounded_json(development_report)
    result, receipt = replay_result(
        data, provenance, observations, task="contractnli-development-v1"
    )
    if (
        not isinstance(report, dict)
        or report.get("dataset") != provenance
        or report.get("results") != result
        or report.get("observations") != receipt
        or report.get("replay_matches_recorded_results") is not True
    ):
        raise ValueError("A complete independently replayed development report is required")
    protocol = {
        "schema_version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "task": TASK,
        "archive_sha256": ARCHIVE_SHA256,
        "member": MEMBER,
        "development_report_sha256": report_sha,
        "development_observations_sha256": receipt["sha256"],
        "scorer_files": before,
        "recipe": recipe,
        "policy": POLICY,
    }
    if scorer_files() != before:
        raise ValueError("Scorer changed during freeze")
    raw = canonical(protocol) + b"\n"
    if len(raw) > 2_000_000:
        raise ValueError("Protocol byte budget exceeded")
    target.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    fd = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    return sha(raw)


def check_protocol(path, expected_sha256):
    protocol, fingerprint = bounded_json(path)
    if (
        not isinstance(protocol, dict)
        or not isinstance(expected_sha256, str)
        or fingerprint != expected_sha256
        or len(expected_sha256) != 64
        or set(protocol)
        != {
            "schema_version",
            "created_at",
            "task",
            "archive_sha256",
            "member",
            "development_report_sha256",
            "development_observations_sha256",
            "scorer_files",
            "recipe",
            "policy",
        }
        or type(protocol["schema_version"]) is not int
        or protocol["schema_version"] != 1
        or protocol["task"] != TASK
        or protocol["archive_sha256"] != ARCHIVE_SHA256
        or protocol["member"] != MEMBER
        or protocol["policy"] != POLICY
        or protocol["scorer_files"] != scorer_files()
    ):
        raise ValueError("Frozen protocol differs; test split was not read")
    return protocol


def load_test(archive, protocol_path, expected_sha256):
    check_protocol(protocol_path, expected_sha256)
    data, provenance = _load_split(archive, MEMBER, expected_sha256=ARCHIVE_SHA256)
    check_protocol(protocol_path, expected_sha256)
    return data, provenance


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True)
    parser.add_argument("--protocol", required=True)
    parser.add_argument("--protocol-sha256", required=True)
    parser.add_argument("--replay", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.output.resolve() in {
            Path(p).resolve() for p in (args.archive, args.protocol, args.replay)
        }:
            raise ValueError("Report cannot replace source evidence")
        data, provenance = load_test(args.archive, args.protocol, args.protocol_sha256)
        result, receipt = replay_result(data, provenance, args.replay, task=TASK)
        reference = evaluate(
            data,
            "chaoslab.contractnli:always_not_mentioned",
            invoke_adapter=lambda _, body: always_not_mentioned(body),
            task=TASK,
        )
        check_protocol(args.protocol, args.protocol_sha256)
        publish_report(
            args.output,
            {
                "recorded_at": datetime.now(UTC).isoformat(),
                "task": TASK,
                "dataset": provenance,
                "protocol_sha256": args.protocol_sha256,
                "results": result,
                "constant_not_mentioned_reference": reference,
                "observations": receipt,
                "mode": "saved test replay; no adapter import or provider calls",
                "limits": POLICY["limits"],
            },
        )
    except (ValueError, OSError):
        raise SystemExit("Frozen test replay rejected; no result published") from None
    print(
        json.dumps(
            {"documents": result["documents"], "claims": result["claims"], "provider_requests": 0}
        )
    )


if __name__ == "__main__":
    main()
