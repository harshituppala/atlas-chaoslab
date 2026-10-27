# Recover the database before reopening the workspace

Date: October 27, 2026. Status: local synthetic-provider recovery passed. Hosted recovery remains open.

The application-process check left PostgreSQL running. Two additional modes now test what happens when the database process restarts, and when a logical backup is restored into a separate fresh cluster.

Both modes stop the API and worker after a seeded analysis and human review. A canonical digest records every row in all ten application tables, including empty tables. In restart mode, the PostgreSQL postmaster changes while the cluster identifier stays the same. All table digests must match before the application reopens.

Restore mode writes a private logical archive and checks its checksum before and after restoration. A truncated copy must fail archive admission. The source cluster stops, but its files are retained. A separate destination starts with no application tables and a different cluster identifier. Runtime roles and credentials are created there independently; reviewed grants are reapplied after restoration. All application table digests must match the source before the new API and worker start.

The first restore attempt exposed a missing prerequisite: the schema-filtered archive did not include the `public.vector` dependency. It failed before a successful report could be written. The destination fixture now creates the reviewed pgvector extension before restoring its dependent columns. It does not download an extension or accept an external database target.

Each mode passed fifteen browser groups. After fresh sign-in, the restored run, review and audit history matched the browser’s saved values, and the old session remained unusable. The new destination also passed the restricted-role checks and three privilege refusals. The API-only restart mode still passed fourteen groups; the native suite passed 929 tests with eighteen optional database groups skipped.

[Database restart evidence](../../reports/managed-postgres-database-restart.json) and [separate restore evidence](../../reports/managed-postgres-restore.json) record these as distinct runs. The seed covers a completed baseline analysis, review, audit and membership; empty tables matching does not demonstrate recovery of uploaded original bytes or populated vector caches. Those have separate earlier restore evidence.

The provider is synthetic, and PostgreSQL uses authenticated loopback TCP without database TLS. API shutdown reached the fixture’s two-second connection-drain deadline in both modes, with zero running tasks reported cancelled. These results establish the recorded local recovery behavior, not uninterrupted service, a cloud backup policy, verified database TLS, hostile-backup handling or hosted Cognito acceptance. The archive is created by this trusted fixture; arbitrary backups must not be supplied to it.

No model, cloud service or deployed application changed. The frozen evaluation and prior reservations remain untouched.
