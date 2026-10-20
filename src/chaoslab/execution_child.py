"""Private evaluation child; stdout is reserved for the JSON result."""

import importlib
import json
import resource
import sys

from .execution import MAX_INPUT_BYTES, MAX_OUTPUT_BYTES


def main():
    resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_OUTPUT_BYTES, MAX_OUTPUT_BYTES))
    raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
    if len(raw) > MAX_INPUT_BYTES:
        raise ValueError("Input byte budget exceeded")
    body = json.loads(raw)
    module, function = sys.argv[1].split(":")
    adapter = getattr(importlib.import_module(module), function)
    result = adapter(body["input"], body["fault"])
    sys.stdout.write(json.dumps(result, allow_nan=False))


if __name__ == "__main__":
    main()
