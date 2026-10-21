# Workbench sign-in and loss of access

The private workbench previously accepted a pasted bearer token even when the API had an optional cookie session. The interface now asks the server which profile is enabled before showing either connection flow. An absent `/auth/config` keeps the local token screen; network errors and invalid configuration show a retry screen instead.

In the optional profile, a normal POST form starts sign-in. The page reads only CSRF metadata and expiry from `/auth/session`. It never receives a provider access token. API requests use same-origin cookies, omit Authorization and carry the CSRF header. An operator still supplies the configured exchange explicitly; default launchers and the fictional public lab do not enable managed login.

Expiry, a rejected API identity or a sign-out action unmounts the workbench. This removes displayed sources, notes, history and review state, and aborts that component's outstanding requests. An old response cannot reopen the workspace. This is a UI boundary, not a guarantee that an already accepted server job was cancelled or that JavaScript memory was securely erased.

A failed logout must remain visible as a failure. The page hides the workspace immediately, retains the CSRF metadata needed to retry, and does not say the server session ended until it receives 204. Local logout does not end the identity-provider session. For safety, any session-authenticated 403 hides the workspace, including a role or workspace-selection refusal; a user can check sign-in again and select a permitted workspace.

The existing HTML policy allowed forms only to the application's origin. The enabled profile now also permits its one configured HTTPS provider origin. Script and connection policies stay restricted to self. The policy builder rejects wildcards, HTTP origins and directive separators. This allowance is needed for the navigation flow; real redirect-chain behavior remains part of provider acceptance.

## Evidence

`python scripts/verify_browser_login_ui.py` builds the interface and runs seven Chromium cases against a loopback server. They cover CSRF/bearer separation, local-profile fallback, configuration failure, membership refusal, expiry with a delayed request, logout failure/retry and a direct configured form-target probe. The report fingerprints source, tests, compiled assets and the raw browser result. A bundled Node/pnpm installation can be passed with the runner's documented flags.

The provider and API responses are intercepted fixtures. The form-target probe submits directly to an intercepted destination; it does not follow a real authorization redirect. An initial attempt to intercept a fulfilled 303's next request reached DNS instead of the second handler. That approach was discarded rather than reported as provider acceptance. No real provider token or cookie is involved in these browser cases.

The native suite separately checks signed tokens, configured middleware, cookie flags, Origin/CSRF and membership changes. Neither set of checks proves the whole system works through a real identity provider, TLS and a deployed proxy. Those checks, durable hosting and distributed session/rate controls remain unfinished.
