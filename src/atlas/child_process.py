"""Bounded POSIX pipes for trusted worker children; not a hostile-code sandbox."""

import math
import os
import selectors
import signal
import subprocess
import time
from dataclasses import dataclass

from .domain import ResourceBudgetExceeded


@dataclass(frozen=True)
class ChildResult:
    returncode: int
    stdout: bytes
    stderr_bytes: int


def kill_group(process):
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def run_bounded(
    argv,
    body,
    *,
    timeout_seconds,
    maximum_input=1_500_000,
    maximum_output=8_000_000,
    maximum_errors=65_536,
):
    """Pump all three pipes concurrently, bounding retained output before JSON decoding.

    stderr is counted/discarded, never returned. Only this invocation's newly
    created process group is signalled. Children escaping that group are outside
    this supervisor's containment boundary.
    """
    if not isinstance(body, bytes):
        raise TypeError("Child input must be bytes")
    if (
        type(timeout_seconds) not in {int, float}
        or not math.isfinite(timeout_seconds)
        or not 0 < timeout_seconds <= 600
    ):
        raise ValueError("Invalid child deadline")
    if any(
        type(v) is not int or not 1 <= v <= 16_000_000
        for v in (maximum_input, maximum_output, maximum_errors)
    ):
        raise ValueError("Invalid child byte budget")
    if len(body) > maximum_input:
        raise ResourceBudgetExceeded("Child input budget exceeded")
    deadline = time.monotonic() + timeout_seconds
    process = subprocess.Popen(
        argv,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    output, error_bytes, sent = bytearray(), 0, 0
    streams = (process.stdin, process.stdout, process.stderr)
    try:
        with selectors.DefaultSelector() as selector:
            for stream in streams:
                os.set_blocking(stream.fileno(), False)
            selector.register(process.stdout, selectors.EVENT_READ, "stdout")
            selector.register(process.stderr, selectors.EVENT_READ, "stderr")
            if body:
                selector.register(process.stdin, selectors.EVENT_WRITE, "stdin")
            else:
                process.stdin.close()
            root_exited = False
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("Child execution deadline exceeded")
                if process.poll() is not None and not root_exited:
                    # Even a successful root must not leave same-group descendants alive.
                    kill_group(process)
                    root_exited = True
                for key, _ in selector.select(min(remaining, 0.05)):
                    stream, channel = key.fileobj, key.data
                    if channel == "stdin":
                        try:
                            sent += os.write(stream.fileno(), body[sent : sent + 65_536])
                        except BrokenPipeError:
                            sent = len(body)
                        except BlockingIOError:
                            continue
                        if sent == len(body):
                            selector.unregister(stream)
                            stream.close()
                        continue
                    try:
                        chunk = os.read(stream.fileno(), 65_536)
                    except BlockingIOError:
                        continue
                    if not chunk:
                        selector.unregister(stream)
                        stream.close()
                    elif channel == "stdout":
                        if len(output) + len(chunk) > maximum_output:
                            raise ResourceBudgetExceeded("Child output budget exceeded")
                        output.extend(chunk)
                    else:
                        error_bytes += len(chunk)
                        if error_bytes > maximum_errors:
                            raise ResourceBudgetExceeded("Child diagnostic budget exceeded")
            # A child may close all pipes and keep running. The same deadline still applies.
            try:
                returncode = process.wait(timeout=max(0, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                raise TimeoutError("Child execution deadline exceeded") from None
            return ChildResult(returncode, bytes(output), error_bytes)
    finally:
        kill_group(process)
        process.wait()
        for stream in streams:
            stream.close()
