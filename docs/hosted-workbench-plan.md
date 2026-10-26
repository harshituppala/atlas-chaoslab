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
2. Exercise the exact image and process entry points locally, including worker failure, API shutdown, termination forwarding and restart. Prove that a stopped worker cannot leave the service apparently healthy indefinitely. This process arrangement still needs implementation and verification.
3. Configure HTTPS and the exact trusted proxy boundary. Keep callback query strings, cookies and tokens out of application and proxy logs. Check actual host behavior; disabling application access logs alone does not prove proxy redaction.
4. Start with fictional PDF/DOCX sources. Complete real browser sign-in, upload, queued baseline analysis, citation inspection, original-byte download, review conflict and audit inspection. Record the execution mode before running analysis.
5. Restart the deployed API and worker. Sign back in, reopen the same analysis and verify originals, review versions and audit history. An expired session must not be mistaken for lost data.
6. Restore a logical backup into a separate disposable database, reapply reviewed runtime grants and compare the seeded source hashes, review versions and queue state. Never test restoration by overwriting the only copy.
7. Check an unassigned identity/workspace, revoked membership, expired session, callback replay, cross-origin writes and provider failure. Record manual observations separately from automated tests.
8. Publish only aggregate acceptance facts and fictional screenshots. Keep identities, database endpoints, configuration, contracts and session artifacts private. Expand the hosted claim only after its specific checks pass.

## What completion means

A reachable page is insufficient. Completion requires a known deployed revision, real identity-to-review acceptance, persistence across restart, a successful separate restore and a useful explanation of remaining limits. Final recordings should show those verified steps and distinguish live baseline execution from saved model results.
