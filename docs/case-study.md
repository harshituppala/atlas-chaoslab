# Reviewing a requirement is more than finding a matching sentence

ATLAS starts with an ordinary procurement problem: an RFP asks for a capability, and a team needs to determine what its own records actually substantiate. A relevant excerpt can be incomplete, out of date or directly at odds with the obligation. Passing that excerpt through a fluent model does not resolve the disagreement.

The seeded municipal example asks for recovery within four hours. The internal capability register guarantees eight. ATLAS puts the extracted obligation next to the selected excerpt, links each to its source and leaves the assessment pending. A reviewer can inspect the source before recording a decision. The tool does not make a legal-compliance determination.

## One workflow, with recoverable boundaries

The browser submits a job to FastAPI and follows its status. A separate worker extracts requirements, retrieves evidence and checks source identity before publishing a result. The database stores the job and ownership lease; a worker crash can lead to another attempt, but the old owner cannot publish afterward. Result, initial review state and audit data commit together.

This uses the existing database as a queue rather than introducing a broker. That choice keeps the transactional boundary small and lets the prototype run with fewer services. It does not establish unlimited queue throughput or fair scheduling across tenants.

Uploads retain immutable originals. Extracted PDF/DOCX text maps back to pages or paragraphs; citation offsets count Unicode characters and include the document hash. The browser highlights the exact source span. Parsing is bounded and performs no OCR. Complex reading order and table associations still require source review.

## Where the model helps, and where it fails

The default workbench uses an extractive baseline. The opt-in Bedrock path uses the same source/review boundaries and selects server-owned evidence choices rather than inventing offsets. Its drafts are still excerpts. An enabled API configuration and an explicitly opted-in worker are both required before paid jobs can run.

Three multi-obligation development scenarios produced five of nine passing baseline contracts and nine of nine recorded v4 model contracts. That is a useful result for those fixtures, not evidence that the model handles arbitrary contracts. A separate twelve-case transfer set retains two failures.

The paired hostile-evidence test is more revealing. The recorded model run passed eight of twelve cases, but selected an instruction-bearing appendix in one hostile case. The source spans were valid. Its relation label was still the expected contradicted label, so the observation supports an evidence-contamination finding rather than a claim that it followed every malicious instruction.

There were also ordinary failures: a 15-day deletion policy was called contradictory to a within-30-day requirement, and a keyword filter suppressed legitimate annual training evidence mentioning system prompt handling. Blocking more text can make a system less useful while still failing to stop a hostile record. Those cases remain frozen in the reports for the next experiment.

## What CHAOSLAB contributes

CHAOSLAB reads an adapter's JSON outputs and scores them against authored fixtures. Its scorer checks expected obligations and relations, exact evidence records, citation integrity, extractive drafts and pending review. Fault tests distinguish operational failure from successful abstention. The paired comparator rescored two raw runs under one dataset/scorer instead of comparing incompatible headline percentages; missing cases remain visible and obligation regressions cannot hide inside an already-failed scenario.

The harness is independent of ATLAS's decision logic, but the fixtures are same-author synthetic development data. That is implementation separation, not blinded external evaluation. Timings include the documented execution boundary; no production service-level claim follows.

## Storage, access and operation

The local default is SQLite. The PostgreSQL path has real restricted-role/row-policy and concurrency evidence, separately from the Linux Compose workflow. A logical recovery drill restored ten populated tables into a new empty cluster after deleting only the disposable source volume. Restored content and resumed work were checked; this was not an offsite or continuous backup test.

Managed access-token verification resolves workspace membership on each request. Provider claims cannot assign an application role. The Cognito-compatible profile has offline signature/claim tests, but a real browser/provider login remains unfinished. The local bearer-token launcher is deliberately private and must not be exposed as a public service.

Resource controls include request-body admission, parser limits, worker deadlines and bounded child pipes. These target concrete failure modes. They do not make trusted processes into hostile-code sandboxes or establish total-memory and distributed overload guarantees.

## Delivery status

The native suite passes 393 tests, with eighteen optional PostgreSQL groups skipped in that run; the database groups have separate executed evidence. Historical image, browser, backup and live-model reports identify their own scope and source. None automatically becomes current when another suite passes.

ATLAS has no hosted URL yet. Free hosting is required, and recordings are deferred. The next delivery decision must distinguish a durable authenticated service from a deliberately limited running synthetic lab. The public source release is being prepared separately from hosting. An implemented static replay remains a recorded artifact; it does not complete either hosted runtime.

[Run locally](../README.md#run-locally) · [Architecture](architecture.md) · [Threat model](threat-model.md) · [Hosting decision](deployment-options.md) · [Measured history](STATUS.md) · [Paired failure evidence](../reports/injection-pairs-live-v4.json)
