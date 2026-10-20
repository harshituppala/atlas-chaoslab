"""Private subprocess protocol: trusted implementation, untrusted document data."""

import json
import sys

from opentelemetry import trace

from .domain import ResourceBudgetExceeded
from .execution import execute
from .observability import configure


def main():
    configure("atlas-analysis")
    try:
        body = json.loads(sys.stdin.read(1_500_001))
        with trace.get_tracer("atlas.worker").start_as_current_span(
            "atlas.analysis", record_exception=False, set_status_on_exception=False
        ):
            print(json.dumps(execute(body)))
    except ResourceBudgetExceeded:
        print(json.dumps({"worker_error": "resource_budget_exceeded"}))
        sys.exit(2)
    except Exception:
        print(json.dumps({"worker_error": "execution_error"}))
        sys.exit(2)


if __name__ == "__main__":
    main()
