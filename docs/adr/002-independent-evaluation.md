# ADR 002 — Independent evaluator with a JSON adapter boundary

Status: accepted.

CHAOSLAB consumes a versioned input corpus and an adapter returning assessments, traces, and external-model cost. It independently scores the result. ATLAS owns its adapter, keeping the evaluator usable with another system.

Expected answers must be hand-authored or independently annotated; generated outputs must never create the gold labels. Repeated measurements are timing samples, not independent quality cases. Reports include dataset/source hashes, revision, dirty status, Python/environment identity, per-case checks, and failures. Latency percentiles on this small local corpus are descriptive.

Tradeoffs: the initial runner is synchronous and local. It cannot enforce resource isolation for arbitrary adapters; only trusted local adapters may run. Hosted runners need sandboxing, timeouts, artifact validation, and separate trust boundaries.
