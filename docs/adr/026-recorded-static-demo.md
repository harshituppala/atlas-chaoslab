# ADR 026: a separate static recorded evidence room

Date: 2026-10-18. Status: implemented and locally verified; publication/deployment pending.

## Requirement and decision

The confirmed hosting constraint is free only. The full API needs durable storage, scoped identity, workers and secrets; putting its local bearer credentials on a public host would violate the access boundary. Provide a separate read-only React entry, built into apps/web/dist-replay, for inspecting synthetic recordings without an API. Keep the interactive workbench and its acceptance gates separate. This is an interim portfolio demonstration, not evidence that the full stack has been deployed.

The evidence room includes the municipal baseline freshly executed during export and the historical single-case Bedrock browser/worker result. Both remain pending human review. Its own source viewer, search/filter controls, extractive drafts, evaluation failures and provenance view run entirely in browser memory. No authentication, uploads, review writes or new inference are implemented in this entry.

## Export and privacy boundary

atlas.replay projects explicit document/domain fields. It reuses the worker's exact source/citation/draft/pending-review invariants. The historical artifact must match the saved validation report's SHA-256 and provider/pipeline/settings identity, and its original input sentences must match the specific synthetic residency fixture. Jobs, actor identities, arbitrary traces/prompts, tokens, stored run IDs and review notes are not copied. This is a narrow fixture exporter, not a general workspace-redaction facility. The approved synthetic text and source document IDs are deliberately public within this proposed artifact; do not repoint it at client data.

Public recordings are bundled as committed JSON, so a clean clone builds the replay without private artifacts, AWS access or model expenditure. Regenerating the historical projection needs the original private recording; it is deliberately absent from a source-only release. Report hashes identify inputs, not signed authenticity or independent model accuracy. The browser displays the historical provider scope and estimated cost as historical, not current execution.

## Browser and hosting boundary

A build-time HTML content policy allows only local scripts/styles/images and sets connect-src none, form-action none and base-uri none. The build uses relative asset paths and no fonts, analytics, CDNs or outbound links. The existing native dialog provides focus containment/Escape/return focus; displayed offsets count Unicode characters. This is targeted Chromium evidence, not a full accessibility audit. The browser does not independently recompute the citation digests; export validation is the integrity gate.

The content policy is a defense against accidental requests, not a confidentiality boundary for bundled public data or compromised host scripts. A future host must validate HTTPS, security/cache headers, frame-ancestors protection (unavailable through this meta policy), path/asset behavior and the exact deployed bytes. Free hosting availability, terms and account permissions are not established by a local build. Publishing this artifact still requires the separate publication decision; this is not a workaround for the rejected GitHub push or permission to expose the API.

## Executed verification

Ten new projection/tamper tests pass; the full native suite passes 326 tests with 18 opt-in PostgreSQL skips. Three actual Chromium tests pass against the production static artifact, covering recording selection, exact source highlights, search empty states, known failures, dialog keyboard/focus behavior, 390px layouts and a desktop screenshot. Requests were local GET assets only, browser storage/cookies remained empty, and an intentional API fetch was rejected by the content policy. The normal workbench and separate replay builds pass, as do Python and frontend formatting checks. A previously occupied port was left alone; the disposable browser server used loopback port 8127 and exited after testing.

reports/replay-validation.json records actual test-report hashes and post-execution source/build hashes with that limited attestation scope. reports/replay.png is the inspected desktop result. Remote CI is configured to build/test the replay but has not executed. No new model calls or hosting resources were used for this work.
