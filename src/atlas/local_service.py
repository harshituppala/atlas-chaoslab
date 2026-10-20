"""Loopback-only SQLite API with one lifespan-owned baseline worker.

This is a local topology experiment, not the public synthetic hosting profile.
"""

import argparse
import asyncio
import json
import os
import threading
from contextlib import asynccontextmanager
from functools import partial
from pathlib import Path

from .api import create_app
from .jobs import JobQueue
from .store import Store
from .worker import execute_isolated, process_once


class BaselineWorker:
    """One-shot lifecycle; unexpected queue failures require operator intervention."""

    def __init__(self, queue, *, step=None):
        self.queue = queue
        self._step = step or partial(
            process_once, executor=partial(execute_isolated, timeout_seconds=10)
        )
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._state = "created"
        self._thread = threading.Thread(target=self._run, name="atlas-local-worker")

    @property
    def state(self):
        with self._lock:
            return self._state

    def ready(self):
        return self.state == "running" and self._thread.is_alive()

    def start(self):
        with self._lock:
            if self._state != "created":
                raise RuntimeError("Local worker lifecycle cannot be reused")
            self._state = "running"
            try:
                self._thread.start()
            except BaseException:
                self._state = "failed"
                raise

    def _run(self):
        try:
            while not self._stop.is_set():
                if not self._step(self.queue):
                    self._stop.wait(0.1)
        except BaseException:
            # No queue/database/source exception text escapes into public health output.
            with self._lock:
                self._state = "failed"
        finally:
            with self._lock:
                if self._state != "failed":
                    self._state = "stopped"

    def stop(self, *, timeout=30):
        with self._lock:
            if self._state == "created":
                self._state = "stopped"
                return
            if self._state == "running":
                self._state = "stopping"
            self._stop.set()
        if self._thread.ident is None:
            return
        self._thread.join(timeout=timeout)
        if self._thread.is_alive():
            raise RuntimeError("Local worker has not stopped; storage remains open")


def create_local_service(database_path, principals):
    """Use an explicit SQLite file and local principals; never import model configuration."""
    forbidden = (
        "ATLAS_DATABASE_URL",
        "ATLAS_MODEL_JOB_SPEC",
        "ATLAS_ENABLE_BEDROCK_JOBS",
        "ATLAS_TOKEN_TRUST",
    )
    if any(os.getenv(name) for name in forbidden):
        raise ValueError("Remove database/model/managed-auth configuration for this local profile")
    path = Path(database_path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    url = "sqlite:///" + str(path)
    worker_store = Store(url, purpose="worker")
    worker = BaselineWorker(JobQueue(worker_store))
    try:
        app = create_app(url, principals, readiness_probe=worker.ready)
    except BaseException:
        worker_store.engine.dispose()
        raise
    original_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(application):
        async with original_lifespan(application):
            try:
                worker.start()
                yield
            finally:
                # Do not dispose engines underneath a worker whose bounded join failed.
                await asyncio.to_thread(worker.stop)
                worker_store.engine.dispose()
                app.state.store.engine.dispose()

    app.router.lifespan_context = lifespan
    app.state.local_worker = worker
    return app


def main():
    import uvicorn

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", default="var/local-service/atlas.db")
    parser.add_argument("--credentials", default="var/local-credentials.json")
    parser.add_argument("--port", type=int, default=8132)
    args = parser.parse_args()
    credentials = Path(args.credentials)
    if credentials.stat().st_mode & 0o077:
        parser.error("Credentials file must be private to its owner (mode 0600)")
    principals = json.loads(credentials.read_text())
    if not isinstance(principals, dict) or not principals:
        parser.error("A nonempty existing local credentials file is required")
    uvicorn.run(
        create_local_service(args.database, principals),
        host="127.0.0.1",
        port=args.port,
        access_log=False,
    )


if __name__ == "__main__":
    main()
