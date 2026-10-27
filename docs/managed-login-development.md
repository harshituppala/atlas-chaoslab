# Managed login development

The private API has an optional authorization-code and browser-session path. It is enabled only when an operator passes a configured `LoginExchange` into `create_app(..., login_exchange=exchange)`. Default launchers and the public fictional lab keep their existing profiles. The workbench has controlled interface checks, a joined local HTTPS check with a synthetic provider, and a real Cognito-to-review acceptance for one local user. The full service has not been deployed. See [the local acceptance](adr/053-real-cognito-local-acceptance.md) for the exact scope.

## Run the controlled checks

```sh
.runtime/bin/python scripts/verify_login_exchange.py --http-sessions
```

This records `reports/browser-sessions-offline.json`; JUnit files and logs stay under `var/login-exchange/`. It uses controlled token/key services and an in-process HTTP client with HTTPS request URLs. It does not perform a TLS handshake, enforce browser SameSite rules, use AWS credentials or create resources. The older exchange-only report retains the scope of its original run.

## Check the interface

```sh
python scripts/verify_browser_login_ui.py
```

Requires Node, pnpm and installed Playwright Chromium. Set `PLAYWRIGHT_BROWSERS_PATH` to the local browser cache when needed. The runner builds the workbench, starts a loopback server and records seven browser cases in [the UI report](../reports/browser-login-ui.json). Sign-in/API responses are intercepted. This does not perform a real TLS/provider exchange or verify cookie enforcement. See [the interface decision](adr/042-workbench-session-interface.md).

## Run the joined browser/server check

```sh
PYTHONPATH=src python scripts/verify_browser_login_https.py
```

Install Chromium into the same cache used by the runner, from the repository root:

```sh
PLAYWRIGHT_BROWSERS_PATH="$PWD/.cache/playwright" pnpm --dir apps/web exec playwright install chromium
```

The runner defaults to that workspace cache and honors an explicit `PLAYWRIGHT_BROWSERS_PATH` override. CI sets the same value for installation and all browser steps. A missing browser now produces a specific setup error; other failures report only a completed-group count publicly, with detailed synthetic diagnostics kept locally.

This needs the same frontend tools and Chromium installation. It uses real loopback TLS, redirects, cookies, signed tokens, JWKS, membership and a baseline review, with a synthetic passwordless provider. The runner accepts the same bundled Node/pnpm flags as the UI verifier. It needs no AWS credentials, administrator access or cloud resources. [ADR 044](adr/044-composed-browser-login.md) explains the local proxy, certificate pin and test-only controls. The [joined report](../reports/browser-login-https.json) does not establish real provider or hosted acceptance. Browser profiles and temporary/config/cache paths remain in the portfolio folder; the acceptance checks inspect Chromium's actual profile location. The generated TLS private key is also scheduled for deletion on normal process exit if setup fails early.

Optional login HTML uses same-origin referrers so a navigation POST can carry its Origin. It is not cached; index revalidation keeps the same policy. API and callback responses retain no-referrer. Do not weaken Origin checks to accept null to work around browser navigation failures.

## Configure an operator-run application

Copy `deployment/login-settings.example.json` to a private file under `var/`, replace every placeholder with the reviewed provider settings, and restrict it to mode 600. No AWS access key or client secret belongs in this file. The issuer and its key URL must refer to the same pool; the public client, API scope, resource audience and callback must match the reviewed console configuration. For resource binding, the resource-server identifier must equal the API audience. A scope named `review` under `https://atlas.example.invalid/api` is requested as `https://atlas.example.invalid/api/review`. A legacy `atlas/api` scope belongs to a different resource; Cognito rejects that combination before showing the password form. The settings reader now rejects it locally as well.

The explicit factory requires both settings and a database. For an existing TLS termination setup:

```sh
ATLAS_LOGIN_SETTINGS="$PWD/var/login-settings.json" \
ATLAS_DATABASE_URL="sqlite:///$PWD/var/managed-atlas.db" \
PYTHONPATH=src .runtime/bin/python -m uvicorn atlas.managed:create_from_environment \
  --factory --host 127.0.0.1 --port 8000 --no-access-log
```

This binds a private upstream only. It does not install TLS or make an HTTPS callback reachable. The browser must use the exact approved HTTPS origin through a separately configured TLS endpoint. Do not expose this upstream directly or rewrite the callback to bypass origin checks. Keep callback query strings out of proxy logs too.

Unset `ATLAS_DEMO`, `ATLAS_PRINCIPALS`, `ATLAS_TOKEN_TRUST` and `ATLAS_MODEL_JOB_SPEC` before using this profile; their presence is rejected. The entry point opens no provider connection during construction and assigns no membership. Use the separate trusted membership operator after verifying the user's real subject; never copy a role from provider claims. Model jobs remain disabled in this profile. Run a baseline worker against the same database when testing queued work.

The joined synthetic browser check now exercises this factory and settings reader. Its transport overrides remain confined to the fixture. The real Cognito directory/client/domain and scope are configured. A later [local acceptance](adr/053-real-cognito-local-acceptance.md) verified sign-in, a baseline review, persistence, wrong-workspace denial and logout for one identity over loopback TLS and SQLite. [ADR 045](adr/045-managed-application-entry.md) records the earlier entry-point decision; its original test counts describe that release.

## Check the provider before signing in

Validate the settings without opening a database or contacting AWS:

```sh
PYTHONPATH=src .runtime/bin/python scripts/check_managed_provider.py \
  --settings var/login-settings.json
```

Add `--provider` to fetch the pinned issuer's public discovery document and signing keys. The probe requires the advertised issuer, key URL, authorization endpoint and token endpoint to match the operator's settings exactly. It does not follow redirects or use URLs supplied by the discovery response. Responses have time/size limits, and signing keys pass the same RSA admission rules as token verification.

The JSON result contains source/configuration fingerprints and check results. It omits endpoint values, client IDs, key IDs and response bodies. Keep the real settings private. Failure returns a nonzero exit status with a fixed message; no success report is printed. A successful result does not establish that the client or scope is registered, that PKCE works, or that a user can access a workspace. Those need the real browser flow.

The [recorded AWS check](../reports/provider-check.json) passed public discovery and signing-key admission. It sent no user credentials or tokens. See [the decision](adr/046-checking-provider-configuration.md).

## HTTP boundary

| Route | Behavior |
| --- | --- |
| `GET /auth/config` | Announces only the enabled session mode; absent in default profiles. |
| `POST /auth/start` | Requires the exact browser Origin, creates a bound PKCE attempt and redirects to the pinned provider. |
| `GET /auth/callback` | Consumes the matching attempt, verifies the access token and sets an opaque session cookie. Redirects to a clean application URL. |
| `GET /auth/session` | Returns the session's CSRF token and expiry; it grants no workspace access. |
| `POST /auth/logout` | Requires Origin and CSRF for a valid session, then removes server state and cookies. |

Application API writes use the session cookie plus `X-Atlas-CSRF`. API requests still verify signed access claims and resolve server-owned workspace membership every time. Do not send an Authorization header alongside the cookie. A browser must clear displayed data when authentication expires; do not persist provider tokens in browser storage.

The app closes session/exchange state on shutdown. An injected token verifier remains caller-owned. State is local to one process; a restart logs users out, and multiple instances need an explicit shared-session or routing design. Provider refresh tokens are discarded. Local application logout does not log the user out of Cognito.

## Before enabling a hosted flow

Use the [hosted-workbench acceptance plan](hosted-workbench-plan.md) to keep new hosting separate from the already verified local sign-in. No provider selection, account creation or hosted access grant is implied by this guide.

Register one reviewed HTTPS callback and confirm that the provider domain belongs to the intended pool. Configure a public client for authorization code with S256, the API scopes and resource audience expected by the verifier. Membership must be assigned by the application operator, not inferred from groups or roles in provider claims.

Keep callback query strings, cookies and tokens out of server/proxy logs and traces. Configure TLS, trusted proxy handling and request-rate controls. Real browser acceptance must check the external redirect, Lax binding cookie, Strict application cookie, callback replay, provider denial/outage, membership revocation, logout and expiry. Review account access and cost before creating cloud resources; the owner must complete real sign-in without sharing credentials in chat.

[Session decision](adr/041-opt-in-browser-sessions.md) · [Exchange component](adr/040-authorization-code-exchange.md) · [Token profile](adr/025-explicit-cognito-access-profile.md)

## Private loopback without administrator privileges

The default callback remains on standard HTTPS port 443. Some development machines refuse an ordinary process binding that port. The explicit private-development alternative is `https://127.0.0.1:8443/auth/callback`, with the resource audience `https://127.0.0.1:8443/api`.

The settings reader admits that exact literal IP and port only for the callback/resource pair. Provider, issuer and signing-key endpoints keep their standard HTTPS checks. `localhost`, another loopback address, another port and a mismatched resource origin are rejected. Host and Origin checks include `:8443`; the application does not accept the port-443 Origin as equivalent.

Before using this profile, register that exact additional callback with explicit owner approval and retain the original registration. Use a short-lived local TLS certificate, a private database and the approved workspace membership. Bind the listener to `127.0.0.1`, keep access logging disabled and leave the OS trust store alone. Certificate trust and any browser warning require a human decision; the application does not install a trust bypass.

The owner-approved callback addition has been saved in Cognito, and the created owner identity has reviewer membership in one isolated local workspace. Actual loopback TLS requests passed health/auth-discovery checks and rejected an anonymous session and a mismatched port Origin. The browser rejected the local certificate; the owner must complete that handoff and the first password-change/sign-in flow. These steps do not yet establish an authenticated callback, hosted service or durable deployment. See [ADR 050](adr/050-unprivileged-local-login.md).

## Real local acceptance

The owner completed a real Cognito sign-in in Safari on October 22. The private loopback app then resolved the approved reviewer membership, completed a queued baseline analysis, opened source evidence and saved a synthetic review. Reload/reconnection preserved the review. An unassigned workspace was denied; local logout survived reload, and a fresh provider authorization restored access to the saved analysis. The [manual acceptance record](../reports/cognito-local-acceptance.json) and [decision](adr/053-real-cognito-local-acceptance.md) give the exact scope.

This used the existing private SQLite database and a short-lived local certificate. It did not validate a publicly hosted managed service, a reverse proxy, multiple instances or durable cloud storage. Provider outage, callback replay, expiry and membership revocation retain their separate controlled-test evidence. Session state stays in memory, and application logout deliberately leaves provider SSO alone.

## Run with the real queue worker

Add `--separate-worker` to `scripts/verify_browser_login_https.py` to use the actual baseline worker in a separate process. This optional route keeps the synthetic identity provider and isolated SQLite database. It stops the idle worker before submitting a browser job, checks that the job stays queued, confirms that the fixture's in-process processing route returns 409, then starts a new worker process. The browser waits for its result, inspects the source and saves a review. The worker receives a restricted environment without AWS/model/demo configuration.

The [separate-worker record](../reports/browser-login-separate-worker.json) contains thirteen successful groups, including the existing browser binding, signature, CSRF, replay, membership, logout and expiry checks. Its lifecycle record shows both workers stopping cleanly. The unchanged default route also passed all twelve groups; it continues to use the fixture's in-process control. Neither result is a new real Cognito login, PostgreSQL role test or hosted acceptance.

Both routes are now required by the browser CI configuration. The new remote run must pass before remote acceptance is claimed. The fixture controls remain loopback-only test infrastructure and must never be deployed with the workbench.

## Repeat the joined workflow on PostgreSQL

Use `--separate-worker --postgres-bin .runtime/postgresql/bin` with the same runner to create a fresh disposable cluster under its private run directory. The binaries must already be installed; this mode downloads nothing and accepts no existing database URL. It migrates a dedicated schema and applies the reviewed API/worker grants. A separate trusted fixture operator changes membership; the API connection never receives that credential. The worker receives only its own connection.

The [local PostgreSQL browser record](../reports/browser-login-postgres-worker.json) passed thirteen groups, including queued-job processing after worker restart, source inspection, review, signed browser sessions and membership revocation. Live database checks confirmed a nonsuperuser API without BYPASSRLS and a nonsuperuser worker with its dedicated BYPASSRLS attribute. The API could not update memberships; the worker could neither read memberships nor update reviews. These three privilege refusals are separate from the thirteen browser groups.

Browser traffic uses the fixture’s loopback HTTPS certificate; database traffic uses authenticated loopback TCP **without database TLS**. Do not copy that transport into a hosted configuration, whose runtime preflight requires verified database TLS. The cluster stops after the run; logs, credentials and database contents remain private. This optional native mode is not yet a remote CI gate, a real Cognito-to-PostgreSQL run, an API/database restart or a separate restore test. Both existing SQLite modes still passed after adding it.

## Replace the application process

Run `scripts/verify_managed_restart.py --postgres-bin .runtime/postgresql/bin` with the project Python environment and `PYTHONPATH=src`. Like the other browser runner, it accepts explicit `--node` and `--pnpm-script` paths. It creates its own private PostgreSQL cluster, starts real API/worker processes and uses a synthetic provider over loopback HTTPS. It accepts no existing database target.

After a review is saved, the API process stops and a new process takes over. The old session fails, a fresh sign-in succeeds, and the saved run and audit history match exactly. Restoring the old cookie fails again. Membership bootstrap reuses an active grant without changing its version and refuses a revoked grant. [The decision and limits](adr/058-application-process-restart.md) explain the two-second connection-drain deadline and the fourteen-group result.

This is a local process-restart check, not a PostgreSQL restart, backup restore or hosted acceptance. The controller and synthetic provider routes must never be deployed. The test is optional locally; remote CI acceptance is not claimed for this native PostgreSQL mode.

## Restart PostgreSQL or restore separately

The restart runner accepts `--storage restart` and `--storage restore`. Both stop the API and worker before changing storage, then reopen the workbench and require a fresh sign-in.

- `restart` replaces the database process on the same storage and checks every application table before reconnecting.
- `restore` writes a trusted private archive, rejects a truncated copy and restores into a separate fresh cluster with new runtime credentials. The source files remain intact. It checks all application table digests and restricted roles before reconnecting.

Both modes passed fifteen browser groups locally. [ADR 059](adr/059-local-database-recovery.md) records the missing pgvector dependency found on the first attempt, the successful correction and the precise scope. The archive, raw database contents and credentials stay under the private run directory. Database traffic is still loopback without TLS, and these optional native checks are not hosted or remote CI recovery acceptance.
