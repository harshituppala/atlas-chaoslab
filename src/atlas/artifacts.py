"""Private atomic local artifacts, including an invocation reservation journal."""

import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4


def sync_directory(path):
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def durable_directory(path):
    missing = []
    current = path
    while not current.exists():
        missing.append(current)
        current = current.parent
    for directory in reversed(missing):
        directory.mkdir(mode=0o700, exist_ok=True)
        sync_directory(directory.parent)


def reserve_invocation_artifacts(output: Path):
    """Never overwrite a previous or concurrent run's potentially uncertain billing.

    The reservation intentionally survives process death. Use a new output name
    for another run; manual reconciliation is required for an interrupted run.
    """
    journal = output.with_suffix(".ledger.json")
    reservation = output.with_suffix(".reservation.json")
    durable_directory(output.parent)
    if output.exists() or journal.exists():
        raise FileExistsError("Invocation artifacts already exist; choose a new output name")
    descriptor = os.open(reservation, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(
            {"invocation_id": uuid4().hex, "reserved_at": datetime.now(UTC).isoformat()}, handle
        )
        handle.flush()
        os.fsync(handle.fileno())
    sync_directory(output.parent)
    # A preexisting non-cooperating writer must not be silently overwritten either.
    if output.exists() or journal.exists():
        raise FileExistsError("Invocation artifacts appeared during reservation")
    return journal


def write_private_json(path: Path, payload):
    durable_directory(path.parent)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False
        ) as handle:
            temporary = Path(handle.name)
            json.dump(payload, handle, indent=2, default=str, allow_nan=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        sync_directory(path.parent)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
