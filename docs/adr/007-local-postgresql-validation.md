# ADR 007: execute PostgreSQL integration without cloud resources

Status: seven integration groups executed locally on PostgreSQL 18.6 with pgvector 0.8.7; cloud/containers/RLS/migrations remain unvalidated.

The machine has no Docker or package manager, but already has an Apple C toolchain. An official PostgreSQL source archive was downloaded, checked against the published SHA-256 and compiled into the ignored repository runtime. pgvector was built from an exact official repository commit. Sources, build outputs, cluster data, private credentials and logs remain inside the dedicated portfolio folder. No system service or global package installation was performed.

The integration server listens on loopback port 55432 and a private local socket. Local and host connections require SCRAM authentication. Generated administrator credentials are private ignored files; passwords are not placed on command lines. This is a local test administrator, not the production application's least-privilege database identity. The local build omits ICU/readline and does not establish production TLS or cloud parity.

Each integration test creates a random schema in the dedicated `portfolio_integration` database, then removes only that owned schema. Tests refuse non-loopback hosts or other databases. Application persistence, review compare-and-swap, concurrent job claims/publication, lease/cancellation fences, atomic rollback, duplicate admission, upload quotas and tenant-scoped HTTP reads were executed against the real server. Twenty-four jobs were processed by eight competing consumers with one published result per job in that authored scenario.

A separate test loaded pgvector, persisted three small vectors and checked cosine operator ordering. This is an extension/operator smoke test. It does not validate a production semantic retrieval store, approximate indexes, tenant row-level policies or large-scale recall/latency. Those remain separate implementation and verification work.

Run the server with `PYTHONPATH=src .runtime/bin/python scripts/local_postgres.py start`, then `ATLAS_POSTGRES_CONFIG=var/postgresql/client.json PYTHONPATH=src .runtime/bin/python -m pytest tests/test_postgres.py -q --junitxml=var/postgresql/integration.xml`. Stop with the same server script's `stop` action. Ordinary tests skip the opt-in PostgreSQL groups when that private config is not supplied. The JSON report records actual JUnit evidence, server identity, source/test digests and runtime-source provenance; it never contains connection secrets.

Versioned database migrations, fail-closed schema compatibility, least-privilege API/worker roles, row-level isolation, backup/restore and container/deployed tests are still required before a production claim.

Sources: [PostgreSQL source/build documentation](https://www.postgresql.org/docs/18/install-make.html), [official release archive](https://ftp.postgresql.org/pub/source/v18.6/), [pgvector](https://github.com/pgvector/pgvector).
