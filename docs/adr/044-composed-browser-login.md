# Test login through the browser and server together

The first joined browser run stopped at `/auth/start`: Chromium sent `Origin: null`, and ATLAS rejected it. The isolated HTTP tests had supplied an Origin manually, while the UI tests intercepted the sign-in responses. Both missed the interaction between a navigation POST and the document's `no-referrer` policy.

For the explicitly enabled login profile, HTML now uses `Referrer-Policy: same-origin`. This preserves the same-origin form proof without sending the page's URL to the external provider. Callback and API responses retain `no-referrer`, and the server still rejects missing, opaque and foreign Origins. After the first correction, another sign-in failed following a cached reload. The index's 304 path could restore the default policy because it lacked an HTML Content-Type. Optional login documents now use no-store, and index revalidation carries the same policy as the original document.

## What the joined check runs

`verify_browser_login_https.py` builds the workbench and starts ATLAS with a synthetic provider. Chromium follows real redirects over loopback TLS. The provider checks S256, issues a one-use code and returns a signed access token; the existing backend fetches JWKS and verifies that token over TLS. A real database membership grants the fictional reviewer access. The baseline worker processes a queued demonstration, and the browser inspects its source and saves a review.

The runner also checks cross-site cookie withholding, a consumed callback replay with a captured binding cookie, missing-CSRF refusal, membership revocation, logout with a captured session cookie, another sign-in, controlled server expiry and provider denial. The [report](../../reports/browser-login-https.json) records twelve passing groups, two completed exchanges and one JWKS fetch. It fingerprints runtime source, the fixture, browser assertions, dependencies, compiled assets and CI configuration. Raw diagnostics and the fictional screenshot stay under `var/browser-login-https/`.

The test needs no privileged port. A loopback CONNECT proxy maps only the two fixture origins to one local TLS listener and rejects other destinations. The certificate is generated for the run; Chromium gets a subprocess-only exception pinned to that certificate's public key. Backend clients verify the fixture certificate and hostnames. The operating system trust store is unchanged. Browser profiles, temporary files and XDG cache/config paths are directed into the portfolio folder. A Chromium command-line check verifies the actual profile path instead of relying only on environment settings. Access logs are disabled, diagnostic URLs omit queries, and the generated TLS private key is removed during teardown.

## Limits

This is a passwordless synthetic identity fixture, not AWS, Cognito or a real user login. Its provider control routes are deliberately test-only and must never be deployed. The expiry case advances the server's monotonic clock; it does not wait for a real provider session to expire. Local SQLite and a test certificate do not establish durable hosting, public certificate trust, production proxy behavior or distributed sessions.

The native suite passed 617 tests, with eighteen optional PostgreSQL groups skipped. The original eleven-group composed check passed in [Linux CI](https://github.com/harshituppala/atlas-chaoslab/actions/runs/39683853703). A follow-up adds the twelfth group for temporary-profile containment and refreshes the local report; its new remote result must be observed separately. Default launchers and the hosted fictional lab keep their existing profiles. No model calls, cloud resources or hosted deployment were made.


## Browser-cache correction

The temporary-folder follow-up failed in CI before completing browser acceptance. A local run without the previously supplied browser-cache override reproduced a missing Chromium executable. Installation and execution had not agreed on a cache location; the local override had hidden that dependency.

The runner now defaults to the repository's `.cache/playwright`, and the CI browser job uses that path for both installation and execution. A local run without the override passed all twelve groups. Setup errors identify a missing browser without printing private diagnostics. The failed CI run remains visible; the corrected remote result must be checked separately. Application authentication behavior is unchanged by this harness correction.
