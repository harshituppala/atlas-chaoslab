"""Trusted local worker. Computation may repeat; publication is atomic and fenced."""

import argparse
import json
import logging
import os
import signal
import sys
import threading
from pathlib import Path

from pydantic import ValidationError

from .child_process import run_bounded
from .domain import ResourceBudgetExceeded
from .execution import PIPELINE_VERSION
from .jobs import JobQueue, LostLease
from .models.intelligence import MODEL_PIPELINE_VERSION
from .observability import configure
from .store import Store

log = logging.getLogger("atlas.worker")


def execute_isolated(body, timeout_seconds=120):
    """A child process permits hard timeout/reaping instead of a stuck thread."""
    child = run_bounded(
        [sys.executable, "-m", "atlas.worker_task"],
        json.dumps(body).encode(),
        timeout_seconds=timeout_seconds,
    )
    if child.returncode != 0:
        try:
            code = json.loads(child.stdout).get("worker_error")
        except (ValueError, AttributeError):
            code = "execution_error"
        if code == "resource_budget_exceeded":
            raise ResourceBudgetExceeded()
        raise RuntimeError("Analysis child process failed")
    return json.loads(child.stdout)


def execute_model_isolated(claim, *, config_path, session_budget, timeout_seconds=300):
    try:
        child = run_bounded(
            [
                sys.executable,
                "-m",
                "atlas.models.job_task",
                "--config",
                str(config_path),
                "--session-budget",
                str(session_budget),
                "--allow-paid",
            ],
            json.dumps({"id": claim.id, "tenant": claim.tenant, "input": claim.input}).encode(),
            timeout_seconds=timeout_seconds,
        )
    except TimeoutError:
        raise TimeoutError("Model job deadline exceeded; invocation may be billable") from None
    if child.returncode != 0:
        raise RuntimeError("Model job failed; inspect private operator receipts")
    return json.loads(child.stdout)


def process_once(queue, executor=execute_isolated, lease_seconds=60, *, model_executor=None):
    supported = [PIPELINE_VERSION]
    if model_executor is not None:
        supported.append(MODEL_PIPELINE_VERSION)
    claim = queue.claim(lease_seconds, pipeline_versions=supported)
    if claim is None:
        return False
    done, lost = threading.Event(), threading.Event()

    def renew():
        while not done.wait(lease_seconds / 3):
            try:
                queue.heartbeat(claim, lease_seconds)
            except Exception:
                lost.set()
                return  # Fail closed: do not publish without ownership.

    thread = threading.Thread(target=renew, daemon=True)
    thread.start()
    try:
        if claim.pipeline_version == MODEL_PIPELINE_VERSION:
            output = model_executor(claim)
            if not lost.is_set():
                queue.complete(claim, output)
        else:
            output = executor(claim.input)
            if not lost.is_set():
                queue.complete(claim, output)
    except LostLease:
        log.info("Ownership revoked for job %s", claim.id)
    except Exception as exc:
        retryable = claim.pipeline_version == PIPELINE_VERSION and isinstance(
            exc, (TimeoutError, ConnectionError)
        )
        code = (
            "upstream_unavailable"
            if retryable
            else "resource_budget_exceeded"
            if isinstance(exc, ResourceBudgetExceeded)
            else "invalid_output"
            if isinstance(exc, ValidationError)
            else "execution_error"
        )
        if not lost.is_set():
            try:
                queue.fail(claim, code, retryable)
            except LostLease:
                pass
        log.warning("Job %s failed with %s", claim.id, type(exc).__name__)
    finally:
        done.set()
        thread.join(timeout=1)
    return True


def main():
    configure("atlas-worker")
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--lease-seconds", type=int, default=60)
    parser.add_argument("--model-config")
    parser.add_argument("--allow-paid", action="store_true")
    parser.add_argument("--session-budget", default="var/bedrock/campaign-budget.json")
    args = parser.parse_args()
    if bool(args.model_config) != args.allow_paid:
        parser.error("Model execution requires both --model-config and --allow-paid")
    model_executor = None
    if args.model_config:
        from functools import partial

        model_executor = partial(
            execute_model_isolated,
            config_path=args.model_config,
            session_budget=args.session_budget,
        )
    Path("var").mkdir(exist_ok=True)
    queue = JobQueue(
        Store(os.getenv("ATLAS_DATABASE_URL", "sqlite:///var/atlas.db"), purpose="worker")
    )
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    logging.basicConfig(level=logging.INFO)
    while not stop.is_set():
        worked = process_once(
            queue, lease_seconds=args.lease_seconds, model_executor=model_executor
        )
        if args.once:
            break
        if not worked:
            stop.wait(0.25)


if __name__ == "__main__":
    main()
