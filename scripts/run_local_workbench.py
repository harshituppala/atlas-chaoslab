"""Start the private local API and baseline worker together. No cloud credentials."""

import argparse
import fcntl
import json
import os
import re
import secrets
import socket
import stat
import sys
from contextlib import contextmanager
from pathlib import Path

from run_managed_workbench import supervise

from atlas.security.login import unique_object
from atlas.store import Store

ROOT = Path(__file__).resolve().parents[1]
PRINCIPAL = {"tenant": "local-review", "actor": "local-reviewer", "role": "reviewer"}


class LocalSetupError(ValueError):
    pass


def private_file(path, *, create=False, maximum=16384):
    flags = os.O_NOFOLLOW | os.O_NONBLOCK | os.O_RDWR
    if create:
        flags |= os.O_CREAT
    fd = os.open(path, flags, 0o600)
    info = os.fstat(fd)
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_mode & 0o077
        or info.st_uid != os.getuid()
        or (maximum is not None and info.st_size > maximum)
    ):
        os.close(fd)
        raise LocalSetupError("Local settings must be private regular files owned by this user")
    return fd


def credentials(workspace):
    path = workspace / "credentials.json"
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    except FileExistsError:
        pass
    else:
        with os.fdopen(descriptor, "w") as stream:
            json.dump({secrets.token_urlsafe(32): PRINCIPAL}, stream)
            stream.flush()
            os.fsync(stream.fileno())
    with os.fdopen(private_file(path), "rb") as stream:
        value = json.loads(stream.read(16385), object_pairs_hook=unique_object)
    if (
        not isinstance(value, dict)
        or len(value) != 1
        or not re.fullmatch(r"[A-Za-z0-9_-]{40,100}", next(iter(value)), flags=re.ASCII)
        or next(iter(value.values())) != PRINCIPAL
    ):
        raise LocalSetupError("Local credential file is invalid; existing settings were retained")
    return json.dumps(value)


@contextmanager
def prepare(workspace):
    workspace = Path(workspace).resolve()
    if not workspace.is_relative_to(ROOT / "var"):
        raise LocalSetupError("Keep the local workspace inside this repository's var directory")
    workspace.mkdir(parents=True, exist_ok=True, mode=0o700)
    info = workspace.stat()
    if info.st_mode & 0o077 or info.st_uid != os.getuid():
        raise LocalSetupError("Use a private workspace owned by this user")
    lock = private_file(workspace / "launcher.lock", create=True)
    try:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise LocalSetupError("This workspace already has a running launcher") from None
        principals = credentials(workspace)
        database = workspace / "review.db"
        if database.is_symlink():
            raise LocalSetupError("The workspace database must not be a symbolic link")
        if database.exists():
            descriptor = private_file(database, maximum=None)
            os.close(descriptor)
        database_url = "sqlite:///" + str(database)
        store = Store(database_url)
        store.engine.dispose()
        tmp = workspace / "tmp"
        if tmp.is_symlink():
            raise LocalSetupError("The temporary directory must not be a symbolic link")
        tmp.mkdir(exist_ok=True, mode=0o700)
        if tmp.stat().st_mode & 0o077 or tmp.stat().st_uid != os.getuid():
            raise LocalSetupError("Use a private temporary directory owned by this user")
        base = {key: os.environ[key] for key in ("PATH", "LANG") if key in os.environ}
        base.update(
            PYTHONPATH=str(ROOT / "src"),
            PYTHONDONTWRITEBYTECODE="1",
            TMPDIR=str(tmp),
            TMP=str(tmp),
            TEMP=str(tmp),
            ATLAS_DATABASE_URL=database_url,
        )
        yield (
            workspace,
            ({**base, "ATLAS_PRINCIPALS": principals}, {**base, "ATLAS_ENABLE_BEDROCK_JOBS": "0"}),
        )
    finally:
        os.close(lock)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=ROOT / "var/local-workbench")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("Choose an unprivileged port between 1024 and 65535")
    if not (ROOT / "apps/web/dist/index.html").is_file():
        parser.error("Build the interface first with make web")
    try:
        # Keep this socket open through startup. The child inherits this exact
        # listener, so it cannot silently connect the user to another service.
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(("127.0.0.1", args.port))
            listener.listen(128)
            with prepare(args.workspace) as (workspace, envs):
                commands = [
                    [
                        sys.executable,
                        "-m",
                        "uvicorn",
                        "atlas.api:create_app",
                        "--factory",
                        "--fd",
                        str(listener.fileno()),
                        "--no-access-log",
                        "--no-proxy-headers",
                    ],
                    [sys.executable, str(ROOT / "scripts/run_managed_worker.py")],
                ]
                print(f"Starting ATLAS at http://127.0.0.1:{args.port}", flush=True)
                print(f"Reviewer token file: {workspace / 'credentials.json'}", flush=True)
                print(
                    "Open the file privately before recording. Ctrl+C stops both services; saved work stays.",
                    flush=True,
                )
                return supervise(
                    commands, envs, worker_progress_timeout=150, api_pass_fds=(listener.fileno(),)
                )
    except (LocalSetupError, OSError, ValueError):
        print(
            "Local startup refused. Check the port, private workspace and credential file; no settings were reset.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
