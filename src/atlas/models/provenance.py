"""Bounded on-disk source identity; not a signed execution attestation."""

import hashlib
import json
import platform
from pathlib import Path


def source_manifest(root=None):
    root = Path(root) if root is not None else Path(__file__).resolve().parents[3]
    paths = sorted((root / "src").rglob("*.py"))
    paths += [root / "requirements.lock", root / "pyproject.toml"]
    if not paths or len(paths) > 500:
        raise ValueError("Source manifest file budget exceeded")
    entries = {}
    total = 0
    for path in paths:
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            raise ValueError("Source manifest must stay within the source root")
        if path.stat().st_size > 8_000_000 - total:
            raise ValueError("Source manifest byte budget exceeded")
        data = path.read_bytes()
        total += len(data)
        if total > 8_000_000:
            raise ValueError("Source manifest byte budget exceeded")
        entries[path.relative_to(root).as_posix()] = hashlib.sha256(data).hexdigest()
    digest = hashlib.sha256(json.dumps(entries, sort_keys=True).encode()).hexdigest()
    return {
        "schema_version": 1,
        "files": entries,
        "source_sha256": digest,
        "python_version": platform.python_version(),
        "scope": "On-disk source and dependency-lock identity, not proof of loaded module bytes, installed dependencies or signed execution.",
    }
