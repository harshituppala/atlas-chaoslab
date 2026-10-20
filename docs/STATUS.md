# Project status

Updated October 20, 2026. ATLAS and CHAOSLAB work locally, and their [source release](https://github.com/harshituppala/atlas-chaoslab) is public. The [fictional ATLAS review lab](https://atlas-review-lab.onrender.com) is live on free hosting; the full managed review service remains local.

## ATLAS

The review workbench accepts text-bearing PDF/DOCX files and pasted sources, extracts requirements, retrieves capability evidence and links excerpts to their originals. Review decisions use version checks and an audit trail. The API and worker use a database-backed queue with expiring leases and transactional result publication.

The default analysis is an offline extractive baseline. The optional Bedrock path selects evidence from server-owned choices and leaves every assessment pending for human review. Paid jobs require explicit operator configuration and have one queue attempt; a timeout can leave usage uncertain.

SQLite supports the local demonstration. PostgreSQL has separately tested migrations, restricted API/worker roles, tenant row policies and persistent exact pgvector retrieval. Managed-token validation is implemented, but browser sign-in with a real identity provider remains unfinished.

A separate synthetic lab runs the seeded review workflow with temporary sessions. It accepts no uploads or model credentials. Desktop and mobile browser checks cover source inspection, review conflicts and session handling. A dedicated Linux image has also been exercised under a memory limit, with an intentional session reset on restart. Real hosted HTTPS, Chromium and controlled restart checks now pass. Session history is intentionally temporary; cold-start and usage-limit behavior still need further observation. See the [lab runbook](synthetic-lab-runbook.md) and [container checks](lab-container-runbook.md).

## CHAOSLAB

The independent evaluator scores adapter output against synthetic golden cases. It checks extraction, evidence relations, source spans, review state and failure behavior separately. Paired comparisons rescore raw runs under the same dataset and scorer, preserving missing cases and regressions.

A separate `chaoslab-eval` wheel now supports saved-run comparisons without installing ATLAS. A clean-environment check exercised unchanged, corrupt-citation and missing-attempt outcomes, plus an external trusted adapter. See the [installation guide](../src/chaoslab/README.md#install-the-evaluator-on-its-own) and [package decision](adr/037-portable-chaoslab-evaluator.md). Remote CI for this package check is pending.

The datasets are development fixtures written for these projects. They are useful for finding regressions, but do not establish accuracy on customer contracts or constitute an external evaluation.

## Verification

These results come from separate runs. Each report records its own inputs and execution scope.

| Check | Result | Evidence |
| --- | --- | --- |
| Latest native Python suite | 462 passed; 18 optional PostgreSQL groups skipped | Run locally with the commands in the README. |
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

## Remaining work

- Observe free-host cold starts and usage limits; keep the temporary lab separate from a durable service.
- Complete real managed sign-in and durable hosted storage before offering the full review service.
- Extend evaluation with independently written cases, realistic document layouts and targeted tests of threshold reasoning and hostile evidence.
- Finish a practical interview walkthrough that the project owner can explain and demonstrate.

PATCHWORK is deferred. Record walkthrough videos after the projects and final checks are complete, then add them to the portfolio.
