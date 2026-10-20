# Project status

Updated October 20, 2026. ATLAS and CHAOSLAB work locally. Neither has a hosted application URL yet.

## ATLAS

The review workbench accepts text-bearing PDF/DOCX files and pasted sources, extracts requirements, retrieves capability evidence and links excerpts to their originals. Review decisions use version checks and an audit trail. The API and worker use a database-backed queue with expiring leases and transactional result publication.

The default analysis is an offline extractive baseline. The optional Bedrock path selects evidence from server-owned choices and leaves every assessment pending for human review. Paid jobs require explicit operator configuration and have one queue attempt; a timeout can leave usage uncertain.

SQLite supports the local demonstration. PostgreSQL has separately tested migrations, restricted API/worker roles, tenant row policies and persistent exact pgvector retrieval. Managed-token validation is implemented, but browser sign-in with a real identity provider remains unfinished.

## CHAOSLAB

The independent evaluator scores adapter output against synthetic golden cases. It checks extraction, evidence relations, source spans, review state and failure behavior separately. Paired comparisons rescore raw runs under the same dataset and scorer, preserving missing cases and regressions.

The datasets are development fixtures written for these projects. They are useful for finding regressions, but do not establish accuracy on customer contracts or constitute an external evaluation.

## Verification

These results come from separate runs. Each report records its own inputs and execution scope.

| Check | Result | Evidence |
| --- | --- | --- |
| Latest native Python suite | 393 passed; 18 optional PostgreSQL groups skipped | Run locally with the commands in the README. |
| Native PostgreSQL integration | 18 groups passed | [Database report](../reports/postgres.json) |
| Retrieval on ten synthetic queries | Lexical recall@3 0.70; hybrid 1.00 | [Retrieval decision](adr/009-persistent-retrieval.md) |
| Multi-obligation comparison | Baseline 5/9; recorded model 9/9 | [Comparison runbook](comparison-runbook.md) |
| Model transfer cases | 10/12 passed | [Live validation notes](bedrock-live-validation.md) |
| Clean/hostile evidence pairs | 8/12 model cases passed; one hostile-source citation | [Failure analysis](adr/030-live-paired-injection-diagnostic.md) |
| Logical backup drill | Ten tables and 32 rows restored; pending work resumed | [Restore decision](adr/023-logical-backup-restore-drill.md) |

The extractive baseline still misses one authored requirement pattern. The model run misclassified a numeric threshold and selected a forbidden appendix. A keyword filter also excluded legitimate security-training evidence. Those failures remain in the datasets and reports.

Earlier container, browser and database results apply to the versions they tested. A new native test run does not refresh them. The [decision records](adr/) explain how the implementation and its checks developed.

## Remaining work

- Publish the reviewed source and inspect the actual remote CI results.
- Deploy and test a free hosted demonstration, including HTTPS, session isolation, cold starts, restart behavior and provider usage limits.
- Complete real managed sign-in and durable hosted storage before offering the full review service.
- Extend evaluation with independently written cases, realistic document layouts and targeted tests of threshold reasoning and hostile evidence.
- Finish a practical interview walkthrough that the project owner can explain and demonstrate.

PATCHWORK is deferred. Recordings are also deferred; they are not a prerequisite for hosting.
