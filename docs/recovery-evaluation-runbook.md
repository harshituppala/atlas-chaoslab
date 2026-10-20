# Recovery evaluation

CHAOSLAB compares observed queue behavior against authored expected outcomes. Each recovery adapter now runs in its own bounded process so a hang or crash becomes evidence and later cases can still execute.

From the repository root, using only disposable synthetic data:

```sh
PYTHONPATH=src .runtime/bin/python -m chaoslab.recovery \
  --dataset datasets/recovery.json \
  --adapter atlas.recovery_adapter:run \
  --deadline-seconds 10 \
  --output reports/recovery-isolated.json
```

The seven current cases cover expired ownership, cancellation, rollback, retry exhaustion, a last-attempt crash, competing claims and forged review state. Their adapter uses simulated lease time and temporary local SQLite. Running that adapter in an actual child process does not turn simulated clock advancement into a real availability or process-crash measurement. Historical reports/recovery.json remains separate from the newly executed isolated result.

A passing case must satisfy every nonempty authored expectation with the correct type. Operational errors are failed cases with fixed codes: adapter_deadline, adapter_output_budget, adapter_failure, invalid_observations or execution_error. Failures do not skip the remaining cases. The CLI writes the report before exit 1; malformed configuration or a changed source/dataset refuses a new report. Successful completion exits 0. New reports use schema version 2; raw adapter events and exception class names/messages are no longer exported.

Per-case latency includes process startup, imports, the adapter and serialization. It is not inference latency or a service SLO. The default ten-second parent deadline also includes those steps. Increasing it changes the experiment budget, not the expected outcomes. This fixture's simulated clocks must not be used to make a measured recovery-time claim.

Repeat the contract and regression gates:

```sh
mkdir -p var
PYTHONPATH=src .runtime/bin/python -m pytest -q \
  tests/test_recovery_runner.py tests/test_recovery_contract.py \
  --basetemp=var/recovery-runner-focused
PYTHONPATH=src .runtime/bin/python -m pytest -q \
  --basetemp=var/recovery-runner-full \
  --junitxml=var/recovery-runner-tests.xml
```

The focused tests deliberately execute hung/crashing/oversized adapters with fixed private canaries. They also verify continuation, nonzero CLI evidence, missing/wrong-typed observations, ambiguous goldens and preservation of old reports when source identity changes. Tests do not contact models or cloud services.

Select only trusted adapters. This boundary is not a hostile-code sandbox: filesystem/network access, escaped descendants, parent failure and aggregate memory/disk limits remain outside its guarantee. Only src Python bytes and dataset identity are checked; external adapter code is not covered. Reports copy authored case IDs and scope, so use public synthetic fixtures rather than private identifiers. See ADR 032 for the exact measured scope and evidence hash.
