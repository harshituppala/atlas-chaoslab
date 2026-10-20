# ATLAS

A workspace for reviewing RFP requirements against capability records.

The sample starts with a simple disagreement: the RFP asks for recovery within four hours, while the capability register guarantees eight. ATLAS puts the requirement, selected evidence and review decision together so someone can inspect that mismatch before drafting a response.

[Open the fictional lab](https://atlas-review-lab.onrender.com) · [Local setup](../../README.md#run-atlas-locally) · [Case study](../../docs/case-study.md)

## The review

Upload a text-bearing PDF or DOCX, or paste the sources into the local workbench. A worker extracts obligations and selects evidence. Open a citation to inspect the highlighted text, then record a review. If another reviewer saved first, the stale update is rejected so neither decision is silently overwritten.

The default pipeline is extractive and runs offline. The optional Bedrock workflow chooses from server-owned evidence options and proposes a relation. It cannot generate citation offsets or approve its own assessment. Paid execution requires operator configuration.

The public lab is deliberately smaller: one fictional case, temporary sessions, constrained review notes and no uploads or paid inference. Its free host sleeps when idle. Session history resets on restart; it is not customer storage.

## Main decisions

Jobs live in the existing database. Expiring leases let a replacement worker recover work, while ownership checks prevent an old attempt from publishing late. The result, initial review state and audit event commit together. See the [queue decision](../../docs/adr/003-durable-jobs.md).

Documents are immutable snapshots. Citations carry a content hash and Unicode character offsets, checked again before publication. This establishes where the excerpt came from, not whether it satisfies the requirement. PDF pages and DOCX paragraphs retain their source locations; scans need OCR, which is not implemented.

PostgreSQL uses separate API and worker logins with tenant row policies. SQLite supports the private local demonstration. The [architecture](../../docs/architecture.md) and [threat model](../../docs/threat-model.md) describe the remaining trust assumptions.

## Checks and remaining work

Local and hosted checks cover source spans, review conflicts, session isolation and bounded execution. The first free deployment exposed a deadline that was too short for the host; that failure and its correction are recorded in the [hosting decision](../../docs/adr/036-hosted-lab-execution-budget.md).

Known model failures include a numeric-threshold mistake and hostile evidence selection. Real managed sign-in, durable hosted storage, broader document evaluation and production operation remain unfinished. [CHAOSLAB](../chaoslab/README.md) keeps evaluation separate from the application's own validation logic.
