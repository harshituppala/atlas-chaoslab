# 032 — Bound the recovery evaluator's adapter execution

Date: October 19, 2026
Status: implemented and executed locally

## Problem

The general CHAOSLAB scenario runner already used a disposable adapter process. The recovery runner instead imported and called its adapter directly in the judge process. A hanging recovery adapter could stop the entire campaign, mutate judge-owned inputs in memory, and prevent evidence for later cases from being written. That is a concrete gap in a tool intended to measure failure behavior.

## Decision

Use CHAOSLAB's existing adapter invocation boundary for every recovery case. A parent deadline defaults to ten seconds and can be set from greater than zero through 120 seconds. Each adapter receives a serialized copy of only its input, not the expected outcomes. Existing input/output limits and same-process-group cleanup apply; no ATLAS internals are imported by the judge. The default ATLAS recovery adapter remains an explicitly selected trusted implementation.

Operational failures become fixed error codes and strict failed cases. They do not stop later cases; the CLI saves the complete report before returning nonzero. Exception names/messages, raw adapter events and unknown output fields do not enter the report. Only contract-owned observation keys, bounded integer counts, booleans and known queue states are projected. An invalid or missing observation remains null and fails the independent comparison. Valid-but-wrong values remain visible.

The authored dataset must have one through 32 uniquely named cases and nonempty expectations under the known recovery contract. Duplicate JSON fields, non-finite constants, wrong-typed counters, unknown expectation fields and ambiguous envelopes are refused. Input bytes are bounded. Output cannot overwrite the input dataset or a file in the repository's datasets directory. Python source and dataset bytes are captured before execution and checked again before atomic report replacement. A changed identity preserves the previous report.

Report schema advances to version 2 because process/error/projection semantics changed. AI extraction/retrieval and their pipeline versions are unchanged. The seven original recovery inputs and expectations, and the historical reports/recovery.json, remain unchanged.

## Executed evidence

Nineteen new checks include real adapter hang, overflow, crash and malformed-output processes. A timed-out first case becomes adapter_deadline while the following case still passes. Wrong-typed counters and private canaries fail without entering the public report; CLI failure writes evidence before exit 1. Controlled checks cover strict datasets, output protection and changed-source/dataset refusal. Together with the existing recovery scorer test, the focused run passed 20 cases.

All seven original authored recovery cases passed through the new real process boundary; reports/recovery-isolated.json records the actual result and before/after source identity. Their lease time is still simulated. Process isolation of these adapters is not a new real crash/restart or wall-clock-jump experiment, and does not explain the earlier intermittent queue test failure.

The full native regression run passed 421 tests with 18 optional PostgreSQL skips. Ruff and 130 Python formatting checks passed. The private full JUnit artifact's SHA-256 is 8ae56ef91830f273646b17dc705cf5ed01459160a26b67fa393d482d8a40ef76. This is a hash of local evidence, not an execution attestation or independent external audit.

## Limits

These are trusted adapters with the user's filesystem and network privileges. They may lie about observations; comparison is against authored contracts, not signed service telemetry. A child can escape its process group, and the file-size control is not a total disk or RSS budget. Parent SIGKILL/host failure can prevent cleanup. External adapter code outside src is outside the source digest. Dataset case IDs and scope text remain trusted author-owned report content; this projection is not a general private-dataset redactor. There were no paid calls, hosted execution, new PostgreSQL/image checks or publication in this milestone.
