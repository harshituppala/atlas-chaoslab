# 060 — Verify database TLS before choosing a host

The earlier browser and recovery checks used a native PostgreSQL build without TLS support. They established useful application behavior, but could not show that database passwords and document contents would travel over a verified encrypted connection.

A separate local fixture now uses the cached PostgreSQL 17 image. It creates a short-lived certificate authority and server certificate, keeps system trust unchanged, and requires `sslmode=verify-full` with that exact authority. PostgreSQL accepts password authentication only over TLS. The operator, API and worker use separate logins; the application roles keep their existing grants.

Both runtime roles negotiated TLS 1.3 with a 256-bit cipher, as observed by PostgreSQL itself. Five fresh connection attempts failed as expected: an unrelated authority, a mismatched hostname, a missing authority file, plaintext transport and an expired server certificate. The expiry control replaces the fixture's certificate and reloads PostgreSQL; it does not demonstrate a safe production certificate rotation procedure.

The actual API accepted a fictional job, and a separate baseline worker process completed it through the verified database connection. All eight requirements and fourteen source spans were checked. A review and its audit event were saved; a stale review and another workspace's read were refused. The three earlier privilege refusals also hold over TLS. [The report](../../reports/postgres-tls.json) records the image, client version and source fingerprints.

This closes the local transport check, not hosted acceptance. The HTTP client runs in process with synthetic bearer identities. It does not exercise Cognito, a browser, a public proxy or the production supervisor. The earlier restart/restore reports remain separate PostgreSQL 18 fixtures without database TLS; their results have not been relabeled. Certificate distribution, renewal, revocation and recovery still need to be checked against the chosen host.

## Reproduce

With the existing local container engine running and `pgvector/pgvector:pg17` already cached:

```sh
PYTHONPATH=src .runtime/bin/python scripts/verify_postgres_tls.py
```

Use `--docker` for a nonstandard executable path. The runner never pulls an image. It records the resolved image ID, uses a unique disposable database and removes only its own container and network. Private fixture files stay under `var/postgres-tls`; the password file and private server key are removed on exit. The container runs as the database user with a read-only root, dropped capabilities and temporary database storage. Its published port is loopback-only. The dedicated Docker bridge permits egress; this is not a network sandbox. No cloud or model credentials enter the container or worker.

The first attempts exposed two fixture mistakes: the initialization server needed its key before entry-point scripts ran, and an internal-only network did not publish a host port on this engine. Neither attempt produced an accepted report. A later expiry control initially changed a setting that a command-line option overrode; replacing the configured certificate made the refusal test effective. These were fixture corrections, not application or benchmark changes.

The server/client checks follow PostgreSQL's documentation for [certificate verification](https://www.postgresql.org/docs/17/libpq-ssl.html) and [server TLS configuration](https://www.postgresql.org/docs/17/ssl-tcp.html).
