# ADR 023 — Recover from an archive after deleting the source database volume

Date: 2026-10-16

## Requirement

Stack recreation with a retained volume demonstrates persistence, not disaster recovery. A recovery gate must restore actual bytes into a new empty destination and verify application behavior, not merely observe a successful backup command.

## Decision and trust boundary

Extend the disposable Compose verifier with an explicit `--backup-restore` mode. It uses only the uniquely named synthetic project created by that invocation. Add a synthetic PDF upload with original bytes and a physical source map, an operator-created membership and a controlled 384-dimensional vector cache. Retain the real HTTP-created reviewed run and queue a second job with the worker stopped. Stop API writes before taking the verification snapshot and custom-format pg_dump archive. No backup command receives passwords in its arguments.

Copy the archive into the private ignored verification directory (mode 600 under a mode-700 ancestor), hash it, delete the original Compose database volume, and start only PostgreSQL in a new cluster. Verify that no atlas tables or runtime roles exist. Check the archive hash before pg_restore. Restore with --exit-on-error, --single-transaction, --no-owner and --no-acl. Database archives omit cluster-global roles; the trusted initializer must provision fresh runtime credentials and explicit grants after restoration, before API/worker access. This is a deliberate tested recovery step, not an assumption that passwords are backed up in the archive.

Only restore this harness's trusted synthetic archive. PostgreSQL archives can execute SQL chosen by the source database owner. A checksum establishes file continuity, not that an untrusted archive is safe or authentic. Do not feed arbitrary downloaded/user-provided archives into this operator workflow.

## Verification

The operator's canonical manifest reads every atlas base table, serializes each complete row using PostgreSQL row_to_json, sorts rows and hashes them. Compare all table counts/digests before resuming writes. Including original bytea and vector columns prevents a passing check that only counts documents or jobs. All ten application/schema tables must contain seeded data before export. Schema compatibility and forced row policies are independently checked at application startup.

Reject an actual deliberately truncated archive with pg_restore, then prove the restored table manifests still match. Verify byte-identical original PDF, equal source maps, server-owned membership resolution, persistent vector cache reuse with source encoding explicitly forbidden, and cached citation integrity. Read the original approved review and exactly one approval audit event through the real API; foreign-tenant reads still fail. Start the actual worker and require the restored queued job to complete on its first attempt. Record the frozen setup/source/runner hashes, image/database identities, archive hash/size, table digests and checks in reports/backup-restore.json. Preserve reports/compose.json as the separately scoped earlier result.

## Limits

This is a quiesced local logical backup/restore on PostgreSQL 17.11/pgvector 0.8.7, not concurrent-write snapshot testing, WAL/PITR, continuous backup, production RPO/RTO, encrypted/offsite retention or AWS/RDS restore. Controlled vectors test storage fidelity, not embedding quality. Membership resolution is not a live identity-provider login. Backups include source text and originals, so treat real backups as sensitive; this drill contains only synthetic fixtures. Docker administrators and the local provisioning operator remain trusted. The verifier deletes only its own disposable stack/volume on cleanup, retaining the private archive and logs for review. Pipeline semantics remain unchanged.

References: [pg_dump](https://www.postgresql.org/docs/17/app-pgdump.html), [pg_restore](https://www.postgresql.org/docs/17/app-pgrestore.html).
