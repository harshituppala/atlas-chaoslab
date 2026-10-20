# Interview walkthrough

Start by running the municipal RFP example. Open the four-hour recovery requirement and the eight-hour capability record, inspect both sources, then explain why retrieval alone cannot establish that the requirement is satisfied. Use the questions below to connect the demonstration to the code. The answers are study prompts; the project owner should be able to demonstrate each one independently.

## Sources and model output

**What does a valid citation prove?** A quote occurs at a particular Unicode span in a document with the expected hash. It does not prove that the quote supports the requirement, is current or establishes compliance. Show a case with valid citations and a wrong relation.

**Why use an extractive baseline?** It provides an inspectable, offline comparison before introducing model variability. It also exposes extraction and retrieval failures that fluent output can conceal. Show the requirement pattern the baseline still misses.

**Why restrict the model to evidence choices?** Trusted code owns source identity and reconstructs the selected spans. The model chooses among bounded evidence options and proposes a relation; it cannot invent offsets or approve a review. The hostile appendix result shows that valid choices and structured output still permit bad evidence selection.

**Why rank fusion?** BM25 and cosine scores have different scales. Reciprocal rank fusion combines their ordered results. Explain chunk overlap, encoder identity and why ten positive synthetic queries are too small to establish general retrieval quality.

**How do PDF and DOCX locations work?** PDF spans map to extracted text on physical pages. DOCX spans map to body/table paragraphs, not rendered pages. Original bytes and parser identity remain available. Demonstrate a citation after an emoji and explain the difference between Unicode character offsets and JavaScript UTF-16 indices. Reading order, tables and scans remain limitations.

## Jobs and reviews

**Why use the database as a queue?** It keeps job state, result publication and audit writes within one transactional system. A worker receives a lease token; renewal and publication require current ownership. After a lost lease, a replacement recomputes from the immutable input. There is no partial LangGraph-node resume or exactly-once external inference guarantee.

**What happens when two reviewers save at once?** Each update supplies the version the reviewer saw. Only the matching version can update, and its audit event commits in the same transaction. A stale write returns a conflict so the reviewer can inspect the newer decision.

**Why only one paid queue attempt?** A provider may finish work even if the client times out. Automatic retries could charge twice. Reservations precede invocation, private receipts preserve uncertain usage and the queue does not silently retry paid work. A successful remote call can still be lost before local publication; explain that tradeoff.

## Evaluation and boundaries

**What makes CHAOSLAB independent?** It consumes an adapter's JSON output and reconstructs scoring checks separately from ATLAS. Golden labels are not passed to the adapter. The fixtures are still same-author development data, so implementation separation is not external validation.

**Why count omissions separately?** Missing a requirement means no assessment was made. Counting it as insufficient evidence would reward failed extraction. Explain the difference between end-to-end metrics and metrics conditional on successful extraction.

**Which failures are most useful?** The model misread a 15-day deletion policy against a within-30-day requirement. A keyword filter removed legitimate security-training evidence. One hostile case cited an instruction-bearing appendix despite valid source spans. Explain a next experiment for each without changing the original expectations.

**What do row policies protect?** They catch omitted tenant filters and pooled-context mistakes. The trusted API and worker can set database identity context, so policies do not contain a fully compromised service. Show the separate runtime privileges and why the migration owner must not run the API.

**What remains unfinished?** Hosted operation, real identity-provider sign-in and broader evaluation. Local native, database, browser and container runs have different scopes. Be precise about which report supports each claim; do not present local operation as professional production experience.

For implementation details, use the [architecture](architecture.md), [threat model](threat-model.md), [current status](STATUS.md) and [case study](case-study.md).
