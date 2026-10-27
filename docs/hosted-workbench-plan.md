# Taking the private workbench online

The public lab is a temporary fictional exercise. It is not the place to add real uploads or reuse the private workbench database. The next deployment must preserve the private application's identity and data boundaries.

This is an acceptance plan, not a provisioned service or a hosting approval. No additional account, database, public callback or workspace grant has been created for it.

## What already works

One real Cognito identity completed a local review over loopback TLS and SQLite. Separate PostgreSQL runs exercised restricted runtime roles, queue recovery and backup restoration. Those results reduce uncertainty about individual parts; they do not prove that a hosted combination works. See [local sign-in](adr/053-real-cognito-local-acceptance.md), [database CI](postgres-ci.md) and [the operator guide](deployment.md).

## Keep the first deployment small

Use one API process, one baseline worker and a durable PostgreSQL database. Keep paid model jobs disabled. Originals, reviews, jobs, memberships and audit records must outlive a web-service restart. Temporary login sessions may end on restart; the interface must say so and let an authorized user sign back in to recover saved work.

The current process-local session registry rules out an unplanned multi-instance API deployment. A host without a free background-worker service would need a separately tested process-lifecycle arrangement or an explicitly approved paid worker. Do not start a worker inside an API request or weaken the database roles to make a host fit.

## Decide before provisioning

| Decision | Required evidence before approval |
| --- | --- |
| Compute and database provider | Written cost/usage limits, sleep/expiry behavior, regional availability and an exit/cleanup path. A model-testing allowance does not pay for recurring infrastructure. |
| Database permissions | A dedicated migration owner, restricted API role and dedicated worker role can be created on that actual provider. The worker needs BYPASSRLS; the API must not have it. Neither runtime identity may own tables, create schemas or inherit elevated roles. |
| Browser entry point | Exact HTTPS origin, callback, audience and API scope are prepared for review. Existing loopback callbacks are not public-host approval. |
| Workspace access | Intended identity, workspace, role and revocation path are explicit. Provider login alone must grant no membership. |
| Original documents | Existing database-backed originals remain retained; local container storage cannot be the only copy. Limits and restore coverage are known before uploads are enabled. |

The existing free Render lab is not approval for a new service. If the chosen provider cannot satisfy a role or recovery boundary, choose another arrangement; do not relax the boundary silently. Provider compatibility and cost remain unverified until checked against that provider's current documentation and actual account.

## Prepare locally, then test the hosted combination

1. Prepare separate operator, API and worker configuration. The runtime receives no migration-owner credential. Reject inherited demo credentials and model settings, as the managed factory already does. Keep settings private and out of images, reports and logs.
2. Exercise the exact image and process entry points locally, including worker failure, API shutdown, termination forwarding and restart. Prove that a stopped worker cannot leave the service apparently healthy indefinitely. A loopback-only [supervisor prototype](../scripts/run_managed_workbench.py) now has [local lifecycle controls](../reports/workbench-supervisor.json). The actual joined API/worker image, worker analysis descendants and hosted teardown still need acceptance.
3. Configure HTTPS and the exact trusted proxy boundary. Keep callback query strings, cookies and tokens out of application and proxy logs. Check actual host behavior; disabling application access logs alone does not prove proxy redaction.
4. Start with fictional PDF/DOCX sources. Complete real browser sign-in, upload, queued baseline analysis, citation inspection, original-byte download, review conflict and audit inspection. Record the execution mode before running analysis.
5. Restart the deployed API and worker. Sign back in, reopen the same analysis and verify originals, review versions and audit history. An expired session must not be mistaken for lost data.
6. Restore a logical backup into a separate disposable database, reapply reviewed runtime grants and compare the seeded source hashes, review versions and queue state. Never test restoration by overwriting the only copy.
7. Check an unassigned identity/workspace, revoked membership, expired session, callback replay, cross-origin writes and provider failure. Record manual observations separately from automated tests.
8. Publish only aggregate acceptance facts and fictional screenshots. Keep identities, database endpoints, configuration, contracts and session artifacts private. Expand the hosted claim only after its specific checks pass.

## What completion means

A reachable page is insufficient. Completion requires a known deployed revision, real identity-to-review acceptance, persistence across restart, a successful separate restore and a useful explanation of remaining limits. Final recordings should show those verified steps and distinguish live baseline execution from saved model results.

## Local supervisor preparation

The prototype reads a private JSON file with exactly `api_database`, `worker_database` and an absolute `login_settings` path. Database URLs require separate PostgreSQL logins on the same endpoint/database and `sslmode=verify-full`; live role checks remain the application’s responsibility. It forwards each credential only to its intended process, leaves model jobs disabled and inherits no AWS, demo or proxy settings. The parent is trusted and holds both credentials; this is not isolation from a compromised same-user process.

The API binds loopback, uses one process and disables access logs and proxy-header trust. Unexpected API or worker exit, including exit zero, stops its sibling and returns failure. Operator SIGTERM/SIGINT requests paired shutdown. No automatic restart hides a crash or replays paid work. The supervisor does not detect a hung process.

Fifteen controls passed natively and in a non-root, network-disabled Linux container with current source mounted read-only. Four cases use real stand-in processes; the others check configuration, environments and construction failure. They do not run the real API, worker, database or provider. The full native suite passed 926 tests, with eighteen optional PostgreSQL groups skipped.

Process-group cleanup has a deliberate limit: a descendant that starts a new session is outside its group. The current analysis worker does that for bounded analysis. Before this becomes a hosted entry point, verify whole-container teardown and in-flight-job recovery using the actual worker; do not mistake the stand-in tests for that proof. No public bind, provider configuration or deployment was added here.

## Container cleanup check

A [local Docker exercise](../reports/supervisor-container.json) now tests the boundary that process-group signals alone cannot cover. It runs the actual supervisor as PID1 and the actual bounded-child primitive, with stand-ins for the API and worker. The analysis stand-in starts a separate session and writes an atomic heartbeat. Operator shutdown stops the container and heartbeat; restarting creates a fresh heartbeat without resuming the old one. An unexpected worker exit also stops the container, returns failure and ends its detached analysis heartbeat.

The verifier uses an existing local image with current source mounted read-only, no network, no credentials, no Docker socket and only a synthetic writable proof directory. It removes its own container afterward. Reproduce it with `scripts/verify_supervisor_container.py --image <existing-local-image>`, using the project Python environment and `PYTHONPATH=src`. It does not build or pull an image.

This establishes the local container boundary for these controls. It does not establish a built managed application image, real API/queue recovery, a live PostgreSQL role or backup restore, hung-worker detection or hosted sign-in. Those remain the next acceptance gates.

## Queue and separate-worker integration

The [joined local HTTPS workflow](../reports/browser-login-separate-worker.json) now uses the actual managed API, database-backed queue, separate baseline worker and isolated analysis child. A job submitted while the worker is stopped stays queued; a new worker then completes it, after which the browser opens the source and records a review. Manual fixture processing is disabled for this mode. The identity provider is synthetic and storage is SQLite.

This closes the gap between manual in-process fixture execution and a real queue consumer for that local setup. It does not establish API restart persistence, the supervisor's combined hosted image, PostgreSQL TLS/roles, separate backup restore or real deployed identity acceptance. Keep those gates open.

The joined synthetic-login workflow also now passes against a fresh local PostgreSQL cluster with the actual restricted API and worker roles and a separate fixture membership operator. [The record](../reports/browser-login-postgres-worker.json) includes the role attributes and three refused privileged operations. This removes the SQLite-only integration gap for that local workflow. Database transport remains authenticated loopback without TLS; provider-specific verified TLS, API/database restart, restore and hosted sign-in remain open.
