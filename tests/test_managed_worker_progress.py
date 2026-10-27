"""A live PID or lease thread cannot substitute for progress in the queue loop."""

import json
import os
import signal
import subprocess
import sys
import time

import pytest
from test_workbench_supervisor import SCRIPT, module, wait_for

from atlas.jobs import JobQueue
from atlas.store import Store

ROOT = SCRIPT.parents[1]


@pytest.mark.parametrize("mode", ["frozen", "silent", "closed", "invalid", "healthy"])
def test_progress_pipe_detects_stalls_and_preserves_operator_shutdown(tmp_path, mode):
    api = tmp_path / "api"
    worker = tmp_path / "worker"
    api_code = (
        "import signal,time;from pathlib import Path;"
        f"p=Path({str(api)!r});p.write_text('ready');"
        "signal.signal(signal.SIGTERM,lambda *_:(p.with_suffix('.stopped').write_text('yes'),exit(0)));"
        "time.sleep(60)"
    )
    worker_code = (
        "import os,sys,time;from pathlib import Path;"
        "fd=int(sys.argv[-1]);"
        f"Path({str(worker)!r}).write_text(str(os.getpid()));"
    )
    if mode == "frozen":
        worker_code += (
            f"os.write(fd,b'.');os.kill(os.getpid(),{int(signal.SIGSTOP)});time.sleep(60)"
        )
    elif mode == "silent":
        worker_code += "time.sleep(60)"
    elif mode == "closed":
        worker_code += "os.close(fd);time.sleep(60)"
    elif mode == "invalid":
        worker_code += "os.write(fd,b'not-progress');time.sleep(60)"
    else:
        worker_code += "\nwhile True:os.write(fd,b'.');time.sleep(.05)"
    commands = [[sys.executable, "-c", api_code], [sys.executable, "-c", worker_code]]
    harness = tmp_path / "supervise.py"
    harness.write_text(
        f"import importlib.util; s=importlib.util.spec_from_file_location('s',{str(SCRIPT)!r});"
        "m=importlib.util.module_from_spec(s);s.loader.exec_module(m);"
        f"raise SystemExit(m.supervise({commands!r},[{{}},{{}}],grace=.1,poll_interval=.02,worker_progress_timeout=2))"
    )
    child = subprocess.Popen([sys.executable, str(harness)], stderr=subprocess.PIPE)
    try:
        wait_for(worker, child)
        if mode == "healthy":
            # Longer than the deadline: repeated queue-loop progress keeps it alive.
            time.sleep(2.2)
            assert child.poll() is None
            child.send_signal(signal.SIGTERM)
        assert child.wait(timeout=6) == (0 if mode == "healthy" else 1)
        assert api.with_suffix(".stopped").exists()
        if mode == "frozen":
            assert b"stopped making progress" in child.stderr.read()
        with pytest.raises(ProcessLookupError):
            os.kill(int(worker.read_text()), 0)
    finally:
        if child.poll() is None:
            child.kill()
            child.wait()
        child.stderr.close()


def test_real_managed_worker_reports_loop_progress_and_completes_baseline(tmp_path):
    url = "sqlite:///" + str(tmp_path / "queue.db")
    store = Store(url)
    queue = JobQueue(store)
    job = queue.submit(
        "a", "fixture", "progress-job-001", json.loads((ROOT / "datasets/demo.json").read_text())
    )
    read_fd, write_fd = os.pipe()
    os.set_blocking(read_fd, False)
    child = subprocess.Popen(
        [
            sys.executable,
            str(ROOT / "scripts/run_managed_worker.py"),
            "--progress-fd",
            str(write_fd),
        ],
        env={"PYTHONPATH": str(ROOT / "src"), "ATLAS_DATABASE_URL": url},
        pass_fds=(write_fd,),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    os.close(write_fd)
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            assert child.poll() is None
            if queue.get("a", job["id"])["status"] == "succeeded":
                break
            time.sleep(0.05)
        else:
            pytest.fail("Actual managed worker did not complete the queued fixture")
        progress = os.read(read_fd, 4096)
        assert progress and progress.strip(b".") == b""
        child.send_signal(signal.SIGTERM)
        assert child.wait(timeout=5) == 0
    finally:
        if child.poll() is None:
            child.kill()
            child.wait()
        child.stderr.close()
        os.close(read_fd)
        store.engine.dispose()


@pytest.mark.parametrize("deadline", [0, -1, float("inf"), float("nan"), 601])
def test_invalid_progress_deadline_is_refused_before_spawn(deadline):
    with pytest.raises(ValueError):
        module.supervise([["api"], ["worker"]], [{}, {}], worker_progress_timeout=deadline)
