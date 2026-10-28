# A useful route when the public lab is busy

October 28, 2026.

During the employer-facing review, overlapping live checks reached the public lab's capacity/activity notice. The browser could not proceed to the findings. A subsequent serial run completed the review, reload and logout workflow. Both observations remain in the private review evidence; the successful run does not erase the refusal.

Keep the existing admission limits. The frontend now reads the server's delta-seconds Retry-After header for 429/503 responses, accepts bounded numeric values up to one hour, and disables the analysis retry until that delay has elapsed. There is no automatic retry or polling. Missing or invalid headers produce manual retry guidance without an invented wait time. The countdown is a convenience for this page, not a reservation or a bypass of server enforcement; reloading does not create extra server capacity.

The busy panel offers a saved worked example and a link to recorded evaluation results. The example is an authored, fictional, read-only walkthrough using exact excerpts from the municipal RFP and capability register. It does not claim to be a fresh model response, execute an analysis, change the current run or save a review. It uses the existing keyboard-trapped dialog and returns focus to its opener. Existing session state remains governed by expiry and the server's limits.

The browser acceptance fills all four actual server session slots using independent clients, observes the real 503 with a 60-second delay, opens the example at desktop and phone widths without extra API calls, releases one slot, advances only the browser clock and explicitly retries. The real server then accepts a session and analysis. A separate controlled 429 checks a ten-minute delay; the existing missing-header control exercises immediate manual recovery. Source inspection, saved review, stale conflict, session expiry and recorded-results tests remain in the same suite.

These checks do not establish live-host concurrency capacity, cold-start reliability, exhaustive accessibility compliance or participant understanding. The public host is unchanged until a specifically approved deployment. No model cohort, backend admission rule or analysis recipe changed.


## Deployment packaging correction

The approved b3cd53d deployment failed before replacing the live service: Dockerfile.lab's explicit frontend COPY list omitted SavedReviewExample.tsx. The regular browser build and managed-image job used a fuller source tree, so their success did not establish that this public image could build. The failed provider deployment is retained as dep-dbh0lhbl550s738ce3sg.

The public Dockerfile and isolated verification context now both include the named component. The existing allowlisted lab-image check builds that exact Dockerfile, runs forty-one focused Linux checks, exercises the actual HTTP review/source boundaries and verifies old-session refusal plus fresh analysis after restart. It passed locally after the correction. The managed-runtime CI job now runs this public-image check too and uploads its separate report. No additional application source, permissions, capacity or paid services are added by the correction. Hosted replacement and acceptance are still separate from this local result.


The owner-approved functionality is now live through packaging correction 39203a4 after all five CI40709733229 jobs passed. Render deployment dep-dbh0p8ks728c73chq5p0 succeeded in 42.6 seconds. [Hosted acceptance](../../reports/lab-capacity-hosted.json) checks actual four-session saturation, read-only fallback and manual recovery. The countdown uses a controlled browser clock; the server recovers by releasing an owned slot. Separate HTTPS and saved-results checks passed. The first deployment failure and the checker's premature network-idle wait remain in private evidence. Human research and recordings stay pending by owner choice.
