# PostgreSQL checks on each commit

The `postgres` job in `.github/workflows/ci.yaml` builds the same checksum-pinned PostgreSQL and pgvector sources used by the local integration runtime. It starts a dedicated loopback database and runs the deterministic integration groups. It does not connect to a deployed database or need repository secrets.

The database administrator is used to create disposable schemas, apply migrations and provision temporary test roles. Runtime-boundary tests reconnect as the API and worker roles with their own generated passwords. The API has no superuser, table-owner or RLS-bypass privileges. The trusted worker deliberately has BYPASSRLS for cross-workspace queue processing, with narrower table grants; that is an explicit service trust boundary, not tenant isolation from a compromised worker.

The groups cover migrations and rollback, tenant policies and pooled-context reset, revoked membership, grant/policy drift, HTTP document intake, vector-cache integrity, competing consumers, stale leases, cancellation and atomic publication. Some correctness cases use synthetic vectors and controlled model results. Passing them does not establish semantic retrieval quality or model accuracy.

The optional CPU embedding-model group is excluded explicitly. Its model download and historical local result remain separate; it is not silently counted as a CI pass. The current gate expects the other seventeen groups, including six named critical boundaries. A failed, skipped, duplicated or missing execution cannot produce a passing acceptance report. Newly added integration groups are included by the source inventory; changes to the selected inventory require review.

## Reproduce locally

With the prepared runtime and locked Python environment:

```sh
PYTHONPATH=src .runtime/bin/python scripts/local_postgres.py start
PYTHONPATH=src .runtime/bin/python scripts/verify_postgres_ci.py
PYTHONPATH=src .runtime/bin/python scripts/local_postgres.py stop
```

Use only the dedicated `portfolio_integration` database on loopback. Every group creates a random schema; fixtures remove their schemas and roles afterward. Stop a cluster only if you started it for this run. The CI job stops its disposable cluster even when verification fails.

`reports/postgres-ci.json` contains the outcome, authored group names, server/extension versions and source/evidence fingerprints. The uploaded artifact excludes connection settings, passwords, raw JUnit, database contents and test logs. A failing run writes a bounded failure report rather than reusing an older success. For local debugging, private execution logs are under `var/postgresql-ci/`.

The [current checked-in record](../reports/postgres-ci.json) identifies its execution scope. A local result is not remote CI acceptance. The workflow's own uploaded report adds its GitHub run and commit identifiers when it actually executes there. None of these checks establishes hosted TLS, durable cloud storage, a general RLS security proof or production capacity.
