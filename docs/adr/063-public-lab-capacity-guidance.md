# A useful route when the public lab is busy

October 28, 2026.

During the employer-facing review, overlapping live checks reached the public lab's capacity/activity notice. The browser could not proceed to the findings. A subsequent serial run completed the review, reload and logout workflow. Both observations remain in the private review evidence; the successful run does not erase the refusal.

Keep the existing admission limits. The frontend now reads the server's delta-seconds Retry-After header for 429/503 responses, accepts bounded numeric values up to one hour, and disables the analysis retry until that delay has elapsed. There is no automatic retry or polling. Missing or invalid headers produce manual retry guidance without an invented wait time. The countdown is a convenience for this page, not a reservation or a bypass of server enforcement; reloading does not create extra server capacity.

The busy panel offers a saved worked example and a link to recorded evaluation results. The example is an authored, fictional, read-only walkthrough using exact excerpts from the municipal RFP and capability register. It does not claim to be a fresh model response, execute an analysis, change the current run or save a review. It uses the existing keyboard-trapped dialog and returns focus to its opener. Existing session state remains governed by expiry and the server's limits.

The browser acceptance fills all four actual server session slots using independent clients, observes the real 503 with a 60-second delay, opens the example at desktop and phone widths without extra API calls, releases one slot, advances only the browser clock and explicitly retries. The real server then accepts a session and analysis. A separate controlled 429 checks a ten-minute delay; the existing missing-header control exercises immediate manual recovery. Source inspection, saved review, stale conflict, session expiry and recorded-results tests remain in the same suite.

These checks do not establish live-host concurrency capacity, cold-start reliability, exhaustive accessibility compliance or participant understanding. The public host is unchanged until a specifically approved deployment. No model cohort, backend admission rule or analysis recipe changed.
