"""Explicit local-only container initialization and secret-file service launch.

This is not production provisioning: one isolated Compose database, no TLS, local
bearer principals, and a trusted Docker administrator. Never reuse for cloud setup.
"""

import argparse
import json
import os
import sys
from pathlib import Path

from psycopg import sql
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

from .migrations import ensure_ready, upgrade


def load_secret(name):
    path = Path("/run/secrets") / name
    if path.stat().st_size > 65_536:
        raise ValueError("Local stack secret exceeds size limit")
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError("Local stack secret must be an object")
    return value


def database_url(user, password):
    if user not in {"atlas_owner", "atlas_api", "atlas_worker"}:
        raise ValueError("Unexpected local database role")
    if not isinstance(password, str) or not 24 <= len(password) <= 128:
        raise ValueError("Invalid local database password")
    return URL.create(
        "postgresql+psycopg",
        username=user,
        password=password,
        host="postgres",
        port=5432,
        database="atlas",
        query={"sslmode": "disable", "options": "-csearch_path=atlas,public"},
    )


def initialize(settings):
    engine = create_engine(database_url("atlas_owner", settings["owner_password"]))
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE SCHEMA IF NOT EXISTS atlas AUTHORIZATION atlas_owner"
            )
            connection.exec_driver_sql("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
            connection.exec_driver_sql("REVOKE ALL ON DATABASE atlas FROM PUBLIC")
        upgrade(engine)
        # Execute the reviewed reference; on repeat runs reuse only roles with the
        # exact expected attributes, then reapply explicit grants and passwords.
        reference = Path("deployment/postgres-runtime-roles.sql").read_text()
        with engine.begin() as connection:
            for name, bypass in (("atlas_api", False), ("atlas_worker", True)):
                row = connection.execute(
                    text(
                        "SELECT rolsuper, rolcreatedb, rolcreaterole, rolinherit, rolbypassrls, rolcanlogin "
                        "FROM pg_roles WHERE rolname=:name"
                    ),
                    {"name": name},
                ).first()
                if row is not None and tuple(row) != (False, False, False, False, bypass, True):
                    raise ValueError("Existing local runtime role has unexpected attributes")
                if row is not None:
                    reference = "\n".join(
                        line
                        for line in reference.splitlines()
                        if not line.startswith("CREATE ROLE " + name + " ")
                    )
            connection.exec_driver_sql(reference)
            for name, key in (("atlas_api", "api_password"), ("atlas_worker", "worker_password")):
                database_url(name, settings[key])  # Apply the same bounded password contract.
                statement = sql.SQL("ALTER ROLE {} PASSWORD {}").format(
                    sql.Identifier(name), sql.Literal(settings[key])
                )
                connection.exec_driver_sql(statement.as_string())
                connection.exec_driver_sql(
                    sql.SQL("GRANT CONNECT ON DATABASE atlas TO {}")
                    .format(sql.Identifier(name))
                    .as_string()
                )
        ensure_ready(engine, bootstrap_empty_sqlite=False)
    finally:
        engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("service", choices=["initialize", "api", "worker"])
    args = parser.parse_args()
    try:
        if os.getenv("ATLAS_LOCAL_STACK") != "1":
            raise ValueError("Local stack requires explicit opt-in")
        if args.service == "initialize":
            initialize(load_secret("operator"))
            print(json.dumps({"local_schema_ready": True, "revision": "0005"}))
            return
        settings = load_secret(args.service)
        role = "atlas_" + args.service
        os.environ["ATLAS_DATABASE_URL"] = database_url(
            role, settings["password"]
        ).render_as_string(hide_password=False)
        os.environ["ATLAS_ENABLE_BEDROCK_JOBS"] = "0"
        if args.service == "api":
            os.environ["ATLAS_PRINCIPALS"] = json.dumps(settings["principals"])
            command = [
                sys.executable,
                "-m",
                "uvicorn",
                "atlas.api:create_app",
                "--factory",
                "--host",
                "0.0.0.0",
                "--port",
                "8000",
            ]
        else:
            command = [sys.executable, "-m", "atlas.worker"]
        os.execv(sys.executable, command)
    except Exception:
        # Database exceptions can contain connection parameters or SQL literals.
        # Keep bootstrap failure fixed and never serialize secret-bearing errors.
        raise SystemExit(
            "Local stack initialization/launch failed; verify private configuration"
        ) from None


if __name__ == "__main__":
    main()
