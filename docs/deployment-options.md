# Hosting decision — October 19, 2026

ATLAS is not hosted yet. Hosting must stay free, and demo recordings are deferred. The source is public; the hosted application remains unfinished. The separate model-test allowance is not an infrastructure budget.

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
| Public synthetic lab | A running baseline restricted to seeded fictional inputs, tightly bounded sessions/actions, no real uploads or model credentials, explicit history-reset limits | Dedicated local API and React lab exercised through three Chromium workflows; a dedicated local Linux image also passes constrained HTTP/restart checks; hosted HTTPS/provider behavior remains unverified. The private/local API cannot be exposed as a shortcut. |

A public lab could demonstrate the actual analysis/review workflow without pretending to provide durable customer storage. It would need explicit admission, session/isolation, origin, resource and cleanup rules plus local/browser tests before deployment. It would remain a prototype, not the full service. The separate local API boundary now has seeded-input, session, origin, budget and cleanup tests (ADR 033). A separate React workbench is now connected and checked on loopback HTTP (ADR 034); a pinned dedicated image has separate local Linux evidence (ADR 035). Provider execution and hosted HTTPS are not validated. This document does not approve public deployment.

## Next acceptance steps

The reviewed source is public and its initial CI run passed. Remaining hosting steps:

1. Select and implement the intended hosted runtime profile under the free-only constraint. Verify provider quotas, database/identity privileges, secret delivery, shutdown and teardown before creating resources.
2. Validate the actual hosted URL: login/session boundary, isolation, queue completion, citation/original access, review conflicts, restart behavior, resource rejection and persistence claims appropriate to that profile.
3. Record what actually happened, including failures. Do not label a reachable page as the full deployed application.

Recordings are deferred and are not an acceptance dependency. The already prepared static replay remains explicitly recorded and is not a substitute for a running hosted backend. Earlier paid-host price comparisons remain in Git history; they are not approved alternatives.
