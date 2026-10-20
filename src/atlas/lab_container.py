"""Explicit synthetic-only container entry; never starts the private bearer API."""

import os

from .synthetic_lab import create_lab


def configuration(environment):
    if environment.get("ATLAS_LAB_CONTAINER") != "1":
        raise ValueError("Synthetic container requires explicit opt-in")
    origin = environment.get("ATLAS_LAB_ORIGIN", "")
    if not origin or len(origin) > 512:
        raise ValueError("Synthetic container requires its exact external origin")
    port = environment.get("PORT", "8000")
    if not port.isascii() or not port.isdecimal() or not 1 <= int(port) <= 65535:
        raise ValueError("Invalid synthetic container port")
    return origin, int(port)


def main():
    import uvicorn

    origin, port = configuration(os.environ)
    app = create_lab(origin, web_root="apps/web/dist-lab", execution_timeout_seconds=20)
    uvicorn.run(app, host="0.0.0.0", port=port, access_log=False, proxy_headers=False)


if __name__ == "__main__":
    main()
