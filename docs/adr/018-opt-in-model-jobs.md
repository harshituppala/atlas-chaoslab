# ADR 018 — Explicit model jobs with terminal paid failures

Status: backend implemented; live evidence recorded separately below.

## Requirement

Connect the existing structured Bedrock workflow to durable reviews without allowing baseline retries, arbitrary caller-selected provider credentials, or worker crashes to trigger repeated paid executions.

## Decision

Job submission accepts an execution mode. Baseline is the default. Bedrock admission requires the operator's ATLAS_ENABLE_BEDROCK_JOBS=1 setting; viewers still cannot submit. The queue stores the configured model pipeline in its existing pipeline_version column and includes it in the idempotency fingerprint. Reusing a key across modes conflicts. No schema migration is required.

Model jobs have exactly one queue attempt. Baseline workers filter claims to their supported pipeline and leave model jobs queued. An explicitly opted-in worker handles both modes. Model execution runs in a separate child process with a 300-second deadline; baseline retains its existing execution path and deadline. On model failure, timeout, cancellation or expired lease, publication is fenced and automatic paid retries are disabled. Cancellation prevents publication but does not guarantee cancellation of an in-flight remote request or immediately stop the child; spending remains bounded by its configured reservation and deadline.

Each model job derives a private artifact key from tenant and job identity. Exclusive durable invocation reservation and cumulative campaign reservation precede credential initialization. A second execution cannot reuse those artifacts, even after interrupted work. The child records receipts privately and exposes only fixed failure categories to the parent. Provider config and session-budget paths are operator CLI arguments, not client-supplied fields. Both --model-config and --allow-paid are required. The API admission flag alone cannot initialize credentials.

The stored job pipeline selects the persistence validator. Model results must retain the original source snapshot, valid exact citations, extractive drafts, unique requirements and pending human review. Baseline jobs still reject model payloads. Model costs may be unknown; unknown never becomes zero. Model trace publication is restricted to a fixed integrity-check stage.

## Tradeoffs and remaining work

This prefers conservative at-most-one paid queue attempt to automatic recovery. A crash after successful inference but before database publication can leave a paid result unavailable; an operator must inspect private receipts. Remote providers do not offer an atomic transaction with the local database. This is not exactly-once inference or a distributed billing system. Multiple hosts must not assume a local POSIX journal is a shared budget lock.

The job pins the workflow version but not a full provider configuration fingerprint. The restricted role currently constrains the allowed model; persistent provider/model/region attribution and config pinning remain work before deployment. A dedicated user-facing mode selector is not implemented in this milestone. Admission is default-off, and no production or cloud deployment is claimed.

## Verification

239 default tests passed with 17 optional PostgreSQL groups skipped; Ruff passed. New offline cases verify mode-bound idempotency, baseline worker isolation, model readback, terminal timeouts/crashes, publication rollback, disabled admission, rejection of caller provider config, real SDK stub execution, funding-before-credentials and duplicate invocation exclusion. Stubbed live flags and synthetic prices are contract fixtures, not model accuracy or paid execution evidence.


A real one-case backend validation subsequently succeeded: synthetic FastAPI TestClient submission, isolated Bedrock child, SQLite publication and authenticated readback. The independent factual-support judge passed all checks for residency-exact. Estimated model cost USD 0.0014465, not an invoice. The initial attempt failed before inference during credential setup; its reservation was preserved. A non-inference check confirmed credential retrieval failure, then the existing restricted role was refreshed and verified before the new attempt. No failed job was replayed. Public report: reports/model-job-backend.json. This does not validate browser submission or PostgreSQL/model integration.
