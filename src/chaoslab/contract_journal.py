"""Private, bounded observations for reproducible contract-task scoring."""

import hashlib
import json
import math
import os
import stat
from pathlib import Path

from .execution import MAX_OUTPUT_BYTES, validate_adapter

MAX_JOURNAL_BYTES = 128 * 1024 * 1024
MAX_LINE_BYTES = MAX_OUTPUT_BYTES + 16384


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def input_digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Ambiguous observation JSON")
        result[key] = value
    return result


def finite_float(value):
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("Non-finite observation number")
    return result


def invalid_constant(_):
    raise ValueError("Invalid observation constant")


class ObservationJournal:
    """Only the new run directory is writable; no raw observations enter reports."""

    def __init__(
        self, directory, *, dataset, adapter, scorer_sha256, task="contractnli-development-v1"
    ):
        if task not in {"contractnli-development-v1", "contractnli-test-v1"}:
            raise ValueError("Unsupported journal task")
        self.directory = Path(directory).resolve()
        if not self.directory.is_relative_to(Path("var").resolve()):
            raise ValueError("Observation directory must be new and under private var/")
        validate_adapter(adapter)
        self.directory.parent.mkdir(parents=True, exist_ok=True)
        self.directory.mkdir(mode=0o700)
        self.partial = self.directory / "observations.partial.jsonl"
        self.final = self.directory / "observations.jsonl"
        descriptor = os.open(
            self.partial, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
        )
        self.stream = os.fdopen(descriptor, "wb")
        self.digest, self.full_digest = hashlib.sha256(), hashlib.sha256()
        self.size, self.count = 0, 0
        self.header = {
            "kind": "header",
            "schema_version": 1,
            "task": task,
            "dataset": dataset,
            "adapter": adapter,
            "scorer_sha256": scorer_sha256,
        }
        try:
            self._write(self.header)
        except BaseException:
            self.close()
            raise

    def _write(self, value, *, body=True):
        raw = canonical(value) + b"\n"
        if len(raw) > MAX_LINE_BYTES or self.size + len(raw) > MAX_JOURNAL_BYTES:
            raise ValueError("Observation journal byte budget exceeded")
        self.stream.write(raw)
        self.stream.flush()
        os.fsync(self.stream.fileno())
        self.size += len(raw)
        self.full_digest.update(raw)
        if body:
            self.digest.update(raw)

    def record(self, value):
        if not isinstance(value, dict) or set(value) != {
            "document_id",
            "input_sha256",
            "status",
            "output",
        }:
            raise ValueError("Invalid private observation record")
        self._write({"kind": "observation", **value})
        self.count += 1

    def finish(self):
        self._write(
            {"kind": "complete", "records": self.count, "body_sha256": self.digest.hexdigest()},
            body=False,
        )
        self.close()
        os.replace(self.partial, self.final)
        descriptor = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        return {
            "sha256": self.full_digest.hexdigest(),
            "records": self.count,
            "origin_scorer_sha256": self.header["scorer_sha256"],
        }

    def close(self):
        self.stream.close()


def read_observations(path, *, dataset, inputs, task="contractnli-development-v1"):
    """Admit a complete saved run without importing or calling its adapter."""
    if task not in {"contractnli-development-v1", "contractnli-test-v1"}:
        raise ValueError("Unsupported journal task")
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as source:
            info = os.fstat(source.fileno())
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_mode & 0o077
                or info.st_size > MAX_JOURNAL_BYTES
            ):
                raise ValueError
            digest, full_digest, records, header, footer, size = (
                hashlib.sha256(),
                hashlib.sha256(),
                {},
                None,
                None,
                0,
            )
            while raw := source.readline(MAX_LINE_BYTES + 1):
                size += len(raw)
                if (
                    len(raw) > MAX_LINE_BYTES
                    or size > MAX_JOURNAL_BYTES
                    or not raw.endswith(b"\n")
                    or footer is not None
                ):
                    raise ValueError
                value = json.loads(
                    raw,
                    object_pairs_hook=unique_object,
                    parse_constant=invalid_constant,
                    parse_float=finite_float,
                )
                if not isinstance(value, dict):
                    raise ValueError
                full_digest.update(raw)
                if header is None:
                    if (
                        set(value)
                        != {"kind", "schema_version", "task", "dataset", "adapter", "scorer_sha256"}
                        or value["kind"] != "header"
                        or type(value["schema_version"]) is not int
                        or value["schema_version"] != 1
                        or value["task"] != task
                        or value["dataset"] != dataset
                    ):
                        raise ValueError
                    validate_adapter(value["adapter"])
                    fingerprint = value["scorer_sha256"]
                    if (
                        not isinstance(fingerprint, str)
                        or len(fingerprint) != 64
                        or any(c not in "0123456789abcdef" for c in fingerprint)
                    ):
                        raise ValueError
                    header = value
                elif value.get("kind") == "complete":
                    if (
                        set(value) != {"kind", "records", "body_sha256"}
                        or type(value["records"]) is not int
                        or value["records"] != len(records)
                        or value["body_sha256"] != digest.hexdigest()
                    ):
                        raise ValueError
                    footer = value
                    continue
                else:
                    if (
                        set(value) != {"kind", "document_id", "input_sha256", "status", "output"}
                        or value["kind"] != "observation"
                    ):
                        raise ValueError
                    identifier = value["document_id"]
                    if (
                        type(identifier) is not int
                        or identifier not in inputs
                        or identifier in records
                        or value["input_sha256"] != input_digest(inputs[identifier])
                        or value["status"] not in {"returned", "failed"}
                        or (value["status"] == "failed" and value["output"] is not None)
                    ):
                        raise ValueError
                    records[identifier] = value
                digest.update(raw)
            if header is None or footer is None or set(records) != set(inputs):
                raise ValueError
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        raise ValueError("Private contract observations rejected") from None
    return (
        header,
        records,
        {
            "sha256": full_digest.hexdigest(),
            "records": len(records),
            "origin_scorer_sha256": header["scorer_sha256"],
        },
    )
