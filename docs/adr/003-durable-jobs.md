# ADR 003 — Durable jobs in the existing database

Status: accepted for the local reliability milestone.

Document analysis must survive HTTP disconnects and worker crashes. The application already needs a transactional database; at the demonstrated scale, using that database for a queue avoids another operational service. Computation is at least once. The result, initial review rows, job terminal state, and audit events are published in one transaction.

A claim increments attempts and receives a random lease token. Renewal and publication require the job to remain running, the token to match, and the lease to remain unexpired. Cancellation revokes the token. An expired worker cannot renew or publish even if its computation later succeeds. A replacement worker recomputes from the immutable stored input. Queue admission binds the tenant's idempotency key to both input and pipeline version.

A separate child process executes each analysis with a 120-second timeout. Python's subprocess timeout terminates and reaps the child. A heartbeat thread renews database ownership while the parent waits. If renewal fails, publication fails closed. Timeout/connection failures use bounded exponential delay, with a default three-attempt ceiling. Other execution errors and budget refusals terminate the job. An exhausted expired claim is reaped to failed when a worker next polls.

Claiming uses conditional UPDATE predicates and RETURNING. SQLite serializes writers. PostgreSQL semantics are not yet integration-tested. There is no exactly-once claim for model calls, billing, email, or other external side effects: future external tools need provider idempotency and their own side-effect contracts.

Tradeoffs and limits: one trusted worker polls globally across tenants; no per-tenant fairness, admission quota, broker-driven wakeup, or strong sandboxing of arbitrary third-party code is implemented. This child process executes only our trusted module. Cancellation immediately prevents publication but can leave the current computation running until its deadline. Cleanup/retention, migrations, real PostgreSQL concurrency, and load limits remain deployment gates.

Alternatives: an in-memory task loses work on restart; a full distributed broker adds operational cost before there is a demonstrated queue throughput need. Revisit this decision using measured contention, queue latency, and fairness requirements.

References: https://docs.sqlalchemy.org/en/20/core/connections.html#using-transactions and https://docs.python.org/3/library/subprocess.html#subprocess.run.
