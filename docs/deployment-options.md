# Hosting decision — October 19, 2026

ATLAS is not hosted yet. Hosting must stay free, and demo recordings are deferred. The public source release is being prepared separately from the hosted application. The separate model-test allowance is not an infrastructure budget.

## What a host must preserve

The local application has an API, a separate worker and a database-backed queue. Reviews, source originals and job ownership need durable storage. Runtime API/worker roles differ from the migration owner. A hosted service also needs HTTPS, secrets outside source, a tested identity flow and server-owned workspace membership. The existing token verifier does not implement browser sign-in by itself.

Putting the current SQLite/local-token demo on a public URL would skip those requirements. Successful local Compose or database recovery checks do not make that a deployment configuration.

## Render free hosting: constraints checked

Render's [free-instance documentation](https://render.com/docs/free), checked October 19, says free web services sleep after 15 idle minutes and lose local filesystem changes on restart, redeploy or sleep. Persistent disks are unavailable on free web services. Free Postgres expires after 30 days and has no managed backup support. Other service types such as standalone background workers do not offer free instances.

The workspace shares 750 free instance hours monthly. Bandwidth/build overages can be billed when a payment method exists; absence of paid compute does not alone prove a zero invoice. Before creating an ATLAS service, inspect the actual workspace's usage/payment/spending settings and shared projects. Do not add a card, paid plan or trial to resolve a limit without approval.

These constraints rule out copying the current three-service Compose stack unchanged and calling it a durable free deployment.

## Two application profiles, with different claims

| Profile | Intended behavior | Current state |
| --- | --- | --- |
| Full review service | Managed access, durable originals/reviews/jobs, private database roles, separate worker and tested recovery | Local implementation/evidence; a coherent free deployment combination remains unverified. |
| Public synthetic lab | A running baseline restricted to seeded fictional inputs, tightly bounded sessions/actions, no real uploads or model credentials, explicit history-reset limits | Proposed adaptation only. The private/local API cannot be exposed as a shortcut. |

A public lab could demonstrate the actual analysis/review workflow without pretending to provide durable customer storage. It would need explicit admission, session/isolation, origin, resource and cleanup rules plus local/browser tests before deployment. It would remain a prototype, not the full service. No such public runtime profile has been implemented or approved by this document.

## Next acceptance steps

1. Publish only the reviewed source release. Keep private systems, runtime files, credentials and prior local history out.
2. Select and implement the intended hosted runtime profile under the free-only constraint. Verify provider quotas, database/identity privileges, secret delivery, shutdown and teardown before creating resources.
3. Validate the actual hosted URL: login/session boundary, isolation, queue completion, citation/original access, review conflicts, restart behavior, resource rejection and persistence claims appropriate to that profile.
4. Record what actually happened, including failures. Do not label a reachable page as the full deployed application.

Recordings are deferred and are not an acceptance dependency. The already prepared static replay remains explicitly recorded and is not a substitute for a running hosted backend. Earlier paid-host price comparisons remain in Git history; they are not approved alternatives.
