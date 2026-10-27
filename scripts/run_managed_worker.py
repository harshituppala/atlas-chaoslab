"""Baseline-only queue worker with progress reported to its trusted supervisor."""

import argparse
import os
import signal
import time

from atlas.jobs import JobQueue
from atlas.observability import configure
from atlas.store import Store
from atlas.worker import process_once


class StopRequested(BaseException):
    """Unwind the bounded-child cleanup without recording a fabricated job failure."""


def run(database_url, progress_fd, *, step=process_once):
    # Analysis children use close_fds=True and cannot keep this pipe alive.
    os.set_inheritable(progress_fd, False)

    def stop(*_):
        raise StopRequested()

    previous = {sig: signal.signal(sig, stop) for sig in (signal.SIGTERM, signal.SIGINT)}
    store = None
    try:
        store = Store(database_url, purpose="worker")
        queue = JobQueue(store)
        while True:
            # Only the queue loop reports progress. A lease-renewal thread must
            # not hide a blocked database operation or stuck analysis execution.
            os.write(progress_fd, b".")
            worked = step(queue)
            if not worked:
                time.sleep(0.25)
    except StopRequested:
        return 0
    finally:
        if store is not None:
            store.engine.dispose()
        os.close(progress_fd)
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--progress-fd", type=int, required=True)
    args = parser.parse_args()
    if args.progress_fd < 3:
        parser.error("A dedicated supervisor pipe is required")
    configure("atlas-managed-worker")
    return run(os.environ["ATLAS_DATABASE_URL"], args.progress_fd)


if __name__ == "__main__":
    raise SystemExit(main())
