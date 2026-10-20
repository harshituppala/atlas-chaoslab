"""Local-only launcher. Credentials are generated, never committed."""

import json
import os
import secrets
from pathlib import Path

import uvicorn

from .api import create_app

Path("var").mkdir(exist_ok=True)
if os.getenv("ATLAS_DEMO") == "1":
    if os.getenv("ATLAS_TOKEN_TRUST"):
        raise SystemExit("Choose either local demo credentials or managed authentication")
    path = Path("var/local-credentials.json")
    if not path.exists():
        path.write_text(
            json.dumps(
                {
                    secrets.token_urlsafe(32): {
                        "tenant": "northstar",
                        "actor": "local-reviewer",
                        "role": "reviewer",
                    }
                },
                indent=2,
            )
        )
        path.chmod(0o600)
    os.environ["ATLAS_PRINCIPALS"] = path.read_text()
    print("Local credential stored in var/local-credentials.json. Paste the token into the UI.")
uvicorn.run(create_app(), host="127.0.0.1", port=8000, access_log=False)
