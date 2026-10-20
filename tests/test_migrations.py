import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import MetaData, create_engine, event, inspect, select, text

from atlas.documents import metadata as document_metadata
from atlas.execution import execute
from atlas.migration_scripts.versions.r0001_baseline import schema
from atlas.migrations import (
    HEAD,
    SchemaNotReady,
    adopt_legacy,
    backup_sqlite,
    config,
    ensure_ready,
    lock,
    revision,
    schema_differences,
    target_schema,
    upgrade,
)
from atlas.pg_retrieval import metadata as retrieval_metadata
from atlas.security.memberships import metadata as membership_metadata
from atlas.store import Store
from atlas.store import metadata as runtime_metadata


def test_fresh_migration_and_runtime_schema_agree(tmp_path):
    url = "sqlite:///" + str(tmp_path / "fresh.db")
    store = Store(url)
    with store.engine.connect() as connection:
        assert revision(connection) == HEAD
        assert schema_differences(connection) == []
    # Catch model changes that are missing a reviewed migration.
    runtime = target_schema()
    for metadata in (runtime_metadata, document_metadata, retrieval_metadata, membership_metadata):
        for table in metadata.tables.values():
            expected = runtime.tables[table.name]
            assert list(table.c.keys()) == list(expected.c.keys())
            assert {index.name for index in table.indexes} == {
                index.name for index in expected.indexes
            }
    merged = MetaData()
    for metadata in (runtime_metadata, document_metadata, retrieval_metadata, membership_metadata):
        for table in metadata.tables.values():
            table.to_metadata(merged)
    with store.engine.connect() as connection:
        assert compare_metadata(MigrationContext.configure(connection), merged) == []


def test_existing_database_requires_explicit_verified_adoption(tmp_path):
    url = "sqlite:///" + str(tmp_path / "legacy.db")
    engine = create_engine(url)
    schema().create_all(engine)
    # A previously saved source snapshot must survive stamp/index upgrades unchanged.
    body = json.loads(Path("datasets/demo.json").read_text())
    payload = execute(body)
    with engine.begin() as connection:
        connection.execute(
            schema()
            .tables["runs"]
            .insert()
            .values(
                id="preserved",
                tenant="a",
                key="legacy-key",
                fingerprint="digest",
                created="2026-10-14T00:00:00+00:00",
                payload=payload,
            )
        )
    with pytest.raises(SchemaNotReady):
        Store(url)
    adopt_legacy(engine)
    with engine.connect() as connection:
        assert revision(connection) == HEAD
        assert connection.execute(select(schema().tables["runs"].c.payload)).scalar_one() == payload
    ensure_ready(engine)


def test_adoption_refuses_unknown_schema_without_stamping(tmp_path):
    engine = create_engine("sqlite:///" + str(tmp_path / "unknown.db"))
    schema().create_all(engine)
    with engine.begin() as connection:
        connection.exec_driver_sql("ALTER TABLE runs ADD COLUMN private_drift TEXT")
    with pytest.raises(SchemaNotReady, match="differs"):
        adopt_legacy(engine)
    with engine.connect() as connection:
        assert revision(connection) is None
        assert "alembic_version" not in inspect(connection).get_table_names()


def test_drift_or_future_revision_refuses_startup(tmp_path):
    engine = create_engine("sqlite:///" + str(tmp_path / "drift.db"))
    upgrade(engine)
    with engine.begin() as connection:
        connection.execute(text("UPDATE alembic_version SET version_num='future-release'"))
    with pytest.raises(SchemaNotReady, match="revision"):
        ensure_ready(engine)
    with engine.begin() as connection:
        connection.execute(text("UPDATE alembic_version SET version_num=:head"), {"head": HEAD})
        connection.exec_driver_sql("DROP INDEX ix_runs_tenant_created")
    with pytest.raises(SchemaNotReady, match="drift"):
        ensure_ready(engine)


def test_index_upgrade_rolls_back_ddl_and_revision_then_recovers(tmp_path):
    engine = create_engine("sqlite:///" + str(tmp_path / "rollback.db"))
    upgrade(engine, "0001")

    def injected_failure(_connection, _cursor, statement, _parameters, _context, _many):
        if statement.startswith("CREATE INDEX ix_audit_tenant_resource_time"):
            raise RuntimeError("Authored migration failure after the first index")

    event.listen(engine, "before_cursor_execute", injected_failure)
    with pytest.raises(RuntimeError):
        upgrade(engine)
    event.remove(engine, "before_cursor_execute", injected_failure)
    with engine.connect() as connection:
        assert revision(connection) == "0001"
        assert "ix_runs_tenant_created" not in {
            index["name"] for index in inspect(connection).get_indexes("runs")
        }
    upgrade(engine)
    ensure_ready(engine)
    # The index-only rollback is reversible without deleting application rows.
    with engine.begin() as connection:
        lock(connection)
        command.downgrade(config(connection), "0001")
    with pytest.raises(SchemaNotReady):
        ensure_ready(engine)
    upgrade(engine)
    ensure_ready(engine)


def test_consistent_private_backup_can_restore_saved_data(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    original = tmp_path / "source.db"
    with sqlite3.connect(original) as connection:
        connection.execute("CREATE TABLE fixture (value TEXT)")
        connection.execute("INSERT INTO fixture VALUES ('authored synthetic value')")
    backup = backup_sqlite(original)
    assert backup.stat().st_mode & 0o777 == 0o600
    with sqlite3.connect(original) as connection:
        connection.execute("DELETE FROM fixture")
    # Exercise the actual backup restore API into another owned disposable file.
    restored = tmp_path / "restored.db"
    with sqlite3.connect(backup) as saved, sqlite3.connect(restored) as destination:
        saved.backup(destination)
    with sqlite3.connect(restored) as connection:
        assert (
            connection.execute("SELECT value FROM fixture").fetchone()[0]
            == "authored synthetic value"
        )


def test_empty_sqlite_upgrade_callers_serialize_without_partial_schemas(tmp_path):
    # This test targets database locking, not simultaneous Alembic global Python contexts.
    import subprocess
    import sys

    url = "sqlite:///" + str(tmp_path / "simultaneous.db")
    code = "import sys;from sqlalchemy import create_engine;from atlas.migrations import upgrade;upgrade(create_engine(sys.argv[1]))"

    def execute_upgrade(_):
        return subprocess.run(
            [sys.executable, "-c", code, url], capture_output=True, timeout=15
        ).returncode

    with ThreadPoolExecutor(max_workers=3) as pool:
        assert list(pool.map(execute_upgrade, range(3))) == [0, 0, 0]
    ensure_ready(create_engine(url))


def test_readiness_rejects_a_changed_schema_revision():
    from fastapi.testclient import TestClient

    from atlas.api import create_app

    app = create_app("sqlite://", {})
    with TestClient(app) as client:
        assert client.get("/readyz").json()["schema_revision"] == HEAD
        with app.state.store.engine.begin() as connection:
            connection.execute(text("UPDATE alembic_version SET version_num='future'"))
        assert client.get("/readyz").status_code == 503
