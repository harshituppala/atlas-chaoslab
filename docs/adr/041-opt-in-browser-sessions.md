# ADR 041: keep browser credentials on the server

Date: October 21, 2026. Status: explicit factory opt-in implemented; controlled HTTP checks passed. Workbench UI and real provider/browser acceptance remain unfinished.

Attach the authorization-code exchange to HTTP routes only when an operator supplies `login_exchange` to `create_app`. Default launchers and the fictional public lab do not enable these routes. Successful callbacks create an opaque, server-side session instead of returning provider tokens to browser JavaScript. Pending attempts and sessions remain process-local.

The temporary login-binding cookie uses Secure, HttpOnly and SameSite=Lax because the provider returns through a cross-site top-level navigation. The application-session cookie uses Secure, HttpOnly and SameSite=Strict. Both use the host-only cookie prefix and root path. Callback redirects remove code/state parameters from the destination URL; errors use fixed destinations without provider details. Cookies contain random handles, and the session registry keeps their hashes.

Session requests must match the configured HTTPS host. Writes require the exact Origin and a synchronizer token supplied in `X-Atlas-CSRF`; cross-site requests and mixed bearer/cookie credentials are rejected. Session metadata exposes only the CSRF token and expiry, so users can still log out after their workspace membership is revoked. Actual API requests reverify the access JWT and resolve current membership. Provider claims and session state cannot grant a workspace role.

Sessions expire at the earlier provider/token lifetime, capped at fifteen minutes, with both wall and monotonic checks. Reauthentication rotates the handle and invalidates the old one. Logout deletes server state and cookies. Capacity refusal preserves existing sessions; closing the service clears its local state. This is application logout, not provider logout or revocation of every copy of an access token.

The recorded verification passed 67 focused checks and 563 native tests, with eighteen optional PostgreSQL groups skipped. Tests exercise job admission, viewer denial, immediate membership revocation, CSRF refusal, duplicate cookies, rotation, capacity, expiry, logout and provider errors. The previous cache-policy assertion was updated because responses now vary on Cookie as well as Authorization. Tests use an in-process ASGI client with HTTPS request URLs: they perform no TLS handshake and do not enforce a real browser's SameSite behavior. See the [offline report](../../reports/browser-sessions-offline.json).

The private workbench still needs controls for starting sign-in, reading session state, attaching CSRF headers and clearing displayed data on expiry. Real provider registration, browser navigation, proxy log redaction, rate limiting and deployed acceptance remain unverified. No AWS pool/client, hosted authentication or durable session backend was created. ATLAS analysis semantics and pipeline versions are unchanged.
