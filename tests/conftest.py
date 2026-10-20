"""Freeze PostgreSQL execution provenance when tests run, not when reports are copied."""

import hashlib
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

from atlas.artifacts import write_private_json


def pytest_sessionstart(session):
    if not os.getenv("ATLAS_POSTGRES_CONFIG"):
        return
    source = hashlib.sha256()
    for file in sorted(Path("src").rglob("*.py")):
        source.update(str(file).encode())
        source.update(file.read_bytes())
    session._postgres_provenance = {
        "started_at": datetime.now(UTC).isoformat(),
        "source_sha256": source.hexdigest(),
        "test_file_sha256": hashlib.sha256(Path("tests/test_postgres.py").read_bytes()).hexdigest(),
        "hook_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "revision": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "working_tree_dirty": bool(
            subprocess.check_output(["git", "status", "--porcelain"], text=True).strip()
        ),
    }


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session, exitstatus):
    manifest = getattr(session, "_postgres_provenance", None)
    path = session.config.getoption("xmlpath", default=None)
    if manifest is None or path is None or not Path(path).exists():
        return
    manifest["completed_at"] = datetime.now(UTC).isoformat()
    manifest["exit_status"] = int(exitstatus)
    manifest["junit_sha256"] = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    write_private_json(Path("var/postgresql/run-manifest.json"), manifest)
