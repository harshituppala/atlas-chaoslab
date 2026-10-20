"""Hard deadlines and bounded artifacts for trusted evaluation adapters.

This is process isolation for reproducible failure handling, not a hostile-code
sandbox: adapters retain the user's filesystem/network permissions.
"""

import json
import os
import re
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

MAX_INPUT_BYTES = 1_500_000
MAX_OUTPUT_BYTES = 2_000_000


class AdapterFailure(Exception):
    pass


class AdapterDeadline(AdapterFailure):
    pass


class AdapterOutputBudget(AdapterFailure):
    pass


def invoke(adapter, inputs, fault=None, *, deadline_seconds=10):
    if not re.fullmatch(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*:[A-Za-z_]\w*", adapter):
        raise ValueError("Adapter must be an explicit trusted module:function")
    if not 0 < deadline_seconds <= 120:
        raise ValueError("Adapter deadline must be greater than zero and at most 120 seconds")
    body = json.dumps({"input": inputs, "fault": fault}, allow_nan=False).encode()
    if len(body) > MAX_INPUT_BYTES:
        raise AdapterOutputBudget("Adapter input budget exceeded")
    root = Path("var/chaoslab/tmp")
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.TemporaryFile(dir=root) as output, tempfile.TemporaryFile(dir=root) as errors:
        process = subprocess.Popen(
            [sys.executable, "-m", "chaoslab.execution_child", adapter],
            stdin=subprocess.PIPE,
            stdout=output,
            stderr=errors,
            start_new_session=True,
        )
        try:
            process.communicate(body, timeout=deadline_seconds)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate()
            raise AdapterDeadline("Adapter wall deadline exceeded") from None
        finally:
            # A returned adapter may have left a child holding output descriptors.
            # Reap only this invocation's process group, never unrelated services.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        output.seek(0)
        raw = output.read(MAX_OUTPUT_BYTES + 1)
        if len(raw) >= MAX_OUTPUT_BYTES:
            raise AdapterOutputBudget("Adapter output budget exceeded")
        if process.returncode:
            raise AdapterFailure("Adapter process failed")
        try:
            result = json.loads(raw)
            if not isinstance(result, dict):
                raise ValueError("Adapter result must be an object")
        except (ValueError, UnicodeError):
            raise AdapterFailure("Adapter output is not valid JSON") from None
        return result
