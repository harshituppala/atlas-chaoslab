"""Private, persistent local startup must not reset credentials or inherit cloud settings."""

import importlib.util
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from test_workbench_supervisor import module as supervisor

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "local_workbench", ROOT / "scripts/run_local_workbench.py"
)
local = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, {"run_managed_workbench": supervisor}):
    spec.loader.exec_module(local)


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(local, "ROOT", tmp_path)
    return tmp_path / "var/local-workbench"


def test_restart_reuses_credentials_and_does_not_leak_privilege(workspace, monkeypatch):
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "must-not-inherit")
    monkeypatch.setenv("ATLAS_DATABASE_URL", "must-not-use")
    monkeypatch.setenv("ATLAS_PRINCIPALS", "must-not-use")
    monkeypatch.setenv("ATLAS_MODEL_JOB_SPEC", "must-not-use")
    with local.prepare(workspace) as (_, (api, worker)):
        original = (workspace / "credentials.json").read_bytes()
        assert json.loads(api["ATLAS_PRINCIPALS"]) == json.loads(original)
        assert "ATLAS_PRINCIPALS" not in worker
        assert worker["ATLAS_ENABLE_BEDROCK_JOBS"] == "0"
        assert all(
            "AWS_SECRET_ACCESS_KEY" not in e and "ATLAS_MODEL_JOB_SPEC" not in e
            for e in (api, worker)
        )
        assert "must-not-use" not in api.values() and "must-not-use" not in worker.values()
    # A populated SQLite schema is larger than a bounded credential JSON file.
    assert (workspace / "review.db").stat().st_size > 16384
    with local.prepare(workspace):
        assert (workspace / "credentials.json").read_bytes() == original


def test_same_workspace_cannot_have_two_launchers(workspace):
    with local.prepare(workspace):
        with pytest.raises(local.LocalSetupError, match="running launcher"):
            with local.prepare(workspace):
                pytest.fail("Second launcher acquired the workspace")


@pytest.mark.parametrize("damage", ["public", "symlink", "invalid", "duplicate"])
def test_invalid_credentials_are_retained_and_refused(workspace, damage):
    with local.prepare(workspace):
        pass
    path = workspace / "credentials.json"
    if damage == "public":
        path.chmod(0o644)
    elif damage == "symlink":
        moved = workspace / "retained.json"
        path.rename(moved)
        path.symlink_to(moved)
    elif damage == "invalid":
        path.write_text('["not credentials"]')
    else:
        token = "x" * 43
        value = json.dumps(local.PRINCIPAL)
        path.write_text('{"' + token + '":' + value + ',"' + token + '":' + value + "}")
    before = path.read_bytes()
    with pytest.raises((local.LocalSetupError, ValueError, OSError)):
        with local.prepare(workspace):
            pytest.fail("Invalid local credential file was admitted")
    assert path.read_bytes() == before


def test_workspace_must_stay_private_and_inside_var(workspace):
    with pytest.raises(local.LocalSetupError):
        with local.prepare(workspace.parent.parent / "outside"):
            pytest.fail("Workspace escaped var")
    workspace.mkdir(parents=True, mode=0o755)
    workspace.chmod(0o755)
    with pytest.raises(local.LocalSetupError):
        with local.prepare(workspace):
            pytest.fail("Public workspace admitted")


def test_database_and_temp_symlinks_are_refused(workspace):
    with local.prepare(workspace):
        pass
    database = workspace / "review.db"
    original = workspace / "retained.db"
    database.rename(original)
    database.symlink_to(original)
    with pytest.raises(local.LocalSetupError):
        with local.prepare(workspace):
            pytest.fail("Linked database admitted")
    database.unlink()
    original.rename(database)
    tmp = workspace / "tmp"
    tmp.rmdir()
    tmp.symlink_to(workspace)
    with pytest.raises(local.LocalSetupError):
        with local.prepare(workspace):
            pytest.fail("Linked scratch directory admitted")
    assert os.stat(original if original.exists() else database).st_mode & 0o077 == 0


def test_stopping_worker_kills_bounded_analysis_and_leaves_recoverable_claim(workspace):
    import signal
    import subprocess
    import time
    from datetime import timedelta

    from atlas.jobs import JobQueue, utcnow
    from atlas.store import Store
    from atlas.worker import process_once

    workspace.mkdir(parents=True, mode=0o700)
    database = "sqlite:///" + str(workspace / "interrupted.db")
    store = Store(database)
    queue = JobQueue(store)
    job = queue.submit(
        "a", "fixture", "local-stop-001", json.loads((ROOT / "datasets/demo.json").read_text())
    )
    marker = workspace / "analysis.pid"
    # Use the actual queue/lease and bounded-child primitive with a controlled
    # sleeping analysis. The application analysis recipe is not patched.
    harness = workspace / "interrupt.py"
    child_code = f"import os,time;from pathlib import Path;Path({str(marker)!r}).write_text(str(os.getpid()));time.sleep(60)"
    harness.write_text(
        f"import sys;sys.path.insert(0,{str(ROOT / 'scripts')!r});"
        "from run_managed_worker import run;from atlas.worker import process_once;"
        "from atlas.child_process import run_bounded;"
        f"\ndef execute(_):return run_bounded([sys.executable,'-c',{child_code!r}],b'',timeout_seconds=120)"
        f"\nraise SystemExit(run({database!r},int(sys.argv[1]),step=lambda queue:process_once(queue,executor=execute)))"
    )
    read_fd, write_fd = os.pipe()
    worker = subprocess.Popen(
        [sys.executable, str(harness), str(write_fd)],
        pass_fds=(write_fd,),
        env={"PYTHONPATH": str(ROOT / "src")},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    os.close(write_fd)
    try:
        deadline = time.monotonic() + 10
        while not marker.exists() and time.monotonic() < deadline:
            assert worker.poll() is None
            time.sleep(0.02)
        assert marker.exists()
        analysis_pid = int(marker.read_text())
        worker.send_signal(signal.SIGTERM)
        assert worker.wait(timeout=5) == 0
        with pytest.raises(ProcessLookupError):
            os.kill(analysis_pid, 0)
        interrupted = queue.get("a", job["id"])
        assert interrupted["status"] == "running" and interrupted["result_id"] is None
        assert interrupted["attempts"] == 1
        queue.clock = lambda: utcnow() + timedelta(seconds=61)
        assert process_once(queue)
        recovered = queue.get("a", job["id"])
        assert recovered["status"] == "succeeded" and recovered["attempts"] == 2
    finally:
        if worker.poll() is None:
            worker.kill()
            worker.wait()
        worker.stderr.close()
        os.close(read_fd)
        store.engine.dispose()
