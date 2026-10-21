# Admit saved observations before scoring

Three malformed saved bundles exposed uncontrolled exceptions in paired comparison: an array at the root raised AttributeError, missing results raised KeyError, and a null result row raised TypeError. The command exited as a crashed process instead of identifying an invalid experiment. The earlier report stayed intact, but the exit status did not match the documented contract.

Shared structural admission now checks bundle rows, source snapshots, assessments, requirements and citations before the scorer indexes those fields. Errors describe a field or container without copying its contents. A saved succeeded row must contain a usable observation. Missing attempts still remain unpaired, and recorded failed attempts still count as attempted failures.

This does not validate an answer's correctness. A wrong digest, out-of-source integer span, unknown relation string, unauthorized approval or omitted requirement remains a scored failure. The validators do not replace the existing citation, source-binding, review-state or evidence checks. During a fresh scenario run, an unusable adapter response is recorded as an attempted failure rather than published as succeeded or silently omitted.

The comparison reader retains its eight-megabyte input budget and duplicate-key refusal. It also rejects floating-point overflow, invalid encoding and nesting beyond 64 levels. This limit is explicit: a first test depended on the interpreter rejecting 2,000 nested lists, but that depth was accepted on this runtime. Admission now walks parsed containers iteratively and tests the exact 64/65 boundary. This is a local evaluation boundary, not a hostile-code or hard memory sandbox.

Observations permit at most 101 documents, 1,000 assessments and 1,000 citations per assessment. These are structural budgets, not recommended document sizes or claims about supported business workloads. Source documents and obligation text retain their existing length bounds.

## Verification

The native suite passed 616 tests, with eighteen optional PostgreSQL groups skipped. Controlled cases cover nineteen malformed observation shapes through both the Python boundary and comparison CLI; each CLI case exits 2 and preserves the old report. Five wrong-but-usable answers remain scored regressions. Separate cases cover numeric overflow, encoding, nesting and malformed live adapter responses.

The standalone evaluator is version 0.1.1. The [installation report](../../reports/chaoslab-package.json) records a new wheel installed without ATLAS or third-party runtime dependencies. Eight controlled checks cover unchanged output, corrupt citations, missing attempts, invalid golden labels, array artifacts, null rows, numeric overflow and excessive nesting. Invalid experiments preserve the previous report; genuine fixture failures still write evidence and exit 1.

A fresh extractive scenario run remains five of nine obligation contracts passing and zero of three complete scenarios. Golden expectations and historical model reports were unchanged. No model calls or hosted deployments were made. These checks improve evaluator failure semantics; they do not add an external dataset, a second application adapter or new evidence of model quality.
