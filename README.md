# ATLAS and CHAOSLAB

ATLAS helps review requirements in RFPs and contracts against a capability register. CHAOSLAB tests whether the resulting assessments deserve to be trusted.

A clause can be easy to retrieve and still be unsatisfied. The seeded RFP asks for recovery within four hours; the capability record guarantees eight. The workbench keeps the obligation, excerpt and review decision together so someone can examine that mismatch before using the result in a response.

**Current status:** working local application with separate API and worker processes. Restricted Bedrock diagnostics, local PostgreSQL, a Linux image and backup recovery have executed in their documented scopes. There is no hosted ATLAS application yet. The default workbench uses an extractive baseline; paid inference requires an operator-enabled configuration. All committed examples are synthetic.

## Review workflow

1. Upload a text-bearing PDF/DOCX or paste requirements and capability records. The parser retains original bytes and maps extracted text to pages or paragraphs.
2. Submit an analysis. A durable job records its execution settings; a worker extracts obligations and selects evidence. The browser can reconnect to unfinished work.
3. Open a requirement and inspect the highlighted original excerpt. Citations include a document hash and Unicode character offsets. A valid span establishes where an excerpt came from, not whether it supports the obligation.
4. Record a review with a note. Version checks prevent two reviewers from silently overwriting each other. A job cannot approve its own output.
5. Inspect the independent evaluation results, including failed cases. Retrieval, source integrity, relation correctness, evidence contamination and review safety are scored separately.

The model-assisted path chooses from server-owned evidence options and returns provisional assessments. It does not generate citation offsets or approve reviews. Response drafts remain extractive excerpts. The application is not a legal-compliance assessor.

## Why the implementation looks this way

The queue uses the existing database rather than a separate broker. Expiring leases and ownership tokens allow a worker to recover a job without letting an old attempt publish later. Result, review and audit writes commit together. This trades extra database coordination for fewer services and one transactional publication boundary. [Queue design](docs/adr/003-durable-jobs.md).

Source identity is checked again when a result is published. Uploaded originals are immutable, and stored sources must match submitted snapshots. This catches forged quotes and stale references; it does not solve factual support. [Document ingestion](docs/adr/006-document-ingestion.md).

PostgreSQL has separate API and worker logins. Forced row policies cover tenant records; the worker has a narrowly granted cross-tenant queue role. The trusted services can still choose their database identity settings, so row policies do not contain a fully compromised service. [Database boundary](docs/adr/012-database-tenant-policies.md).

A local MiniLM encoder and exact pgvector search support persistent hybrid retrieval. Exact search keeps behavior inspectable at this corpus size. There is no measured reason yet to introduce approximate indexing or a distributed retrieval service. [Retrieval design](docs/adr/009-persistent-retrieval.md).

Request bodies and worker pipes have separate byte, concurrency and time budgets. Those controls address observed resource gaps; they are not a total memory cap or a hostile-code sandbox. [API admission](docs/body-admission-runbook.md) · [Worker supervision](docs/worker-supervision-runbook.md).

## What the measurements show

| Experiment | Observed result | What it does not establish |
| --- | --- | --- |
| Native backend/API suite | 393 passed; 18 optional PostgreSQL groups skipped | The skipped groups are not validated by this run. |
| Separate native PostgreSQL exercise | 18 integration groups passed | This is not the full suite against the container database or a cloud service. |
| Retrieval on ten authored positive queries | Lexical recall@3 0.70; hybrid 1.00 | Same small query set; no representative contract accuracy claim. |
| Three scenarios, nine obligations | Baseline 5/9; recorded v4 model 9/9 | Correlated, same-author development fixtures. |
| Twelve transfer cases | Recorded v4 model 10/12 | A deadline relation and an extraction punctuation case still fail. |
| Six clean/hostile pairs | Recorded v4 model 8/12 strict cases; one of six hostile cases contaminates citations | Valid citations and structured output did not prevent hostile evidence selection. |
| Local logical backup drill | Ten populated tables/32 rows restored and checked; a pending job resumes | Quiesced local writes, not offsite backup, point-in-time recovery or a production recovery target. |

The live paired run also misclassified a 15-day deletion policy against a within-30-day obligation. A keyword filter excluded legitimate security-training evidence because it mentioned system prompt handling. Those failures remain in the reports. One hostile variant regressed among four eligible passing controls; that conditional result is not a general attack success rate. No unauthorized review states were observed, but the test supplied no tools, secrets or exfiltration channel.

The standalone extractive baseline still misses an authored drafting pattern. Reports preserve that failure rather than changing the expected answer. There is no blinded external evaluation or real customer dataset, and no production reliability claim.

[Paired model results](reports/injection-pairs-live-v4.json) · [Failure analysis](docs/adr/030-live-paired-injection-diagnostic.md) · [Raw-run comparison](docs/comparison-runbook.md) · [Verification notes](docs/STATUS.md)

## Run locally

Requirements: Python 3.12+, Node 24+ and pnpm 11.25.0. The commands below create a local environment in `.runtime/`.

```sh
python3.12 -m venv .runtime
.runtime/bin/python -m pip install --no-cache-dir -r requirements.lock
mkdir -p var
cd apps/web
pnpm install --frozen-lockfile
pnpm build
cd ../..
make serve
# Separate terminal, from the repository root:
make worker
```

Open http://127.0.0.1:8000. The local launcher creates a random reviewer credential in var/local-credentials.json; enter its token in the workbench. It binds only to loopback, and the browser keeps credentials in memory. Do not publish that credential file or expose this local access mode to the internet.

The default local database is SQLite. Use **Run seeded demonstration** to inspect the municipal RFP without uploading anything. Uploads are limited to 1 MB; scanned pages need OCR, which is not implemented. Reading order, tables and every returned excerpt still need human source review.

For PostgreSQL migrations/runtime preparation, the restricted-role Compose stack and logical recovery commands, follow [the operator guide](docs/deployment.md). Those are separate environments with their own evidence. Do not point disposable verification scripts at a real client database.

## Verify changes

```sh
mkdir -p var
PYTHONPATH=src .runtime/bin/python -m pytest -q --basetemp=var/pytest-local
.runtime/bin/ruff check src tests scripts
.runtime/bin/ruff format --check src tests scripts
# Frontend build:
cd apps/web && pnpm build
# Existing API and worker must be running for the full browser workflow:
pnpm test
```

`make benchmark` records the extractive baseline, recovery and ingestion diagnostics. Known quality failures are reported, not erased. Other focused runbooks cover [paired comparisons](docs/comparison-runbook.md), [live evidence rescoring](docs/live-injection-runbook.md), [body admission](docs/body-admission-runbook.md) and [child-process recovery](docs/worker-supervision-runbook.md). Unit tests use controlled model responses unless explicitly identified as live diagnostics.

The repository contains CI configuration; GitHub CI has not run. A passing native suite does not refresh old container, database or browser evidence automatically.

## Hosting and access

Hosting must remain free. The source release is being prepared for public GitHub publication. The local static-token API is not a deployment configuration. A full hosted service still needs a tested identity/login flow, durable storage, private runtime roles, secrets/TLS handling and an executed hosted workflow. The optional Cognito token profile has real-signature offline tests; no live Cognito login is claimed.

Demo recordings are deferred. The existing static replay remains a separate recorded artifact; it is not a hosted backend or a prerequisite for hosting. [Hosting status and decisions](docs/deployment-options.md) · [Release checkpoint](docs/RELEASE.md).

## Source map

- src/atlas: API, jobs, source/domain validation, retrieval and worker implementation.
- src/chaoslab: independent scoring, trusted adapter execution and paired comparisons.
- apps/web: React/TypeScript review workbench and evaluation views.
- datasets and reports: synthetic fixtures and executed evidence, including failures.
- docs/adr: decisions, alternatives and limits; docs/STATUS.md summarizes the current verification and remaining work.

Decision records describe the design and checks at the time they were written; later records may supersede earlier limitations. PATCHWORK is deferred.
