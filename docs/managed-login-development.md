# Managed login development

The private API has an optional authorization-code and browser-session path. It is enabled only when an operator passes a configured `LoginExchange` into `create_app(..., login_exchange=exchange)`. Default launchers and the public fictional lab keep their existing profiles. The workbench has controlled interface checks and a joined local HTTPS check with a synthetic provider; real AWS/provider acceptance remains unfinished.

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

Copy `deployment/login-settings.example.json` to a private file under `var/`, replace every placeholder with the reviewed provider settings, and restrict it to mode 600. No AWS access key or client secret belongs in this file. The issuer and its key URL must refer to the same pool; the public client, API scope, resource audience and callback must match the reviewed console configuration.

The explicit factory requires both settings and a database. For an existing TLS termination setup:

```sh
ATLAS_LOGIN_SETTINGS="$PWD/var/login-settings.json" \
ATLAS_DATABASE_URL="sqlite:///$PWD/var/managed-atlas.db" \
PYTHONPATH=src .runtime/bin/python -m uvicorn atlas.managed:create_from_environment \
  --factory --host 127.0.0.1 --port 8000 --no-access-log
```

This binds a private upstream only. It does not install TLS or make an HTTPS callback reachable. The browser must use the exact approved HTTPS origin through a separately configured TLS endpoint. Do not expose this upstream directly or rewrite the callback to bypass origin checks. Keep callback query strings out of proxy logs too.

Unset `ATLAS_DEMO`, `ATLAS_PRINCIPALS`, `ATLAS_TOKEN_TRUST` and `ATLAS_MODEL_JOB_SPEC` before using this profile; their presence is rejected. The entry point opens no provider connection during construction and assigns no membership. Use the separate trusted membership operator after verifying the user's real subject; never copy a role from provider claims. Model jobs remain disabled in this profile. Run a baseline worker against the same database when testing queued work.

The joined synthetic browser check now exercises this factory and settings reader. Its transport overrides remain confined to the fixture. The real Cognito directory/client/domain and scope are configured, but real user sign-in is still pending. See [ADR 045](adr/045-managed-application-entry.md).

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

Register one reviewed HTTPS callback and confirm that the provider domain belongs to the intended pool. Configure a public client for authorization code with S256, the API scopes and resource audience expected by the verifier. Membership must be assigned by the application operator, not inferred from groups or roles in provider claims.

Keep callback query strings, cookies and tokens out of server/proxy logs and traces. Configure TLS, trusted proxy handling and request-rate controls. Real browser acceptance must check the external redirect, Lax binding cookie, Strict application cookie, callback replay, provider denial/outage, membership revocation, logout and expiry. Review account access and cost before creating cloud resources; the owner must complete real sign-in without sharing credentials in chat.

[Session decision](adr/041-opt-in-browser-sessions.md) · [Exchange component](adr/040-authorization-code-exchange.md) · [Token profile](adr/025-explicit-cognito-access-profile.md)
