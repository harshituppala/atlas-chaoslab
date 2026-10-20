"""Independent atomic report publication: readers see the old or complete new JSON."""

import json
import os
import tempfile
from pathlib import Path


def publish_report(path: Path, payload, *, default=None):
    # Serialize before touching the old report; refuse non-finite fabricated metrics.
    text = json.dumps(payload, indent=2, allow_nan=False, default=default) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
