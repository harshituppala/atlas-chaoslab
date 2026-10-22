"""Development-split contract inference checks against external annotations.

Raw contracts stay local. This is a different task from RFP extraction, and the
included constant-label baseline is not an AI model or a legal assessment.
"""

import argparse
import hashlib
import json
import os
import stat
import time
import zipfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from .__main__ import source_digest
from .artifacts import publish_report
from .contract_journal import ObservationJournal, input_digest, read_observations
from .execution import AdapterFailure, invoke, validate_adapter

ARCHIVE_SHA256 = "e03fc77bbf8b53e2976a250e81d8a294bc3d5e5fb014521e477dee9340d6287b"
MEMBER = "contract-nli/dev.json"
CHOICES = ("Entailment", "Contradiction", "NotMentioned")
MAX_ARCHIVE = 128 * 1024 * 1024
MAX_MEMBER = 16 * 1024 * 1024


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate dataset member")
        result[key] = value
    return result


def invalid_number(_):
    raise ValueError("Invalid dataset constant")


def file_digest(stream):
    stream.seek(0)
    digest, size = hashlib.sha256(), 0
    while block := stream.read(1024 * 1024):
        size += len(block)
        if size > MAX_ARCHIVE:
            raise ValueError("Archive exceeds byte budget")
        digest.update(block)
    return digest.hexdigest()


def require(condition):
    if not condition:
        raise ValueError("Invalid ContractNLI development annotations")


def validate_development(data):
    try:
        require(isinstance(data, dict))
        labels, documents = data["labels"], data["documents"]
        require(isinstance(labels, dict) and 1 <= len(labels) <= 128)
        require(isinstance(documents, list) and 1 <= len(documents) <= 1000)
        for key, value in labels.items():
            require(isinstance(key, str) and 1 <= len(key) <= 128)
            require(isinstance(value, dict) and isinstance(value["hypothesis"], str))
            require(1 <= len(value["hypothesis"].encode()) <= 8192)
        ids = set()
        for document in documents:
            require(isinstance(document, dict))
            identifier, text, spans = document["id"], document["text"], document["spans"]
            require(type(identifier) is int and identifier >= 0 and identifier not in ids)
            ids.add(identifier)
            require(isinstance(text, str) and 1 <= len(text.encode()) <= 1_000_000)
            require(isinstance(spans, list) and 1 <= len(spans) <= 10000)
            for span in spans:
                require(isinstance(span, list) and len(span) == 2)
                start, end = span
                require(type(start) is type(end) is int and 0 <= start < end <= len(text))
            sets = document["annotation_sets"]
            require(isinstance(sets, list) and len(sets) == 1)
            annotations = sets[0]["annotations"]
            require(isinstance(annotations, dict) and set(annotations) == set(labels))
            for annotation in annotations.values():
                require(isinstance(annotation, dict) and annotation["choice"] in CHOICES)
                evidence = annotation["spans"]
                require(isinstance(evidence, list) and len(evidence) <= len(spans))
                require(all(type(index) is int and 0 <= index < len(spans) for index in evidence))
                require(len(set(evidence)) == len(evidence))
                require((annotation["choice"] == "NotMentioned") == (not evidence))
    except (ValueError, KeyError, TypeError, UnicodeError):
        raise ValueError("Invalid ContractNLI development annotations") from None


def load_development(path, *, expected_sha256=ARCHIVE_SHA256):
    """Read one fixed member in place; never extract archive-supplied paths."""
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_ARCHIVE:
                raise ValueError
            before = file_digest(stream)
            if before != expected_sha256:
                raise ValueError
            stream.seek(0)
            with zipfile.ZipFile(stream) as archive:
                members = archive.infolist()
                selected = [member for member in members if member.filename == MEMBER]
                if len(members) > 10000 or len(selected) != 1:
                    raise ValueError
                member = selected[0]
                if (
                    member.file_size > MAX_MEMBER
                    or member.is_dir()
                    or stat.S_ISLNK(member.external_attr >> 16)
                    or member.flag_bits & 1
                ):
                    raise ValueError
                with archive.open(member) as source:
                    raw = source.read(MAX_MEMBER + 1)
                if len(raw) > MAX_MEMBER:
                    raise ValueError
            if file_digest(stream) != before:
                raise ValueError
        data = json.loads(raw, object_pairs_hook=unique_object, parse_constant=invalid_number)
        validate_development(data)
    except (
        OSError,
        ValueError,
        TypeError,
        RecursionError,
        KeyError,
        zipfile.BadZipFile,
        RuntimeError,
    ):
        raise ValueError("ContractNLI archive or development split rejected") from None
    return data, {
        "archive_sha256": before,
        "member": MEMBER,
        "member_sha256": hashlib.sha256(raw).hexdigest(),
    }


def adapter_input(document, labels):
    return {
        "task": "contractnli-development-v1",
        "document": {
            "id": document["id"],
            "text": document["text"],
            "spans": [list(s) for s in document["spans"]],
        },
        "hypotheses": [{"id": key, "text": value["hypothesis"]} for key, value in labels.items()],
    }


def always_not_mentioned(inputs, fault=None):
    """Constant-label reference; it retrieves no evidence and performs no reasoning."""
    return {
        "predictions": [
            {"id": item["id"], "choice": "NotMentioned", "spans": []}
            for item in inputs["hypotheses"]
        ]
    }


def predictions(output, labels, span_count):
    if not isinstance(output, dict) or set(output) != {"predictions"}:
        raise ValueError("Invalid prediction envelope")
    items = output["predictions"]
    if not isinstance(items, list) or len(items) > len(labels):
        raise ValueError("Invalid predictions")
    result = {}
    for item in items:
        if not isinstance(item, dict) or set(item) != {"id", "choice", "spans"}:
            raise ValueError("Invalid prediction")
        identifier, choice, spans = item["id"], item["choice"], item["spans"]
        if (
            not isinstance(identifier, str)
            or identifier not in labels
            or identifier in result
            or choice not in CHOICES
        ):
            raise ValueError("Invalid prediction identity or choice")
        if not isinstance(spans, list) or len(spans) > span_count:
            raise ValueError("Invalid predicted evidence")
        if any(type(index) is not int or not 0 <= index < span_count for index in spans) or len(
            set(spans)
        ) != len(spans):
            raise ValueError("Invalid predicted evidence")
        if choice == "NotMentioned" and spans:
            raise ValueError("NotMentioned predictions must have no evidence")
        result[identifier] = item
    return result


def evaluate(data, adapter, *, invoke_adapter=invoke, observer=None):
    validate_adapter(adapter)
    validate_development(data)
    labels = data["labels"]
    confusion = {choice: Counter() for choice in CHOICES}
    failures, missing, joint, exact, eligible, overlap, predicted_spans, expected_spans = (0,) * 8
    for document in data["documents"]:
        inputs = adapter_input(document, labels)
        record = {
            "document_id": document["id"],
            "input_sha256": input_digest(inputs),
            "status": "failed",
            "output": None,
        }
        try:
            output = invoke_adapter(adapter, inputs)
            record.update(status="returned", output=output)
            observed = predictions(output, labels, len(document["spans"]))
            failure = False
        except (AdapterFailure, ValueError):
            failures += 1
            observed, failure = {}, True
        # Recording failures must abort publication, not become adapter failures.
        if observer is not None:
            observer(record)
        for key, expected in document["annotation_sets"][0]["annotations"].items():
            item = observed.get(key)
            predicted = item["choice"] if item else ("failed" if failure else "missing")
            missing += int(item is None and not failure)
            confusion[expected["choice"]][predicted] += 1
            wanted, chosen = set(expected["spans"]), set(item["spans"]) if item else set()
            evidence_equal = item is not None and wanted == chosen
            joint += int(predicted == expected["choice"] and evidence_equal)
            # ContractNLI defines evidence identification only for non-neutral labels.
            if expected["choice"] != "NotMentioned":
                eligible += 1
                exact += int(evidence_equal)
                overlap += len(wanted & chosen)
                expected_spans += len(wanted)
                predicted_spans += len(chosen)
    claims = len(labels) * len(data["documents"])
    correct = sum(confusion[label][label] for label in CHOICES)
    per_class = {}
    for label in CHOICES:
        tp = confusion[label][label]
        support = sum(confusion[label].values())
        fp = sum(confusion[other][label] for other in CHOICES if other != label)
        fn = support - tp
        per_class[label] = {
            "support": support,
            "correct": tp,
            "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0.0,
        }
    return {
        "documents": len(data["documents"]),
        "claims": claims,
        "failed_documents": failures,
        "missing_predictions": missing,
        "label_accuracy": correct / claims,
        "macro_label_f1": sum(item["f1"] for item in per_class.values()) / len(CHOICES),
        "joint_label_and_exact_evidence": joint / claims,
        "per_class": per_class,
        "confusion": {key: dict(value) for key, value in confusion.items()},
        "evidence": {
            "eligible_claims": eligible,
            "exact_sets": exact,
            "matched_spans": overlap,
            "predicted_spans": predicted_spans,
            "expected_spans": expected_spans,
            "micro_precision": overlap / predicted_spans if predicted_spans else None,
            "micro_recall": overlap / expected_spans if expected_spans else None,
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--adapter", help="Explicit trusted module:function")
    mode.add_argument(
        "--replay", type=Path, help="Private complete observations; invokes no adapter"
    )
    parser.add_argument("--journal", type=Path, help="New observation directory under private var/")
    parser.add_argument("--output", type=Path, default=Path("var/contractnli-development.json"))
    args = parser.parse_args()
    try:
        if args.replay is not None and args.journal is not None:
            raise ValueError("Replay cannot create an observation journal")
        if args.adapter is not None:
            validate_adapter(args.adapter)
        if args.replay is not None and args.output.resolve() == args.replay.resolve():
            raise ValueError("Report cannot replace its saved observations")
        if args.journal is not None and args.output.resolve().is_relative_to(
            args.journal.resolve()
        ):
            raise ValueError("Keep reports outside the private observation directory")
        if args.output.resolve() == Path(args.archive).resolve():
            raise ValueError("Report cannot replace its dataset archive")
        before = source_digest()
        data, provenance = load_development(args.archive)
        started = time.perf_counter()
        observations = None
        adapter = args.adapter
        if args.replay is not None:
            inputs = {d["id"]: adapter_input(d, data["labels"]) for d in data["documents"]}
            header, records, observations = read_observations(
                args.replay, dataset=provenance, inputs=inputs
            )
            adapter = header["adapter"]

            def replay(_, value):
                record = records[value["document"]["id"]]
                if record["status"] == "failed":
                    raise AdapterFailure("Saved adapter failure")
                return record["output"]

            result = evaluate(data, adapter, invoke_adapter=replay)
        elif args.journal is not None:
            journal = ObservationJournal(
                args.journal, dataset=provenance, adapter=adapter, scorer_sha256=before
            )
            try:
                result = evaluate(data, adapter, observer=journal.record)
                if source_digest() != before:
                    raise ValueError("Scorer source changed; observations remain incomplete")
                observations = journal.finish()
            finally:
                journal.close()
        else:
            result = evaluate(data, adapter)
        elapsed = time.perf_counter() - started
        if source_digest() != before:
            raise ValueError("Scorer source changed; report refused")
        publish_report(
            args.output,
            {
                "recorded_at": datetime.now(UTC).isoformat(),
                "task": "ContractNLI development inference and evidence identification",
                "source": "https://stanfordnlp.github.io/contract-nli/",
                "citation": "Yuta Koreeda and Christopher D. Manning. ContractNLI. Findings of EMNLP 2021.",
                "license": "CC BY 4.0; original license and terms retained with private archive",
                "split": "development; complete split, no model-based case selection",
                "dataset": provenance,
                "scorer_sha256": before,
                "adapter": adapter,
                "mode": "replay" if args.replay is not None else "adapter-run",
                "observations": observations,
                "results": result,
                "evaluation_wall_seconds": elapsed,
                "timing_scope": (
                    "Read-only observation admission and scoring; no adapter execution or model calls."
                    if args.replay is not None
                    else "Sequential adapter child-process startup, optional private journaling and scoring; excludes archive loading and download. Not model request latency."
                ),
                "limits": "Externally authored NDA annotations, not RFP accuracy or legal validation. Public data may be present in model pretraining. Evidence metrics exclude NotMentioned gold labels; undefined precision/recall are null. Malformed/failed document outputs count against all their claims; omissions remain missing. Trusted adapters retain filesystem/network permissions. External adapter code is not covered by the packaged scorer digest. No raw contract text or predictions are published here.",
            },
        )
    except (ValueError, OSError) as error:
        raise SystemExit(str(error)) from None
    print(
        json.dumps(
            {
                "documents": result["documents"],
                "claims": result["claims"],
                "report": str(args.output),
            }
        )
    )


if __name__ == "__main__":
    main()
