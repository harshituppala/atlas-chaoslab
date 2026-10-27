"""Baseline-only queue worker with progress reported to its trusted supervisor."""

import argparse
import os
import signal
import threading

from atlas.jobs import JobQueue
from atlas.observability import configure
from atlas.store import Store
from atlas.worker import process_once


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--progress-fd", type=int, required=True)
    args = parser.parse_args()
    if args.progress_fd < 3:
        parser.error("A dedicated supervisor pipe is required")
    # Analysis children use close_fds=True and cannot keep this pipe alive.
    os.set_inheritable(args.progress_fd, False)
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    configure("atlas-managed-worker")
    store = Store(os.environ["ATLAS_DATABASE_URL"], purpose="worker")
    try:
        queue = JobQueue(store)
        while not stop.is_set():
            # Only the queue loop reports progress. A lease-renewal thread must
            # not hide a blocked database operation or stuck analysis execution.
            os.write(args.progress_fd, b".")
            worked = process_once(queue)
            if not worked:
                stop.wait(0.25)
    finally:
        store.engine.dispose()
        os.close(args.progress_fd)


if __name__ == "__main__":
    main()
