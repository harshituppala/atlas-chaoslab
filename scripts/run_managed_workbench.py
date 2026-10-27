"""Single-instance process supervision; local preparation, not hosted acceptance."""

import argparse
import json
import os
import signal
import stat
import subprocess
import sys
import time
from pathlib import Path

from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

from atlas.managed import read_settings
from atlas.security.login import unique_object


class ConfigurationError(ValueError):
    pass


def settings(path):
    """No credential fallback, owner login, model configuration or inherited AWS access."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_size > 16384:
                raise ValueError
            raw = stream.read(16385)
            if len(raw) > 16384:
                raise ValueError
            value = json.loads(raw, object_pairs_hook=unique_object)
        if not isinstance(value, dict) or set(value) != {
            "api_database",
            "worker_database",
            "login_settings",
        }:
            raise ValueError
        urls = [make_url(value[k]) for k in ("api_database", "worker_database")]
        for url in urls:
            if not (
                url.drivername == "postgresql+psycopg"
                and url.username
                and url.password
                and url.host
                and url.database
                and url.query.get("sslmode") == "verify-full"
            ):
                raise ValueError
        api, worker = urls
        if (api.host, api.port, api.database) != (worker.host, worker.port, worker.database):
            raise ValueError
        if api.username == worker.username:
            raise ValueError
        login = Path(value["login_settings"])
        if not login.is_absolute():
            raise ValueError
        read_settings(login)
        return value
    except (OSError, ValueError, TypeError, KeyError, UnicodeError, RecursionError, ArgumentError):
        raise ConfigurationError(
            "Use private runtime settings with separate PostgreSQL logins and verified TLS"
        ) from None


def environments(config, inherited):
    # Explicit allowlist: never inherit the other service credential, demo/model
    # switches, AWS credentials, proxy settings or arbitrary application settings.
    base = {
        k: inherited[k]
        for k in ("PATH", "PYTHONPATH", "LANG", "SSL_CERT_FILE", "SSL_CERT_DIR")
        if k in inherited
    }
    base["PYTHONDONTWRITEBYTECODE"] = "1"
    api = {
        **base,
        "ATLAS_DATABASE_URL": config["api_database"],
        "ATLAS_LOGIN_SETTINGS": config["login_settings"],
    }
    worker = {
        **base,
        "ATLAS_DATABASE_URL": config["worker_database"],
        "ATLAS_ENABLE_BEDROCK_JOBS": "0",
    }
    return api, worker


def terminate_groups(children, grace):
    # Signal each service group even if its original leader exited. Processes
    # that start another session are outside this process-group boundary; a
    # hosted container must independently verify whole-container cleanup.
    def send(sig):
        for child in children:
            try:
                os.killpg(child.pid, sig)
            except ProcessLookupError:
                pass

    send(signal.SIGTERM)
    deadline = time.monotonic() + grace
    while any(p.poll() is None for p in children) and time.monotonic() < deadline:
        time.sleep(0.02)
    send(signal.SIGKILL)
    for child in children:
        child.wait()


def supervise(
    commands, envs, *, grace=10, poll_interval=0.1, worker_progress_timeout=None, api_pass_fds=()
):
    """Either child exit is terminal; no hidden automatic restart or paid replay."""
    stopping = False
    children = []
    progress_read = progress_write = None
    if worker_progress_timeout is not None:
        if not 0 < worker_progress_timeout <= 600 or len(commands) != 2:
            raise ValueError("Invalid worker progress deadline")
        progress_read, progress_write = os.pipe()
        os.set_blocking(progress_read, False)
    last_progress = time.monotonic()

    def stop(*_):
        nonlocal stopping
        stopping = True

    previous = {sig: signal.signal(sig, stop) for sig in (signal.SIGTERM, signal.SIGINT)}
    try:
        for index, (command, env) in enumerate(zip(commands, envs, strict=True)):
            if stopping:
                return 0
            kwargs = {}
            if index == 0 and api_pass_fds:
                kwargs["pass_fds"] = api_pass_fds
            if index == 1 and progress_write is not None:
                command = [*command, "--progress-fd", str(progress_write)]
                kwargs["pass_fds"] = (progress_write,)
            children.append(subprocess.Popen(command, env=env, start_new_session=True, **kwargs))
            if index == 1 and progress_write is not None:
                os.close(progress_write)
                progress_write = None
        while not stopping:
            if any(child.poll() is not None for child in children):
                return 1
            if progress_read is not None:
                try:
                    progress = os.read(progress_read, 4096)
                except BlockingIOError:
                    progress = None
                if progress is not None:
                    if not progress or any(value != ord(".") for value in progress):
                        return 1
                    last_progress = time.monotonic()
                if time.monotonic() - last_progress > worker_progress_timeout:
                    print("Worker stopped making progress; stopping the workbench", file=sys.stderr)
                    return 1
            time.sleep(poll_interval)
        return 0
    finally:
        try:
            terminate_groups(children, grace)
        finally:
            for descriptor in (progress_read, progress_write):
                if descriptor is not None:
                    os.close(descriptor)
            for sig, handler in previous.items():
                signal.signal(sig, handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--settings", required=True)
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("Choose an unprivileged port")
    try:
        config = settings(args.settings)
        envs = environments(config, os.environ)
        commands = [
            [
                sys.executable,
                "-m",
                "uvicorn",
                "atlas.managed:create_from_environment",
                "--factory",
                "--host",
                "127.0.0.1",
                "--port",
                str(args.port),
                "--no-access-log",
                "--no-proxy-headers",
            ],
            [sys.executable, str(Path(__file__).with_name("run_managed_worker.py"))],
        ]
        return supervise(commands, envs, worker_progress_timeout=150)
    except (ConfigurationError, OSError):
        print(
            "Managed workbench failed to start; check private operator configuration",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
