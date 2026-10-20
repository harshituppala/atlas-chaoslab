# 034 — Connect a dedicated synthetic browser workbench

Date: October 19, 2026
Status: implemented and exercised on loopback HTTP; not hosted

## Requirement

The temporary synthetic API from ADR 033 needed a usable review interface. The private workbench expects bearer credentials, uploads and durable jobs, so pointing it at the lab would confuse both the access boundary and product promises. The synthetic exercise needs its own entry while reusing source-dialog behavior and existing review semantics.

## Decision

Add a dedicated React/TypeScript entry and Vite build under dist-lab. It offers only the fictional sample, exact citation inspection, local search/filtering, a capability-evidence panel, server-owned review-note choices, explicit review and session ending. There are no API-address/token inputs, uploads, free-text notes or model controls. Requests are hardcoded to same-origin lab paths and use the HttpOnly cookie; browser storage holds no credentials or review history.

A read-only session metadata route returns remaining absolute lifetime without extending it or issuing a cookie. On reload the browser restores metadata and any existing result. A client timer clears the displayed workspace when that lifetime elapses; server checks remain authoritative. No retry loop recreates expired sessions. A review-version conflict loads the latest result and asks for another inspection rather than submitting a second decision automatically. Ending a session clears the current interface; other open tabs can retain already-rendered fictional data until reload, an attempted request or their local timer.

The API launcher mounts static files only when explicitly given a dist-lab directory with the lab profile marker. The private build is refused by this guard. The existing private and recorded entries remain separate. Response headers supply no-store, host/origin and browser security policies; the real browser checks served assets and APIs on one loopback origin. Artifact review is still needed before publication: the marker is an operator configuration guard, not a comprehensive file/secret scanner.

## Executed checks

Two new backend cases check non-renewing metadata and static mount refusal/headers/API separation. Full native suite: 446 passed and 18 optional PostgreSQL skips. The refreshed ASGI recorder passed with 25 boundary cases and a real baseline child. Ruff and 134 Python formatting checks pass; frontend formatting, TypeScript and the dedicated production build pass.

Three Chromium workflows passed against the actual server and production assets:

- Real baseline analysis, eight pending findings, exact Unicode source highlighting, dialog keyboard focus/return, search, explicit review and stale review conflict across two tabs sharing a session, reload restoration, cookie flags/storage inspection, same-origin lab-only requests with no Authorization header, and logout/reload clearing.
- A 390px workflow with a controlled session-capacity 503 followed by manual recovery and real analysis, recovery-time conflict evidence, the disabled approval option attribute, a follow-up review, and no horizontal overflow.
- A restored real result with lifetime metadata deliberately shortened to one second, followed by actual client-timer display clearing. The real server session is explicitly checked to remain valid; this is not a ten-minute wall-clock/server-expiry measurement.

Desktop and mobile captures were inspected. reports/synthetic-lab-browser.json projects only test names/counts and hashes from the actual passing report; a controlled failed result was refused before publication. Source/build/screenshot identities are captured after browser execution, not claimed as frozen or signed execution attestations. Separate ASGI evidence checks its own before/after source identity.

The initial TypeScript build caught a source-document variable shadowing the DOM document. It was corrected before browser execution. Initial browser checks exposed exact nested-label locator assumptions, an option-disabled matcher limitation, and unreliable late/fake clock setup. Selects now use accessible combobox roles in tests; the native disabled attribute is asserted directly; client expiry uses explicit controlled metadata. Failed run artifacts remain in ignored var. The final three-case report contains one execution per test and no retries, skips or failures.

## Limits

This is a local Chromium/HTTP exercise, not hosted HTTPS/Secure-cookie, reverse-proxy, cold-start, image or free-provider restart/usage validation. The HTTP loopback cookie is intentionally non-Secure; hosted HTTPS remains a separate gate. Native server expiry and browser display expiry have different evidence scopes. No complete accessibility audit, anonymous abuse resistance, durable storage, managed identity or production readiness is claimed.
