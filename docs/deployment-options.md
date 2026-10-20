# Hosting decision — October 20, 2026

The [fictional ATLAS review lab](https://atlas-review-lab.onrender.com) runs on a free Render instance. The full review service remains local because it still needs managed sign-in and durable hosted storage.

## What a host must preserve

The local application has an API, a separate worker and a database-backed queue. Reviews, source originals and job ownership need durable storage. Runtime API/worker roles differ from the migration owner. A hosted service also needs HTTPS, secrets outside source, a tested identity flow and server-owned workspace membership. The existing token verifier does not implement browser sign-in by itself.

Putting the current SQLite/local-token demo on a public URL would skip those requirements. Successful local Compose or database recovery checks do not make that a deployment configuration.

## Render free hosting: constraints checked

Render's [free-instance documentation](https://render.com/docs/free), checked October 19, says free web services sleep after 15 idle minutes and lose local filesystem changes on restart, redeploy or sleep. Persistent disks are unavailable on free web services. Free Postgres expires after 30 days and has no managed backup support. Other service types such as standalone background workers do not offer free instances.

The workspace shares 750 free instance hours monthly. Bandwidth/build overages can be billed when a payment method exists; absence of paid compute does not alone prove a zero invoice. The workspace and shared quotas were inspected before creating the lab. Check them again before adding another service or build; a free instance does not reserve the entire workspace's allowance.

These constraints rule out copying the current three-service Compose stack unchanged and calling it a durable free deployment.

## Two application profiles, with different claims

| Profile | Intended behavior | Current state |
| --- | --- | --- |
| Full review service | Managed access, durable originals/reviews/jobs, private database roles, separate worker and tested recovery | Local implementation/evidence; a coherent free deployment combination remains unverified. |
| Public synthetic lab | A running baseline restricted to seeded fictional inputs, tightly bounded sessions/actions, no real uploads or model credentials, explicit history-reset limits | Free Render deployment with targeted real HTTPS, desktop/mobile Chromium and controlled restart evidence. Temporary sessions reset as advertised. Cold starts and usage-limit behavior remain to observe; the private API stays separate. |

The lab demonstrates the actual extractive analysis and review workflow using fictional records. Hosted checks include secure cookies, source spans, human review, stale conflicts, session isolation and restart reset. The Render workspace showed Hobby with no card on file; the selected instance is Free, with manual deployment and no persistent disk or model credentials. Billing and included usage are shared with other services. The [hosting decision](adr/036-hosted-lab-execution-budget.md) records the first timeout, the bounded correction and acceptance limits.

## Remaining hosting work

1. Observe cold starts and shared usage limits for the running free lab. Check quotas before another build or service.
2. Prepare a separate durable review-service deployment with real sign-in, private database roles, retained originals/reviews and tested recovery.
3. Record what actually happened, including failures. Do not label a reachable page as the full deployed application.

The static replay remains available for inspecting a saved run. It does not execute analysis or preserve review state.
