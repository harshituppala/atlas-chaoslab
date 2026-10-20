"""Manage a private loopback integration cluster under this repository's var/.

Requires the separately prepared PostgreSQL runtime; never downloads or installs.
Credentials stay in private ignored files and are never passed on command lines.
"""

import argparse
import json
import secrets
import subprocess
import tempfile
from pathlib import Path

import psycopg

from atlas.artifacts import write_private_json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["start", "stop", "status"])
    args = parser.parse_args()
    root = Path.cwd().resolve()
    binary = root / ".runtime/postgresql/bin"
    private = root / "var/postgresql"
    private.mkdir(parents=True, exist_ok=True, mode=0o700)
    private.chmod(0o700)
    data, client = private / "data", private / "client.json"
    if not (binary / "pg_ctl").exists():
        parser.error("Prepare the local PostgreSQL runtime before starting an integration cluster")
    if args.action == "stop":
        subprocess.run([str(binary / "pg_ctl"), "-D", str(data), "stop", "-m", "fast"], check=True)
        return
    running = (
        subprocess.run(
            [str(binary / "pg_ctl"), "-D", str(data), "status"], capture_output=True
        ).returncode
        == 0
    )
    if args.action == "status":
        print(json.dumps({"running": running, "configuration_available": client.exists()}))
        return
    if not client.exists():
        if (data / "PG_VERSION").exists():
            parser.error(
                "Existing cluster has no matching client config; recover credentials manually"
            )
        write_private_json(
            client,
            {
                "host": "127.0.0.1",
                "port": 55432,
                "user": "portfolio_admin",
                "password": secrets.token_urlsafe(32),
                "dbname": "portfolio_integration",
                "sslmode": "disable",
            },
        )
    config = json.loads(client.read_text())
    if not (data / "PG_VERSION").exists():
        with tempfile.NamedTemporaryFile(mode="w", dir=private) as password:
            password.write(config["password"] + "\n")
            password.flush()
            subprocess.run(
                [
                    str(binary / "initdb"),
                    "-D",
                    str(data),
                    "--username",
                    config["user"],
                    "--pwfile",
                    password.name,
                    "--auth-local=scram-sha-256",
                    "--auth-host=scram-sha-256",
                    "--no-locale",
                    "--encoding=UTF8",
                ],
                check=True,
                stdout=subprocess.DEVNULL,
            )
    socket = private / "socket"
    socket.mkdir(exist_ok=True, mode=0o700)
    if not running:
        subprocess.run(
            [
                str(binary / "pg_ctl"),
                "-D",
                str(data),
                "-l",
                str(private / "server.log"),
                "-o",
                f"-h 127.0.0.1 -p {config['port']} -k {socket} -c max_connections=40",
                "start",
            ],
            check=True,
            stdout=subprocess.DEVNULL,
        )
    with psycopg.connect(**{**config, "dbname": "postgres"}, autocommit=True) as connection:
        if not connection.execute(
            "SELECT 1 FROM pg_database WHERE datname=%s", (config["dbname"],)
        ).fetchone():
            from psycopg import sql

            connection.execute(
                sql.SQL("CREATE DATABASE {}").format(sql.Identifier(config["dbname"]))
            )
    print(
        json.dumps({"running": True, "binding": "loopback", "credentials": "private ignored file"})
    )


if __name__ == "__main__":
    main()
