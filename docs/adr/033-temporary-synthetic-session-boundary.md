# 033 — A separate temporary synthetic API

Date: October 19, 2026
Status: implemented and checked locally; not a deployed or browser-integrated application

## Requirement

A future free public lab must demonstrate real analysis and review without exposing the private/local-token API or implying durable customer storage. Anonymous users must not submit real documents, trigger models, change somebody else's review or grow retained state without bounds. This is a distinct product profile from the full durable review service.

## Decision

Add a separate FastAPI factory and loopback launcher. The factory does not mount the private API. Its only analysis input is the literal municipal case ID; a pinned SHA-256 identifies the reviewed synthetic seed. Uploads, custom documents, model mode and free-text notes have no accepted schema. Inherited private database/principal/managed-auth/model configuration refuses startup. The baseline child is still real: its output passes the existing source/citation/pending-review publication gate before saving. Prompts, goldens and AI pipeline versions are unchanged.

An opaque random cookie selects a process-local session. Only its digest is kept in the registry. Each session has its own in-memory SQLite database, allowing the existing transactional review/version checks to be reused without accepting tenant or run IDs from the caller. HTTPS configuration uses an HttpOnly/Secure/SameSite=Strict __Host cookie with path /. The loopback HTTP launcher uses a separately named non-Secure local cookie. These flags have been inspected in ASGI tests, not validated in a browser or live TLS session.

Mutation requests require an exact configured Origin. Cross-site Fetch Metadata is refused, a host allowlist applies, and no CORS permission is emitted. These are browser request boundaries, not identity verification: non-browser clients can participate in this anonymous synthetic exercise. All responses are no-store and vary on Cookie/Origin. Schema errors and child failures have fixed text.

Defaults are four sessions, absolute ten-minute expiry, four admitted write bodies of at most 4096 bytes, one concurrent analysis child, two attempted analyses per session, eight attempted starts per process per ten-minute window, and sixteen successful review writes per session. Repeat analysis returns the existing result; repeat session creation with a valid cookie does not extend expiry or allocate another store. Review notes are server-owned choices. Failed attempts consume their start budget. Monotonic time controls expiry and windows.

A periodic task sweeps idle expired sessions; request release also sweeps. An active expired store continues to occupy capacity until its operation releases it, then is disposed. Output cannot be published after expiry is observed. Shutdown closes idle stores and marks active stores for release cleanup. Expiry does not retract response bytes already issued.

The lab deliberately uses one bounded synchronous analysis request rather than the durable job queue. All sessions, reviews and budgets reset on process restart. This cannot be presented as the full private service, durable workflow or managed identity implementation. It also does not replace the optional local API-owned worker profile from ADR 031.

## Executed evidence

Twenty-three new tests passed. They include a real baseline child with eight provisional requirements; successful explicit review plus stale-version/conflicting-evidence rejection; separate session state; logout and restart reset; missing/cross-origin refusal; no private routes/uploads/model inputs/free-text notes; body/host limits; active-expiry capacity retention and no publication; failure-budget release; process start budget across session churn; cached analysis; review limits; worker self-approval rejection; private configuration refusal; idempotent session creation; actual periodic sweep; origin validation and seed pin refusal.

The full native suite passed 444 tests with 18 optional PostgreSQL skips. Ruff and 133 Python formatting checks passed. The independent recorder ran the final ASGI app with a real bounded child and two cookie contexts: eight requirements/fourteen publication-validated citations, all initially pending; cached repeat analysis; human review and stale conflict; another session's empty result; private-route absence; simulated expiry and store removal. reports/synthetic-lab-boundary.json binds actual source/test/JUnit identities. The recorder uses a simulated HTTPS origin and injected expiry clock, not a socket, browser, TLS or hosted provider. A post-test lint-only assignment correction preserves the origin-port check; final source was separately exercised by the recorder.

## Remaining gates and limits

The existing workbench is not wired to this API yet. Provider boot/storage/headers, actual browser cookies/CSRF/navigation, cold starts, deployed restart behavior and usage settings remain unverified.

Capacity and start counters are per process and reset on restart; replicas multiply them. They do not cap invoices, total RSS, network/proxy/header buffers or all request CPU. Anonymous users can occupy all capacity and deny others service; there is no fair per-user rate limit. SQLite/child/publication allocations add memory beyond body budgets. Children retain host privileges and process-group/host-failure limits from ADR 029. Cookie possession confers access to a temporary fictional exercise, not a verified human identity. No production security, durability or availability claim follows.
