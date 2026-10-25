"""Prepare a committed source-only publication candidate; never publish or copy history.

Read HEAD instead of the working tree/index so staged owner documents, private
runtime data and unrelated edits cannot enter the candidate. Pattern checks are
an additional heuristic, not a comprehensive secret or licensing audit.
"""

import hashlib
import io
import json
import re
import subprocess
import tarfile
from pathlib import Path, PurePosixPath
from uuid import uuid4

ROOT_FILES = {
    "README.md",
    "Makefile",
    "Dockerfile",
    "Dockerfile.lab",
    "compose.yaml",
    "pyproject.toml",
    "requirements.lock",
    "requirements-embeddings.lock",
    ".gitignore",
    ".dockerignore",
}
ROOT_DIRS = {
    "src",
    "tests",
    "scripts",
    "datasets",
    "reports",
    "deployment",
    "apps",
    ".github",
    "docs",
}
PRIVATE_PARTS = {
    "var",
    ".git",
    ".runtime",
    ".cache",
    ".aws",
    "node_modules",
    "dist",
    "dist-replay",
    "dist-lab",
    "__pycache__",
}
PRIVATE_FILES = {"docs/interview-practice.md", "docs/portfolio-delivery.md"}
KEY_PATTERNS = [
    re.compile(rb"(?:AKIA|ASIA)[A-Z0-9]{16}"),
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(rb"arn:aws:[^\s\"']*:\d{12}:"),
]


def allowed(name):
    path = PurePosixPath(name)
    return (
        not path.is_absolute()
        and ".." not in path.parts
        and name not in PRIVATE_FILES
        and not PRIVATE_PARTS.intersection(path.parts)
        and not any(p.startswith(".env") for p in path.parts)
        and path.suffix not in {".pem", ".key", ".p12", ".pfx", ".db", ".sqlite", ".log", ".dump"}
        and (
            name in ROOT_FILES
            or len(path.parts) > 1
            and path.parts[0] in ROOT_DIRS
            or path.parts[:2] == ("examples", "review-regression")
            and len(path.parts) > 2
        )
    )


def main():
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    archive = subprocess.check_output(["git", "archive", "--format=tar", "HEAD"])
    export = Path("var/release") / (revision[:12] + "-" + uuid4().hex[:8])
    source = export / "source"
    source.mkdir(parents=True, mode=0o700)
    entries, omitted, total = {}, [], 0
    try:
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            for member in tar.getmembers():
                if member.isdir():
                    continue
                if not allowed(member.name):
                    omitted.append(member.name)
                    continue
                if not member.isfile():
                    raise ValueError("Publication candidate refuses symlinks and special files")
                total += member.size
                if total > 25_000_000 or len(entries) >= 1000:
                    raise ValueError("Publication file/byte budget exceeded")
                data = tar.extractfile(member).read()
                if any(pattern.search(data) for pattern in KEY_PATTERNS):
                    raise ValueError("Potential credential/account identifier: " + member.name)
                path = source / member.name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
                path.chmod(0o755 if member.mode & 0o111 else 0o644)
                entries[member.name] = hashlib.sha256(data).hexdigest()
        if not entries or any(not allowed(path) for path in entries):
            raise ValueError("Invalid publication candidate")
        manifest = {
            "source_revision": revision,
            "files": entries,
            "bytes": total,
            "excluded_committed_files": omitted,
            "history_included": False,
            "published": False,
            "scope": "Allowlisted committed HEAD files only; no working/index/private runtime files. Credential/account pattern scan is heuristic, not a comprehensive privacy, dependency-license or security audit.",
        }
        (export / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        (export / "manifest.json").chmod(0o600)
        subprocess.run(
            ["git", "init", "--initial-branch=main", str(source)], check=True, capture_output=True
        )
        subprocess.run(["git", "add", "."], cwd=source, check=True, capture_output=True)
        subprocess.run(
            [
                "git",
                "-c",
                "user.name=Codex",
                "-c",
                "user.email=codex@localhost",
                "commit",
                "-m",
                "Publish verified ATLAS and CHAOSLAB source snapshot",
            ],
            cwd=source,
            check=True,
            capture_output=True,
        )
        print(
            json.dumps(
                {
                    "candidate": str(source),
                    "source_revision": revision,
                    "files": len(entries),
                    "bytes": total,
                    "published": False,
                }
            )
        )
    except Exception:
        # Preserve a failed candidate for inspection; it must never be published.
        (export / "FAILED").write_text("Candidate preparation failed; do not publish.\n")
        raise


if __name__ == "__main__":
    main()
