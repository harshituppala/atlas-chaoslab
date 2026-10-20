# ADR 008: versioned migrations and explicit prototype adoption

Status: locally executed on SQLite and PostgreSQL 18.6; production rollout and PostgreSQL backup restore remain separate gates.

Startup no longer creates arbitrary missing tables. Alembic revision 0001 freezes the six-table prototype without importing mutable runtime models. Revision 0002 adds compound indexes matching the tenant-scoped history/audit queries. The index upgrade/downgrade changes no document or analysis rows. Downgrading the baseline to an empty database is refused because that would destroy user data.

Application startup requires the expected revision and compares physical schema metadata against the frozen target. Missing/outdated/future revisions and schema drift refuse startup. Readiness also checks the revision. Empty local SQLite databases bootstrap through the same migrations for development convenience. PostgreSQL deployment must run an explicit migration before starting API/worker processes.

Existing unversioned databases require `adopt-legacy`. It stamps only the exact recognized prototype after metadata comparison, then runs the index upgrade. Unknown/partial schemas are refused. PostgreSQL uses a transaction-level advisory lock to serialize migration writers. SQLite uses `BEGIN IMMEDIATE` so DDL really participates in the transaction; a logical SQLAlchemy transaction alone is insufficient under the legacy SQLite driver.

Tests inject a failure after the first index and prove that neither partial DDL nor a new revision commits. This was executed on both SQLite and PostgreSQL. Index-only rollback followed by re-upgrade preserves existing data. SQLite consistent backup/restore was exercised on a disposable database. Prototype adoption preserves authored rows on both databases.

The running local SQLite demo was stopped, backed up via SQLite's backup API into a private ignored file, adopted and restarted. Hash comparisons proved all previously stored rows in six tables remained unchanged at that migration point. The migration CLI automatically backs up an existing SQLite database before upgrade/adoption. PostgreSQL production backup approval and restore proof are not inferred from that local SQLite exercise.

CLI commands: `PYTHONPATH=src .runtime/bin/python -m atlas.migrations upgrade`, `adopt-legacy`, or `check`. A PostgreSQL connection can come from the existing environment configuration or `--postgres-config` pointing to a private file; connection secrets are not command-line arguments or migration configuration logs. Test schemas are disposable and isolated from the application demo.

These migrations do not add row-level security, database role separation, tenant deletion, full foreign-key/integrity policy, persistent embeddings or deployed rollback orchestration. Index existence is verified; no query-latency improvement is claimed without a representative measurement.

Source: [Alembic's shared-connection transaction pattern](https://alembic.sqlalchemy.org/en/latest/cookbook.html#sharing-a-connection-across-one-or-more-programmatic-migration-commands).
