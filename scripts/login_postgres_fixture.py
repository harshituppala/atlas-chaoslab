"""Disposable loopback PostgreSQL for synthetic browser acceptance, never a cloud target."""

import os
import secrets
import socket
import subprocess
from pathlib import Path

from psycopg import sql
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import DBAPIError

from atlas.migrations import upgrade
from atlas.security.memberships import MembershipRegistry
from atlas.store import Store


class PostgresFixture:
    def __init__(self, work, binaries, *, restore_archive=None):
        self.binaries = Path(binaries).resolve()
        self.data = work / "postgres-data"
        self.work = work
        self.running = False
        self.owner = None
        self.log = (work / "postgres-bootstrap.log").open("w")
        password_file = work / "postgres-password"
        passwords = {role: secrets.token_urlsafe(36) for role in ("owner", "api", "worker")}
        password_file.write_text(passwords["owner"])
        password_file.chmod(0o600)
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        self.command_environment = {k: os.environ[k] for k in ("PATH", "LANG") if k in os.environ}
        self.command_environment.update(
            {
                "PGPASSWORD": passwords["owner"],
                "PGHOST": "127.0.0.1",
                "PGPORT": str(port),
                "PGUSER": "atlas_owner",
                "PGDATABASE": "postgres",
                "PGSSLMODE": "disable",
            }
        )
        self.urls = {
            role: URL.create(
                "postgresql+psycopg",
                username="atlas_" + role,
                password=password,
                host="127.0.0.1",
                port=port,
                database="postgres",
                query={"sslmode": "disable", "options": "-csearch_path=atlas,public"},
            ).render_as_string(hide_password=False)
            for role, password in passwords.items()
        }
        try:
            self.command(
                "initdb",
                "-D",
                str(self.data),
                "-U",
                "atlas_owner",
                "--pwfile",
                str(password_file),
                "--auth-host=scram-sha-256",
                "--auth-local=scram-sha-256",
                "--no-locale",
                "--encoding=UTF8",
            )
            self.command(
                "pg_ctl",
                "-D",
                str(self.data),
                "-l",
                str(work / "postgres.log"),
                "-o",
                f"-h 127.0.0.1 -p {port} -k ''",
                "-w",
                "start",
            )
            self.running = True
            engine = create_engine(self.urls["owner"])
            try:
                with engine.begin() as conn:
                    if restore_archive is None:
                        conn.exec_driver_sql("CREATE SCHEMA atlas AUTHORIZATION atlas_owner")
                    conn.exec_driver_sql("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
                    conn.exec_driver_sql("REVOKE ALL ON DATABASE postgres FROM PUBLIC")
                if restore_archive is None:
                    upgrade(engine)
                else:
                    # A schema-only archive does not include dependencies in public.
                    # Provision the reviewed pgvector dependency before its columns.
                    with engine.begin() as connection:
                        connection.exec_driver_sql(
                            "CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public"
                        )
                    with engine.connect() as connection:
                        assert (
                            connection.execute(
                                text(
                                    "SELECT count(*) FROM information_schema.tables WHERE table_schema='atlas'"
                                )
                            ).scalar_one()
                            == 0
                        )
                    self.command(
                        "pg_restore",
                        "--exit-on-error",
                        "--no-owner",
                        "--no-acl",
                        "--dbname=postgres",
                        str(restore_archive),
                    )
                with engine.begin() as conn:
                    conn.exec_driver_sql(Path("deployment/postgres-runtime-roles.sql").read_text())
                    for role in ("api", "worker"):
                        driver = conn.connection.driver_connection
                        driver.execute(
                            sql.SQL("ALTER ROLE {} PASSWORD {}").format(
                                sql.Identifier("atlas_" + role), sql.Literal(passwords[role])
                            )
                        )
                        driver.execute(
                            sql.SQL("GRANT CONNECT ON DATABASE postgres TO {}").format(
                                sql.Identifier("atlas_" + role)
                            )
                        )
            finally:
                engine.dispose()
            self.owner = Store(self.urls["owner"])
            self.memberships = MembershipRegistry(self.owner)
            self.observations = {}
            for role in ("api", "worker"):
                store = Store(self.urls[role], purpose=role)
                try:
                    with store.engine.connect() as conn:
                        row = dict(
                            conn.execute(
                                text(
                                    "SELECT current_user AS role, rolsuper AS superuser, rolbypassrls AS bypass FROM pg_roles WHERE rolname=current_user"
                                )
                            )
                            .mappings()
                            .one()
                        )
                        assert row == {
                            "role": "atlas_" + role,
                            "superuser": False,
                            "bypass": role == "worker",
                        }
                        self.observations[role] = row
                    denied = (
                        ["UPDATE atlas.memberships SET active=false WHERE false"]
                        if role == "api"
                        else [
                            "SELECT * FROM atlas.memberships",
                            "UPDATE atlas.reviews SET version=version WHERE false",
                        ]
                    )
                    for statement in denied:
                        try:
                            with store.engine.begin() as connection:
                                connection.exec_driver_sql(statement)
                        except DBAPIError as error:
                            assert getattr(error.orig, "sqlstate", None) == "42501"
                        else:
                            raise AssertionError("Runtime privilege unexpectedly admitted")
                    self.observations[role]["forbidden_operations_refused"] = len(denied)
                finally:
                    store.engine.dispose()
        except BaseException:
            self.close()
            raise
        finally:
            password_file.unlink(missing_ok=True)

    def command(self, binary, *args):
        subprocess.run(
            [str(self.binaries / binary), *args],
            check=True,
            stdout=self.log,
            stderr=self.log,
            timeout=45,
            env=self.command_environment,
        )

    def identity(self):
        with self.owner.engine.connect() as connection:
            return tuple(
                connection.execute(
                    text(
                        "SELECT (SELECT system_identifier FROM pg_control_system()), pg_postmaster_start_time()"
                    )
                ).one()
            )

    def restart(self):
        before = self.identity()
        self.owner.engine.dispose()
        self.command("pg_ctl", "-D", str(self.data), "-m", "fast", "-w", "restart")
        self.owner = Store(self.urls["owner"])
        self.memberships = MembershipRegistry(self.owner)
        after = self.identity()
        assert before[0] == after[0] and before[1] != after[1]
        return {"same_cluster_identifier": True, "postmaster_start_changed": True}

    def dump(self, path):
        self.command(
            "pg_dump",
            "--format=custom",
            "--schema=atlas",
            "--no-owner",
            "--no-acl",
            "--file=" + str(path),
        )
        path.chmod(0o600)

    def close(self):
        if self.owner is not None:
            self.owner.engine.dispose()
            self.owner = None
        try:
            if self.running or (self.data / "postmaster.pid").exists():
                self.command("pg_ctl", "-D", str(self.data), "-m", "fast", "-w", "stop")
                self.running = False
        finally:
            if not self.log.closed:
                self.log.close()
