"""Real process exit/signal controls; no provider, database or model execution."""

import importlib.util
import json
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/run_managed_workbench.py"
spec = importlib.util.spec_from_file_location("workbench_supervisor", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_credentials_are_separated_and_inherited_privilege_is_absent():
    api, worker = module.environments(
        {
            "api_database": "api-secret",
            "worker_database": "worker-secret",
            "login_settings": "/private/login.json",
        },
        {
            "PATH": "/bin",
            "AWS_SECRET_ACCESS_KEY": "secret",
            "ATLAS_DEMO": "1",
            "ATLAS_PRINCIPALS": "owner",
            "ATLAS_MODEL_JOB_SPEC": "paid",
            "HTTP_PROXY": "http://proxy",
            "ATLAS_DATABASE_URL": "owner-secret",
        },
    )
    assert api["ATLAS_DATABASE_URL"] == "api-secret"
    assert worker["ATLAS_DATABASE_URL"] == "worker-secret"
    assert "ATLAS_LOGIN_SETTINGS" not in worker
    assert worker["ATLAS_ENABLE_BEDROCK_JOBS"] == "0"
    assert all(
        "AWS" not in k
        and k not in {"HTTP_PROXY", "ATLAS_DEMO", "ATLAS_PRINCIPALS", "ATLAS_MODEL_JOB_SPEC"}
        for env in (api, worker)
        for k in env
    )
    assert "worker-secret" not in api.values() and "api-secret" not in worker.values()


def runtime_file(tmp_path, monkeypatch, **changes):
    monkeypatch.setattr(module, "read_settings", lambda path: None)
    value = {
        "api_database": "postgresql+psycopg://api:secret@db/atlas?sslmode=verify-full",
        "worker_database": "postgresql+psycopg://worker:secret@db/atlas?sslmode=verify-full",
        "login_settings": "/private/login.json",
    }
    value.update(changes)
    path = tmp_path / "runtime.json"
    path.write_text(json.dumps(value))
    path.chmod(0o600)
    return path


def test_valid_config_does_not_open_database(tmp_path, monkeypatch):
    assert (
        module.settings(runtime_file(tmp_path, monkeypatch))["login_settings"]
        == "/private/login.json"
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"worker_database": "postgresql+psycopg://api:secret@db/atlas?sslmode=verify-full"},
        {"worker_database": "postgresql+psycopg://worker:secret@other/atlas?sslmode=verify-full"},
        {"api_database": "sqlite:///local.db"},
        {"api_database": "not-a-database-url"},
        {"api_database": "postgresql+psycopg://api:secret@db/atlas?sslmode=require"},
        {"login_settings": "relative.json"},
        {"owner_database": "never-admit"},
    ],
)
def test_invalid_config_has_fixed_nonsecret_error(tmp_path, monkeypatch, changes):
    with pytest.raises(module.ConfigurationError) as error:
        module.settings(runtime_file(tmp_path, monkeypatch, **changes))
    assert "secret" not in str(error.value)


def test_public_or_symlink_config_refused(tmp_path, monkeypatch):
    path = runtime_file(tmp_path, monkeypatch)
    path.chmod(0o644)
    with pytest.raises(module.ConfigurationError):
        module.settings(path)
    path.chmod(0o600)
    link = tmp_path / "link"
    link.symlink_to(path)
    with pytest.raises(module.ConfigurationError):
        module.settings(link)


def wait_for(path, child):
    deadline = time.monotonic() + 5
    while not path.exists() and time.monotonic() < deadline:
        assert child.poll() is None
        time.sleep(0.02)
    assert path.exists()


@pytest.mark.parametrize("trigger", ["exit-zero", "exit-error", "term", "int"])
def test_real_pair_failure_and_operator_shutdown(tmp_path, trigger):
    # The harness imports the actual supervisor into a disposable child process.
    # Each stand-in writes its PID and records SIGTERM before stopping.
    child_code = "import os,signal,time;from pathlib import Path;p=Path(os.environ['MARK']);signal.signal(signal.SIGTERM,lambda *_:(p.with_suffix('.stopped').write_text('yes'),exit(0)));p.write_text(str(os.getpid()));time.sleep(60)"
    harness = tmp_path / "harness.py"
    commands = [[sys.executable, "-c", child_code]] * 2
    if trigger.startswith("exit"):
        # First child waits until its sibling is ready, then exits.
        commands[0] = [
            sys.executable,
            "-c",
            f"import time;from pathlib import Path;p=Path({str(tmp_path / 'b')!r});\nwhile not p.exists():time.sleep(.02)\nraise SystemExit({0 if trigger == 'exit-zero' else 2})",
        ]
    harness.write_text(
        f"import importlib.util; s=importlib.util.spec_from_file_location('s',{str(SCRIPT)!r});m=importlib.util.module_from_spec(s);s.loader.exec_module(m);raise SystemExit(m.supervise({commands!r},[{{'MARK':{str(tmp_path / 'a')!r}}},{{'MARK':{str(tmp_path / 'b')!r}}}],grace=.3,poll_interval=.02))"
    )
    child = subprocess.Popen(
        [sys.executable, str(harness)], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
    )
    try:
        wait_for(tmp_path / "b", child)
        if trigger in ("term", "int"):
            wait_for(tmp_path / "a", child)
            child.send_signal(signal.SIGTERM if trigger == "term" else signal.SIGINT)
        assert child.wait(timeout=5) == (1 if trigger.startswith("exit") else 0)
        assert (tmp_path / "b.stopped").exists()
        if trigger in ("term", "int"):
            assert (tmp_path / "a.stopped").exists()
    finally:
        if child.poll() is None:
            child.kill()
            child.wait()


def test_spawn_failure_stops_already_started_sibling(monkeypatch):
    class Child:
        pid = 987654

        def poll(self):
            return 0

        def wait(self):
            return 0

    first = Child()
    calls = []

    def spawn(*args, **kwargs):
        if calls:
            raise OSError("private details")
        calls.append(True)
        return first

    signals = []
    monkeypatch.setattr(module.subprocess, "Popen", spawn)
    monkeypatch.setattr(module.os, "killpg", lambda pid, sig: signals.append((pid, sig)))
    before = signal.getsignal(signal.SIGTERM)
    with pytest.raises(OSError):
        module.supervise([["api"], ["worker"]], [{}, {}], grace=0.01)
    assert signals == [(first.pid, signal.SIGTERM), (first.pid, signal.SIGKILL)]
    assert signal.getsignal(signal.SIGTERM) == before
