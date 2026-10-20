# ADR 036: allow for the free host's slower CPU

Date: October 20, 2026. Status: implemented; hosted HTTP, browser and controlled restart checks passed.

The first Render deployment built and started successfully on a free instance. HTTPS, the session cookie and static assets were reachable, but the seeded analysis returned a fixed 503. A second request failed after 5.18 seconds, matching the configured five-second child deadline. The free instance advertises 0.1 CPU and 512 MB; the earlier local image check used one CPU. A successful local run did not predict the hosted execution time.

Keep the ordinary local lab deadline at five seconds and give the container entry twenty seconds. The factory accepts only an integer from one to thirty seconds. Request data cannot change it. One computation slot, session expiry, two starts per session, eight process starts per ten-minute window and the existing byte limits remain in force. The larger wall budget allows slower startup; it does not change extraction, retrieval or citation semantics.

Timeouts and other execution failures now emit different fixed log messages. Neither includes documents, cookies, exception details or model output. The client still receives the same fixed failure response. A timeout releases the computation slot so the next permitted attempt can run; it does not automatically retry.

Seven new cases check invalid deadlines, the configured execution budget, slot recovery and exclusion of a private error canary from responses and logs. The native suite passes 460 tests with eighteen optional PostgreSQL groups skipped. The first remote browser job stopped on formatting in the new configuration, before browser execution; that formatting is corrected and the complete frontend formatting check passes locally. The failed CI run remains visible.

The hosted HTTP verifier checks the fictional baseline, exact source spans, secure cookies, review conflicts, isolation, origin/body refusal and absence of the private upload API. A successful provider deployment or health response alone is insufficient. Hosted analysis, browser use and restart behavior must pass before the portfolio presents the lab as a working demo. No cloud durability, general model accuracy or production SLA follows from this demonstration.

The corrected source passed both remote CI jobs: 460 backend tests, ten private-workbench browser tests, three static-viewer tests and three synthetic-lab browser tests. Hosted HTTPS returned eight requirements with fourteen independently checked source spans. A real Chromium workflow verified source inspection, human review, reload, secure cookies, logout and desktop/mobile layout. An operator-triggered restart rejected the old session before its original expiry and allowed a fresh successful analysis. Cold-start, ten-minute expiry, load and billing behavior are not established by these checks.

The first hosted browser harness waited for network idle and timed out; the corrected harness waited for document readiness and then asserted the actual workflow. No application success is inferred from that failed navigation attempt.
