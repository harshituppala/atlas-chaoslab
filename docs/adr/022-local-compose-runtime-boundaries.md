# ADR 022 — Initialize the local container database before restricted runtime startup

Date: 2026-10-16

## Decision

The previous Compose target passed one database owner connection to both services and did not run migrations. Current runtime guards rightly refuse that configuration. Preserve those guards: run a one-shot initializer after PostgreSQL health, migrate explicitly, create/check dedicated roles and apply the reviewed table grants. API and worker start only after successful initialization. Repeated initialization reuses only roles with the expected attributes. This is a local fixed-host/fixed-database launcher requiring explicit ATLAS_LOCAL_STACK opt-in, not a production provisioner.

Mount only each service's secret file. The initializer receives provisioning passwords; PostgreSQL receives its owner password file; API and worker get their own credentials. Do not embed passwords in Compose environment declarations, image layers or public reports. Construct the private database URL inside the process. Fixed initialization errors suppress SQL/connection exception details. Files use mode 644 beneath a mode-700 host directory so UID 10001 can read their individual bind mounts. Host/Docker administrators and authorized service processes remain trusted. This is not encrypted managed-secret storage.

PostgreSQL, worker and initializer share an internal network. The API also needs a frontend bridge for Docker Desktop host-port forwarding; the all-internal experiment reached readiness but could not publish a usable host port. Publish only the API, only on loopback. API outbound networking remains possible. All application services use UID 10001, no-new-privileges, dropped capabilities, and process/memory budgets. Do not describe these controls as arbitrary-code isolation. Paid model admission is disabled and no provider credentials are mounted.

## Executed evidence

scripts/verify_compose.py creates a unique disposable stack with generated synthetic principals and secrets, freezes setup/source/runner hashes before the build and checks them after execution. It records actual image IDs and database/extension/schema versions. The real HTTP/worker test covers idempotent admission, API container recreation while work is queued, source/citation integrity, foreign-tenant refusal, concurrent review conflict, unfiltered SQL visibility under the restricted API role, and approved review/audit persistence after full stack recreation with its volume retained. Repeated initialization executes the same grants safely. Inspected configurations contain no generated secret values. Cleanup removes only the verifier's named project and volume.

Measured results are reports/compose.json. Native PostgreSQL eighteen-group results and image offline-suite evidence are separate artifacts with separate scopes. Local unit tests cover secret-error redaction and opt-in/connection boundaries. Pipeline semantics did not change, so extractive/model pipeline versions remain unchanged.

## Limits

One synthetic workflow on PostgreSQL 17.11/pgvector 0.8.7 and Linux ARM64 is not load evidence, the entire database integration suite in containers, live-provider execution, managed identity, TLS, encrypted backup or AWS deployment. No vector-quality benchmark ran in this stack. Retaining a Docker volume across recreation proves persistence, not backup recovery. Tags may move; actual image IDs are recorded. Hashes identify local on-disk inputs and do not attest installed software against a malicious local actor; frontend build input identity is not captured here. Docker stores images/volumes in its own support directory. Continue with explicit backup/restore before considering deployment acceptance.

References: [Compose secret files](https://docs.docker.com/compose/how-tos/use-secrets/), [startup dependency conditions](https://docs.docker.com/compose/how-tos/startup-order/), [Docker networking](https://docs.docker.com/engine/network/).
