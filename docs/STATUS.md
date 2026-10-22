# Project status

Updated October 21, 2026. ATLAS and CHAOSLAB work locally, and their [source release](https://github.com/harshituppala/atlas-chaoslab) is public. The [fictional ATLAS review lab](https://atlas-review-lab.onrender.com) is live on free hosting; the full managed review service remains local.

## ATLAS

The review workbench accepts text-bearing PDF/DOCX files and pasted sources, extracts requirements, retrieves capability evidence and links excerpts to their originals. Review decisions use version checks and an audit trail. The API and worker use a database-backed queue with expiring leases and transactional result publication.

The default analysis is an offline extractive baseline. The optional Bedrock path selects evidence from server-owned choices and leaves every assessment pending for human review. Paid jobs require explicit operator configuration and have one queue attempt; a timeout can leave usage uncertain.

SQLite supports the local demonstration. PostgreSQL has separately tested migrations, restricted API/worker roles, tenant row policies and persistent exact pgvector retrieval. Managed-token validation and a single-use authorization-code exchange component have offline verification. Thirty-nine focused exchange cases pass, including PKCE, browser binding, replay and token checks. An explicit factory opt-in now attaches HTTP callbacks and opaque browser sessions, with Origin/CSRF checks and per-request membership verification. The workbench interface now supports that explicit profile; real provider/browser sign-in remains unfinished; see the [integration boundary](managed-login-development.md).

A separate synthetic lab runs the seeded review workflow with temporary sessions. It accepts no uploads or model credentials. Desktop and mobile browser checks cover source inspection, review conflicts and session handling. A dedicated Linux image has also been exercised under a memory limit, with an intentional session reset on restart. Real hosted HTTPS, Chromium and controlled restart checks now pass. Session history is intentionally temporary; cold-start and usage-limit behavior still need further observation. See the [lab runbook](synthetic-lab-runbook.md) and [container checks](lab-container-runbook.md).

## CHAOSLAB

The independent evaluator scores adapter output against synthetic golden cases. It checks extraction, evidence relations, source spans, review state and failure behavior separately. Paired comparisons rescore raw runs under the same dataset and scorer, preserving missing cases and regressions.

A separate `chaoslab-eval` wheel now supports saved-run comparisons without installing ATLAS. A clean-environment check exercised unchanged, corrupt-citation and missing-attempt outcomes, plus an external trusted adapter. See the [installation guide](../src/chaoslab/README.md#install-the-evaluator-on-its-own) and [package decision](adr/037-portable-chaoslab-evaluator.md). The independent package job, backend checks and browser checks passed in [GitHub CI](https://github.com/harshituppala/atlas-chaoslab/actions/runs/39515100079).

The datasets are development fixtures written for these projects. They are useful for finding regressions, but do not establish accuracy on customer contracts or constitute an external evaluation.

## Verification

These results come from separate runs. Each report records its own inputs and execution scope.

| Check | Result | Evidence |
| --- | --- | --- |
| Latest native Python suite | 641 passed; 18 optional PostgreSQL groups skipped | Run locally with the commands in the README. |
| Document-layout ingestion | Three new cases passed; original four unchanged and passing | [Layout report](../reports/ingestion-layout.json) and [scorer correction](adr/038-repeated-source-locations.md) |
| Native PostgreSQL integration | 18 groups passed | [Database report](../reports/postgres.json) |
| Retrieval on ten synthetic queries | Lexical recall@3 0.70; hybrid 1.00 | [Retrieval decision](adr/009-persistent-retrieval.md) |
| Multi-obligation comparison | Baseline 5/9; recorded model 9/9 | [Comparison runbook](comparison-runbook.md) |
| Model transfer cases | 10/12 passed | [Live validation notes](bedrock-live-validation.md) |
| Clean/hostile evidence pairs | 8/12 model cases passed; one hostile-source citation | [Failure analysis](adr/030-live-paired-injection-diagnostic.md) |
| Logical backup drill | Ten tables and 32 rows restored; pending work resumed | [Restore decision](adr/023-logical-backup-restore-drill.md) |

The extractive baseline still misses one authored requirement pattern. The model run misclassified a numeric threshold and selected a forbidden appendix. A keyword filter also excluded legitimate security-training evidence. Those failures remain in the datasets and reports.

Earlier container, browser and database results apply to the versions they tested. A new native test run does not refresh them. The [decision records](adr/) explain how the implementation and its checks developed.

The [corrected GitHub CI run](https://github.com/harshituppala/atlas-chaoslab/actions/runs/39461145031) passed 460 backend tests, ten private-workbench browser tests, three static-viewer tests and three synthetic-lab browser tests. Eighteen optional database groups were skipped. The earlier formatting failure remains visible in GitHub history.

Hosted acceptance checked eight requirements and fourteen exact source spans, human review and stale conflicts, session isolation, secure cookies and rejection of private API routes. A real Chromium run covered desktop/mobile source inspection, review, reload and logout. A provider restart rejected the old session before its expiry and allowed a fresh analysis. See [HTTP](../reports/hosted-lab.json), [browser](../reports/hosted-lab-browser.json) and [restart](../reports/hosted-lab-restart.json) reports. These checks do not establish durable storage or production reliability.

The [public portfolio](https://harshit-uppala-portfolio.vercel.app) now has separate ATLAS and CHAOSLAB source links, project guides and an ATLAS lab link. An unauthenticated Chromium check passed at desktop and mobile widths after deployment: both project dialogs opened, their links matched the published destinations, Escape dismissed them, and no horizontal overflow or browser runtime errors were observed. The latest [source CI run](https://github.com/harshituppala/atlas-chaoslab/actions/runs/39463244651) also passed.

The layout evaluation exposed a judge defect: a repeated quote on page three was compared only with its first occurrence on page one. The corrected judge searches the authored segment and keeps physical page numbers across blank pages. Source and fixture changes now prevent report publication. These checks cover synthetic text/source mapping, not rendered layout or table interpretation. See the [layout guide](layout-evaluation.md). The layout release passed [GitHub CI](https://github.com/harshituppala/atlas-chaoslab/actions/runs/39542856232).

Authored scenario contracts now reject unknown relations, duplicate source IDs and inconsistent evidence expectations before scoring. This closes a controlled false pass where an invalid expected label matched the scorer's unknown-status fallback. The separately installed comparison command rejects invalid experiments without replacing earlier reports. See [the decision](adr/039-golden-contract-validation.md). The golden-contract release passed [GitHub CI](https://github.com/harshituppala/atlas-chaoslab/actions/runs/39577292428).

The [login exchange report](../reports/login-exchange-offline.json) records controlled HTTP/RSA tests only. No AWS pool/client or enabled login routes were created. The exchange-only release passed [GitHub CI](https://github.com/harshituppala/atlas-chaoslab/actions/runs/39626877457).

The [HTTP session report](../reports/browser-sessions-offline.json) records 67 focused checks and the full native suite. It uses controlled ASGI requests, not a real browser or TLS connection. Routes remain absent from default profiles. See [ADR 041](adr/041-opt-in-browser-sessions.md); the session release passed [GitHub CI](https://github.com/harshituppala/atlas-chaoslab/actions/runs/39632885844).

The [workbench sign-in checks](../reports/browser-login-ui.json) passed seven controlled Chromium cases. Six existing bearer-workbench browser regressions also passed locally. The interface hides workspace data on expiry/denial/logout, aborts pending requests and reports failed logout without claiming success. The native suite separately covers the server configuration and pinned form policy. [ADR 042](adr/042-workbench-session-interface.md) records the boundaries: intercepted responses and direct form-target probes do not establish a real external login. No identity-provider resources or paid calls were made; hosted applications are unchanged. The interface release passed all three jobs in [GitHub CI](https://github.com/harshituppala/atlas-chaoslab/actions/runs/39666498219).

Saved-observation admission now rejects malformed bundles and nested containers before scoring. The comparison CLI returns 2 and preserves earlier evidence, while wrong-but-usable answers remain scored failures. Fresh malformed adapter output is recorded as an attempted failure. The separately installed evaluator passed eight controlled checks without ATLAS installed; the extractive scenario baseline remains five of nine obligations and zero of three complete scenarios. See [ADR 043](adr/043-saved-observation-admission.md) and [the refreshed package report](../reports/chaoslab-package.json). No dataset expectations or historical model results changed. The admission release passed [GitHub CI](https://github.com/harshituppala/atlas-chaoslab/actions/runs/39682008435).

The [joined browser login check](../reports/browser-login-https.json) passed twelve groups through real loopback TLS and a synthetic identity provider. It exercises redirects, S256, signed-token/JWKS verification, browser cookies, a queued baseline review, revoked membership, logout, replay, controlled expiry and denial. It exposed a Chromium form-Origin/privacy-policy mismatch and a repeated-sign-in caching problem; [ADR 044](adr/044-composed-browser-login.md) records the correction. No real AWS user, public certificate or deployed identity flow was validated. The first joined-login release passed all three [Linux CI jobs](https://github.com/harshituppala/atlas-chaoslab/actions/runs/39683853703). A follow-up now verifies that Chromium's temporary profile stays inside the portfolio folder; its twelve-group local run passed. The follow-up [CI run](https://github.com/harshituppala/atlas-chaoslab/actions/runs/39708459631) then failed in the composed runner. A local no-override reproduction found a missing Chromium executable. The installer and runner now share the explicit workspace browser cache, and all twelve groups pass locally without the earlier override. The corrected [remote run](https://github.com/harshituppala/atlas-chaoslab/actions/runs/39709057021) passed all three jobs.

The managed application now has an explicit operator factory with a private settings file and database selection. It rejects inherited demo/bearer/model profiles and owns its authentication clients through shutdown. Twenty-four focused cases passed; the joined synthetic Chromium/TLS check now uses this factory and again passed all twelve groups. The approved real Cognito directory, public client, domain, API scope and authorization-code callback settings have been created and saved. Real user sign-in, an authenticated external callback and hosted service acceptance remain untested. See [ADR 045](adr/045-managed-application-entry.md) and the [operator entry point](managed-login-development.md#configure-an-operator-run-application).

The operator-entry release passed backend and standalone-evaluator CI, but its final joined-browser step failed during a second frontend build. The build error had omitted the underlying output. The runner now reports the exit code and CI retains only its frontend build log for three days; no session logs, provider responses or certificates are uploaded. A fresh local joined run still passes twelve groups. The failed [remote run](https://github.com/harshituppala/atlas-chaoslab/actions/runs/39710460942) remains visible; diagnosis is in progress.

## Remaining work

- Observe free-host cold starts and usage limits; keep the temporary lab separate from a durable service.
- Complete real managed sign-in and durable hosted storage before offering the full review service.
- Extend evaluation with independently written cases, realistic document layouts and targeted tests of threshold reasoning and hostile evidence.
- Finish a practical interview walkthrough that the project owner can explain and demonstrate.

PATCHWORK is deferred. Record walkthrough videos after the projects and final checks are complete, then add them to the portfolio.
