"""One-shot parser process: no durable writes, source text never goes to stderr."""

import base64
import json
import logging
import sys

from .domain import ResourceBudgetExceeded
from .ingestion import UnsupportedDocument, extract_document


def main():
    # POSIX CPU limit; Linux also bounds address space. macOS RLIMIT_AS is not reliable.
    if sys.platform != "win32":
        import resource

        resource.setrlimit(resource.RLIMIT_CPU, (10, 10))
        if sys.platform.startswith("linux"):
            resource.setrlimit(resource.RLIMIT_AS, (384 * 1024 * 1024, 384 * 1024 * 1024))
    logging.disable(logging.CRITICAL)
    try:
        body = json.loads(sys.stdin.buffer.read(1_500_001))
        raw = base64.b64decode(body["data"], validate=True)
        result = extract_document(raw, body["format"], body["title"], body["kind"])
        print(result.model_dump_json())
    except ResourceBudgetExceeded:
        print(json.dumps({"error": "resource_budget_exceeded"}))
        sys.exit(2)
    except UnsupportedDocument as exc:
        # Only application-owned error messages; parser exceptions never cross this boundary.
        print(json.dumps({"error": "unsupported_document", "detail": str(exc)}))
        sys.exit(2)
    except Exception:
        print(json.dumps({"error": "extraction_failed"}))
        sys.exit(2)


if __name__ == "__main__":
    main()
