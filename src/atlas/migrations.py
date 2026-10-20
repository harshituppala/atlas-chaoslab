"""Explicit versioned upgrades and fail-closed schema compatibility checks."""

import argparse
import json
import os
import re
import sqlite3
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import Index, create_engine, inspect, text
from sqlalchemy.engine import URL

from .migration_scripts.versions.r0001_baseline import schema
from .migration_scripts.versions.r0002_query_indexes import INDEXES
from .migration_scripts.versions.r0003_retrieval_cache import add_schema
from .migration_scripts.versions.r0004_memberships import add_schema as add_memberships
from .migration_scripts.versions.r0005_row_security import TENANT_TABLES, expression

HEAD = "0005"


class SchemaNotReady(Exception):
    pass


def config(connection):
    value = Config()
    value.set_main_option("script_location", str(Path(__file__).parent / "migration_scripts"))
    value.attributes["connection"] = connection
    return value


def target_schema(revision=HEAD):
    metadata = schema()
    if revision in {"0002", "0003", "0004", "0005"}:
        for name, table, columns in INDEXES:
            Index(name, *(metadata.tables[table].c[column] for column in columns))
    if revision in {"0003", "0004", "0005"}:
        add_schema(metadata)
    if revision in {"0004", "0005"}:
        add_memberships(metadata)
    return metadata


def revision(connection):
    return MigrationContext.configure(connection).get_current_revision()


def schema_differences(connection, target=HEAD):
    return compare_metadata(MigrationContext.configure(connection), target_schema(target))


def lock(connection):
    if connection.dialect.name == "postgresql":
        # Upgrade/adoption is a single-writer operation, even with multiple launchers.
        connection.execute(text("SELECT pg_advisory_xact_lock(71423901)"))
        # Refuse filtered data migration/backup checks instead of silently omitting rows.
        # This setting does not grant a bypass to an unprivileged role.
        connection.execute(text("SET LOCAL row_security = off"))
    elif connection.dialect.name == "sqlite":
        # SQLite's legacy driver otherwise executes DDL outside the logical transaction.
        if not connection.connection.driver_connection.in_transaction:
            connection.exec_driver_sql("BEGIN IMMEDIATE")


def upgrade(engine, destination="head"):
    with engine.begin() as connection:
        lock(connection)
        command.upgrade(config(connection), destination)


def adopt_legacy(engine):
    """Stamp only the exact known prototype, then apply the index migration."""
    with engine.begin() as connection:
        lock(connection)
        if revision(connection) is not None:
            raise SchemaNotReady("Database already has a revision; use upgrade")
        if schema_differences(connection, "0001"):
            raise SchemaNotReady("Unversioned schema differs from the recognized prototype")
        command.stamp(config(connection), "0001")
        command.upgrade(config(connection), "head")


def ensure_ready(engine, bootstrap_empty_sqlite=True):
    with engine.connect() as connection:
        empty = not inspect(connection).get_table_names()
    if empty and engine.dialect.name == "sqlite" and bootstrap_empty_sqlite:
        upgrade(engine)
    with engine.connect() as connection:
        if revision(connection) != HEAD:
            raise SchemaNotReady(
                "Database revision is unavailable or outdated; run an explicit migration"
            )
        if schema_differences(connection):
            raise SchemaNotReady("Database schema drift detected; startup refused")
        if connection.dialect.name == "postgresql":
            check_row_policies(connection)


def check_row_policies(connection):
    rows = (
        connection.execute(
            text(
                "SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity, p.polname, p.polcmd, "
                "p.polpermissive, p.polroles, pg_get_expr(p.polqual,p.polrelid) AS predicate, "
                "pg_get_expr(p.polwithcheck,p.polrelid) AS write_check "
                "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                "LEFT JOIN pg_policy p ON p.polrelid=c.oid WHERE n.nspname=current_schema() "
                "AND c.relname = ANY(:tables)"
            ),
            {"tables": list((*TENANT_TABLES, "memberships"))},
        )
        .mappings()
        .all()
    )
    if len(rows) != len(TENANT_TABLES) + 1:
        raise SchemaNotReady("Database row policy drift detected")

    def normalized(value):
        return re.sub(r"\s+|[()]|::text", "", value or "").lower()

    for row in rows:
        expected = normalized(expression(row["relname"]))
        if not (
            row["relrowsecurity"]
            and row["relforcerowsecurity"]
            and row["polname"] == "atlas_identity"
            and row["polcmd"] == "*"
            and row["polpermissive"]
            and list(row["polroles"]) == [0]
            and normalized(row["predicate"]) == expected
            and normalized(row["write_check"]) == expected
        ):
            raise SchemaNotReady("Database row policy drift detected")


def backup_sqlite(path):
    """Consistent private SQLite backup, not a copy of a possibly active journal."""
    root = Path("var/backups")
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    with tempfile.NamedTemporaryFile(
        prefix="before-migration-" + stamp + "-", suffix=".db", dir=root, delete=False
    ) as handle:
        destination = Path(handle.name)
    try:
        with (
            sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True) as original,
            sqlite3.connect(destination) as backup,
        ):
            original.backup(backup)
        return destination
    except Exception:
        destination.unlink(missing_ok=True)
        raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["upgrade", "adopt-legacy", "check"])
    parser.add_argument(
        "--postgres-config", help="Private ignored config file, never a URL on the command line"
    )
    args = parser.parse_args()
    if args.postgres_config:
        values = json.loads(Path(args.postgres_config).read_text())
        url = URL.create(
            "postgresql+psycopg",
            username=values["user"],
            password=values["password"],
            host=values["host"],
            port=values["port"],
            database=values["dbname"],
            query={"sslmode": values["sslmode"]},
        )
    else:
        url = os.getenv("ATLAS_DATABASE_URL", "sqlite:///var/atlas.db")
    engine = create_engine(url)
    try:
        if (
            args.action != "check"
            and engine.dialect.name == "sqlite"
            and engine.url.database
            and Path(engine.url.database).exists()
        ):
            backup = backup_sqlite(engine.url.database)
            print(json.dumps({"private_backup": str(backup)}))
        if args.action == "adopt-legacy":
            adopt_legacy(engine)
        elif args.action == "upgrade":
            upgrade(engine)
        ensure_ready(engine, bootstrap_empty_sqlite=False)
        print(json.dumps({"schema_ready": True, "revision": HEAD}))
    except SchemaNotReady as exc:
        raise SystemExit(str(exc)) from None
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
