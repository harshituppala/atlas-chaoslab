# Worker child supervision

Baseline and opt-in model jobs now use concurrent bounded POSIX pipes rather than capturing unbounded output before checking it. Defaults per invocation: 1,500,000 encoded input bytes, 8,000,000 stdout bytes, 65,536 stderr bytes; baseline deadline 120 seconds, model deadline 300 seconds. The input limit is checked before spawning, output limits during reads. Each invocation owns a new process group, which is killed/reaped on failure and cleaned up after normal completion.

## Failure handling

Resource-budget failures indicate excess encoded input, result output or diagnostic output. stderr is counted/discarded and is not available in a public log or exception. Inspect the trusted implementation and existing private model journals/receipts as appropriate; do not log document bodies, raw child output or credentials. Unexpected child termination still reaches the existing fenced queue failure path. A following job can run without recycling the worker.

A model timeout or killed child may still represent a billable provider request. Do not delete or refund conservative reservations, erase uncertain receipts or automatically resubmit the paid job. Model attempts remain one. Renewed provider access and any expenditure must follow the existing user-authorized budget; this supervisor grants no new spending authority.

The limit bounds pipe retention, not total memory: input serialization, result conversion/JSON decoding, kernel pipes and child libraries add allocations. Process-group cleanup is not arbitrary-code containment; a child can escape a group or use other host resources, and a hard-killed parent/host failure cannot execute cleanup. This is POSIX-specific. Use separate container/OS controls for broader boundaries, with their own executed evidence.

## Reproduce

From the repository root:

```sh
PYTHONPATH=src .runtime/bin/python -m pytest -q tests/test_child_process.py \
  --basetemp=var/pytest-child-process
PYTHONPATH=src .runtime/bin/python -m pytest -q \
  --basetemp=var/pytest-worker-supervision --junitxml=var/worker-supervision-tests.xml
PYTHONPATH=src .runtime/bin/python scripts/verify_worker_supervision.py
```

The recorder refuses missing/failing focused tests or a failed native suite, then creates its own temporary SQLite database under var/worker-supervision and runs a timeout followed by a real successful baseline job. It disposes the engine and removes that temporary database. It writes only aggregate/check/hash evidence to reports/worker-supervision.json, not source-bearing results, model receipts, credentials or raw JUnit errors.

At this milestone: 18 focused supervision tests, 384 full-suite passes and 18 opt-in PostgreSQL skips. Tests include real native subprocesses and descendant heartbeat checks; model wiring uses controlled data. The recorder separately identifies post-execution test hashes and before/after queue-exercise source hashes. It establishes no provider cancellation, full process-tree sandbox, deployed/container behavior or cloud billing reconciliation. The pending immutable source-release candidate is unchanged.
