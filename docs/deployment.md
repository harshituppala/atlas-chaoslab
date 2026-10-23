# Deployment gate and cost discipline

**The application has not been deployed to AWS. Restricted Bedrock inference has executed within an approved test allowance; application infrastructure has not been provisioned.**

The local Compose file is a test target, not a validated deployment. Docker Desktop is installed, and the application image has executed on Linux ARM64 as UID 10001: dependency consistency, the offline backend suite, and a real HTTP/worker/SQLite restart and review-race workflow. See reports/container.json and ADR 021. The Compose/PostgreSQL stack now passes the separately recorded disposable workflow in reports/compose.json: explicit initialization, actual restricted logins, forced row policies, real API/worker execution, competing reviews and full stack recreation with retained database state. See ADR 022 for network/secrets limits. The complete local PostgreSQL suite has passed eighteen real groups on a private PostgreSQL 18.6 build, including restricted runtime logins, forced row policies and controlled model-job publication. The entire native PostgreSQL integration suite has not been run against the container database; its eighteen-group evidence remains separate. A separate local logical backup/restore drill now deletes the synthetic source volume and restores a new empty cluster, checking full table content and recovered application behavior (reports/backup-restore.json, ADR 023). Deployed migration rollout, production backup scheduling/encryption/offsite/PITR and actual production role provisioning still require validation. The earlier stack-recreation result alone remains persistence evidence.

Hosting must remain free. Earlier AWS infrastructure proposals are historical alternatives, not approved plans. Follow the [hosting decision](deployment-options.md) before selecting a provider. Restricted Bedrock test access does not authorize an application deployment or ongoing infrastructure charges.

Required acceptance evidence:

1. Container build, health/readiness, migrations, PostgreSQL integration and simultaneous review tests.
2. Managed OIDC audience/issuer validation, role mapping, tenant row-level policies, TLS, restricted origins, secrets and rotation.
3. Body/rate/job/time/token limits; failure/restart recovery; prompt-injection and sensitive-data controls.
4. Least-privilege infrastructure configuration, private DB connectivity, storage encryption, retention/deletion, and backup restore proof.
5. Reproducible measured evaluation on held-out data, separate load tests, browser/accessibility checks, and no benchmark label leakage.
6. Dated cost estimate, approval of a maximum budget, alerts, teardown instructions, and a verified rollback.
7. Deployed URL health, authenticated end-to-end workflow, tenant isolation, persisted reviewer decision, trace correlation, and an actual deployment report.

A generated infrastructure file alone is not deployment validation. Do not add résumé language claiming AWS operation until these checks are executed.

### Private managed access-token mode

`ATLAS_TOKEN_TRUST` is a JSON object with `issuer`, `audience` and `jwks_url`, all explicitly operator-selected. The default rfc9068 profile requires RS256 resource access tokens with at+jwt type, not ID tokens; see ADR 010. The explicit cognito-resource profile described below has separately tested purpose/client/resource/scope checks (ADR 025). `ATLAS_DEMO=1` cannot be combined with this mode in the local launcher. Development bearer tokens never authorize requests in managed mode.

After an explicit migration, a trusted operator can apply a private JSON file using `PYTHONPATH=src .runtime/bin/python -m atlas.security.memberships var/membership-change.json`. The file must have mode 600, remain ignored, and contain `issuer`, `subject`, `tenant`, `role`, `active` and `expected_version`. Version 0 creates a membership; later changes require its current version. Membership writes and audit events are one transaction. This is OS/database-owner administration, not a validated production administrator login or fine-grained database role.

An authenticated request can select `X-Workspace-ID`; selection grants nothing without active server-owned membership. With exactly one active membership it can be omitted. `/api/me` reports the resolved identity and mode. The default token profile enables no browser routes. A separate opt-in factory now supplies code/PKCE exchange, opaque sessions and a sign-in interface; refresh tokens are discarded and client secrets are unsupported. Real local Cognito reviewer sign-in is recorded in ADR 053. Deployed session/proxy handling and durable hosted storage still need acceptance before exposing the full review service. See the [managed-login guide](managed-login-development.md). In-flight operations can complete after membership revocation; subsequent authorization checks observe revocation. Key revocation uses the bounded signing-key cache TTL, not immediate token introspection.

### PostgreSQL runtime roles and row policies

Apply migrations with a dedicated trusted operator, then provision separate API and worker logins. The reviewed privilege reference is `deployment/postgres-runtime-roles.sql`; it assumes schema `atlas` and deliberately sets no passwords. Configure passwords through private managed secrets, require TLS in deployment, pin the intended database/search path, and supply different private `ATLAS_DATABASE_URL` values to the API and worker. The reference is not a deployed or byte-for-byte executed provisioning claim; disposable local logins exercised its equivalent table grants.

The API refuses superusers, BYPASSRLS, table ownership, schema creation and elevated role memberships. The worker requires its dedicated nonsuperuser BYPASSRLS role, with narrower table grants and no membership access or review UPDATE privilege. Never use the migration owner as either service login. Membership administration requires a separate operator credential; do not grant the API membership writes. New tables require explicit reviewed privileges.

Migration 0005 installs forced policies for tenant data and issuer/subject membership visibility. Runtime transactions use local identity settings that reset on commit/rollback. Startup detects policy drift. These policies protect against omitted filters and pooled-context leakage, not a compromised trusted service that can choose arbitrary SQL settings. See ADR 012 for executed evidence and remaining deployment limits.


### Optional resource-bound Cognito profile

An operator can set ATLAS_TOKEN_TRUST to the following credential-free configuration shape, replacing every example with the actual approved provider/resource configuration:

```json
{
  "issuer": "https://cognito-idp.ca-central-1.amazonaws.com/ca-central-1_example",
  "audience": "https://atlas.example.invalid/api",
  "jwks_url": "https://cognito-idp.ca-central-1.amazonaws.com/ca-central-1_example/.well-known/jwks.json",
  "profile": "cognito-resource",
  "client_id": "exampleclient123",
  "required_scopes": ["atlas/api"]
}
```

This requires an access token whose signed token_use is access, client_id matches, aud is the exact resource, and scope contains each configured API scope. Resource binding is mandatory for this integration; an ordinary access token with no aud is rejected. An ID token's audience cannot substitute for resource access. Cognito typ may be absent or JWT; those headers remain rejected by the unchanged default profile. Provider keys must be at the exact pinned issuer JWKS path. Workspace membership still determines every role; groups and token role/tenant claims grant nothing.

The access-token profile was tested with real signatures and controlled JWKS; [the original report](../reports/cognito-profile.json) retains that scope. The separate browser/session factory has joined synthetic TLS/Chromium checks. An approved real Cognito directory, public client, domain and scope have also been configured, and [public discovery/key checks](../reports/provider-check.json) now pass. A real local reviewer sign-in, authenticated callback, baseline review, wrong-workspace denial and sign-out were subsequently verified in [ADR 053](adr/053-real-cognito-local-acceptance.md). That evidence covers one identity over private loopback TLS and SQLite. It does not establish a deployed identity flow or durable hosted service. Refresh tokens remain discarded.
