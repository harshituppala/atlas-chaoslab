"""Actual POSIX subprocess supervision, including pipe pressure and descendants."""

import json
import os
import sys
import time
from pathlib import Path

import pytest

from atlas.child_process import run_bounded
from atlas.domain import ResourceBudgetExceeded
from atlas.worker import execute_isolated, execute_model_isolated


def child(code, body=b"", **kwargs):
    return run_bounded(
        [sys.executable, "-c", code],
        body,
        timeout_seconds=kwargs.pop("timeout_seconds", 3),
        **kwargs,
    )


def test_all_pipes_progress_without_input_output_deadlock():
    result = child(
        "import sys; sys.stdout.buffer.write(b'x'*200000);sys.stdout.flush();"
        "data=sys.stdin.buffer.read();sys.stderr.buffer.write(b'e'*60000);"
        "sys.stdout.buffer.write(data)",
        b"y" * 200000,
    )
    assert result.returncode == 0
    assert result.stdout == b"x" * 200000 + b"y" * 200000
    assert result.stderr_bytes == 60000
    assert not hasattr(result, "stderr")


def test_exact_byte_boundaries_and_nonzero_exit_are_preserved():
    result = child(
        "import sys;sys.stdout.buffer.write(sys.stdin.buffer.read());sys.stderr.write('err');sys.exit(7)",
        b"abc",
        maximum_input=3,
        maximum_output=3,
        maximum_errors=3,
    )
    assert (result.stdout, result.returncode, result.stderr_bytes) == (b"abc", 7, 3)


@pytest.mark.parametrize("stream", ["stdout", "stderr"])
def test_oversized_output_is_stopped_without_exporting_child_text(stream, tmp_path):
    marker = tmp_path / "root-pid"
    code = f"import os,sys,time;from pathlib import Path;Path({str(marker)!r}).write_text(str(os.getpid()));sys.{stream}.write('PRIVATE-CANARY'*100000);sys.{stream}.flush();time.sleep(20)"
    with pytest.raises(ResourceBudgetExceeded) as error:
        child(code, maximum_output=1024, maximum_errors=1024)
    assert "PRIVATE-CANARY" not in str(error.value)
    with pytest.raises(ProcessLookupError):
        os.kill(int(marker.read_text()), 0)


def test_input_budget_is_checked_before_spawn(monkeypatch):
    import atlas.child_process as module

    def forbidden(*args, **kwargs):
        raise AssertionError("Oversized input spawned a child")

    monkeypatch.setattr(module.subprocess, "Popen", forbidden)
    with pytest.raises(ResourceBudgetExceeded, match="input"):
        child("", b"four", maximum_input=3)


def test_child_closing_stdin_early_does_not_break_supervisor():
    result = child("import os;os.close(0);print('{}')", b"x" * 400000)
    assert result.returncode == 0 and json.loads(result.stdout) == {}


def test_deadline_still_applies_after_child_closes_output_pipes(tmp_path):
    marker = tmp_path / "pid"
    code = f"import os,time;from pathlib import Path;Path({str(marker)!r}).write_text(str(os.getpid()));os.close(0);os.close(1);os.close(2);time.sleep(20)"
    with pytest.raises(TimeoutError):
        child(code, timeout_seconds=0.3)
    with pytest.raises(ProcessLookupError):
        os.kill(int(marker.read_text()), 0)


@pytest.mark.parametrize("root_hangs", [True, False])
def test_same_group_descendants_stop_on_timeout_or_success(tmp_path, root_hangs):
    heartbeat = tmp_path / "heartbeat"
    nested = f"import time;from pathlib import Path;p=Path({str(heartbeat)!r});\nwhile True:\n p.write_text(str(time.monotonic_ns()));time.sleep(.02)"
    root = (
        f"import sys,subprocess,time;from pathlib import Path;subprocess.Popen([sys.executable,'-c',{nested!r}]);"
        f"p=Path({str(heartbeat)!r});\nwhile not p.exists(): time.sleep(.005)\n"
        + ("time.sleep(20)" if root_hangs else "print('{}')")
    )
    if root_hangs:
        with pytest.raises(TimeoutError):
            child(root, timeout_seconds=0.5)
    else:
        assert json.loads(child(root).stdout) == {}
    observed = heartbeat.read_bytes()
    time.sleep(0.1)
    assert heartbeat.read_bytes() == observed
    # Killing/reaping a failed invocation does not poison later invocations.
    assert child("print('{}')").returncode == 0


@pytest.mark.parametrize("deadline", [0, -1, float("nan"), float("inf"), True, 601])
def test_invalid_deadline_is_rejected(deadline):
    with pytest.raises(ValueError):
        child("", timeout_seconds=deadline)


def test_actual_worker_protocol_still_publishes_valid_baseline():
    body = json.loads(Path("datasets/demo.json").read_text())
    result = execute_isolated(body)
    assert result["provider"] == "extractive-baseline"
    assert len(result["assessments"]) == 8
    assert all(a["review_state"] == "pending" for a in result["assessments"])


def test_model_worker_uses_bounded_supervisor_without_live_calls(monkeypatch):
    from types import SimpleNamespace

    import atlas.worker as worker
    from atlas.child_process import ChildResult

    observed = []

    def controlled(argv, body, **options):
        observed.append((argv, json.loads(body), options))
        return ChildResult(0, b'{"controlled":true}', 0)

    monkeypatch.setattr(worker, "run_bounded", controlled)
    claim = SimpleNamespace(id="synthetic", tenant="synthetic", input={"rfp": {}})
    assert execute_model_isolated(
        claim, config_path="private-config", session_budget="private-budget"
    ) == {"controlled": True}
    assert observed[0][2]["timeout_seconds"] == 300
    assert "--allow-paid" in observed[0][0]
    assert observed[0][1]["id"] == "synthetic"


def test_model_timeout_retains_uncertain_billing_message(monkeypatch):
    from types import SimpleNamespace

    import atlas.worker as worker

    def timeout(*args, **kwargs):
        raise TimeoutError("private child data")

    monkeypatch.setattr(worker, "run_bounded", timeout)
    with pytest.raises(TimeoutError, match="may be billable") as error:
        execute_model_isolated(
            SimpleNamespace(id="x", tenant="t", input={}), config_path="x", session_budget="y"
        )
    assert "private child data" not in str(error.value)
