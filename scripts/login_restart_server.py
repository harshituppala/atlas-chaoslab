"""Child server for a disposable restart exercise; never deploy fixture routes."""

import json
import signal
import socket
import sys
import urllib.request
from pathlib import Path

import uvicorn
from cryptography.hazmat.primitives.asymmetric import rsa
from login_browser_fixture import create_fixture

from atlas.security.memberships import MembershipRegistry
from atlas.store import Store


def main():
    config = json.loads(Path(sys.argv[1]).read_text())
    owner = Store(config["operator_database"])

    def control(action):
        request = urllib.request.Request(
            config["control_origin"] + "/" + action,
            data=b"",
            headers={"X-Fixture-Control": config["control_secret"]},
            method="POST",
        )
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
            request, timeout=10
        ) as response:
            assert response.status == 200

    app, metrics, close = create_fixture(
        Path(config["work"]),
        config["proxy"],
        Path(config["certificate"]),
        rsa.generate_private_key(public_exponent=65537, key_size=2048),
        worker_control=control,
        database_url=config["api_database"],
        membership_operator=MembershipRegistry(owner),
        reuse_membership=True,
    )
    # Uvicorn handles shutdown, then re-raises the captured signal. Keep this
    # fixture entry point alive long enough to close resources and save metrics.
    signal.signal(signal.SIGTERM, lambda *_: None)
    signal.signal(signal.SIGINT, lambda *_: None)
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            ssl_certfile=config["certificate"],
            ssl_keyfile=config["key"],
            access_log=False,
            log_level="info",
            timeout_graceful_shutdown=2,
            lifespan="off",
        )
    )
    try:
        server.run(sockets=[socket.socket(fileno=config["listener_fd"])])
    finally:
        close()
        owner.engine.dispose()
        Path(config["metrics_path"]).write_text(json.dumps(metrics))


if __name__ == "__main__":
    main()
