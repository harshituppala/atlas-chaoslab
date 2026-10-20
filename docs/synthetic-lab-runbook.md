# Temporary synthetic API — local preparation

This separate profile allows only the seeded fictional municipal RFP. It performs real baseline analysis and bounded review practice. It accepts no real uploads, model settings or free-text notes. All history disappears after expiry or restart. A dedicated React workbench now connects to this boundary on one local origin. It is separate from the private workbench and has not been hosted.

Build and start the local interface, with private ATLAS service settings unset:

```sh
cd apps/web
pnpm build:lab
cd ../..
PYTHONPATH=src .runtime/bin/python -m atlas.synthetic_lab \
  --port 8133 --web-root apps/web/dist-lab
```

Open http://127.0.0.1:8133. Omitting --web-root starts the API-only profile. The launcher binds 127.0.0.1 and uses http://127.0.0.1:8133 as its exact allowed origin. Do not expose the private API or forward this local listener publicly. Future hosted factory configuration requires an explicit HTTPS origin and separate provider/browser validation.

In another terminal, these requests keep the temporary cookie inside ignored var:

```sh
umask 077
mkdir -p var
curl -s --cookie-jar var/lab-cookies.txt \
  -H 'Origin: http://127.0.0.1:8133' -H 'Content-Type: application/json' \
  -d '{}' http://127.0.0.1:8133/api/lab/session
curl -s --cookie var/lab-cookies.txt \
  -H 'Origin: http://127.0.0.1:8133' -H 'Content-Type: application/json' \
  -d '{"case_id":"municipal"}' http://127.0.0.1:8133/api/lab/run
```

Do not share cookie jars. Session creation returns only lifetime/reset metadata; cookie possession selects the temporary exercise. Repeat creation with a valid cookie reuses its remaining absolute lifetime. GET /api/lab/session reads the remaining lifetime without renewal. GET /api/lab/run returns only that session's result. DELETE /api/lab/session requires the same Origin and drops the session. Session state is not a user account.

POST /api/lab/reviews/{requirement_id} accepts version, decision (approved/rejected), and note_code (excerpt_checked/needs_followup). It reuses the existing review compare-and-swap rule. Unknown requirements return 404; stale versions or approval of missing/conflicting evidence return 409. No submitted note text is stored.

Default budgets are four live sessions, ten minutes absolute lifetime, one concurrent child, two attempts/session, eight starts/process/ten minutes and sixteen successful review writes/session. The child computation deadline is five seconds; storage/publication and host scheduling add time. Four concurrent write bodies of at most 4096 bytes are admitted. Capacity exhaustion is 503, budget exhaustion 429, a busy session 409, and missing/expired credentials 401. Retry hints are conservative, not a precise availability schedule. A periodic sweep removes expired idle stores; active expiry retains its slot until release and blocks publication. All budgets reset on restart and are not an account spending cap.

## Repeat local verification

```sh
mkdir -p var
PYTHONPATH=src .runtime/bin/python -m pytest -q \
  --basetemp=var/synthetic-lab-full \
  --junitxml=var/synthetic-lab-tests.xml
PYTHONPATH=src .runtime/bin/python scripts/verify_synthetic_lab.py
```

The report records actual ASGI requests and a real baseline child. HTTPS origin, cookie attributes and expiry are checked with TestClient and a controlled clock. These are not real browser/TLS, socket load, provider persistence or cloud deployment checks. Tests also exercise the real periodic sweep, restart reset, resource refusal and cross-session boundaries. The report excludes cookie values, session identifiers and review/source payloads.

No existing local database, credentials file or model budget is used. The seed is pinned; changing it requires an explicit reviewed update, not a caller-selected path. The local interface restores a live session after reload, refreshes stale reviews without resubmitting them, and clears its display on reported expiry. Ending a session does not instantly erase already-rendered fictional data in other tabs. Hosted HTTPS, provider limits and exact source publication still need their own completion and approval. See ADR 033 for failure semantics and limitations.


## Repeat the real browser flows

With the production lab build present and Chromium available:

```sh
pnpm --dir apps/web test:lab
PYTHONPATH=src .runtime/bin/python scripts/record_lab_browser.py
```

This starts a test-owned server on 127.0.0.1:8134 and stops it afterward; it will not reuse an unrelated listener. On this machine set PLAYWRIGHT_BROWSERS_PATH to the repository's .cache/playwright when using the existing browser installation. Private browser JSON is written under var; the recorder projects only the three authored passing case names and hashes. Source/build hashes are post-execution identities, not signed loaded-code evidence. Desktop/mobile captures are synthetic.

The capacity response and one-second client lifetime are controlled faults. Other analysis/review requests reach the actual baseline backend. The lifetime test explicitly confirms that the real server session is still valid; actual server TTL has native controlled-clock evidence, not ten minutes of browser waiting. The loopback HTTP cookie is HttpOnly/SameSite=Strict and intentionally non-Secure. Hosted TLS/Secure-cookie behavior is unverified. ADR 034 records these limits and the corrected initial test assumptions.
