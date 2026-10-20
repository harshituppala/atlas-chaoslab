# ADR 027: compare raw outputs under a single scoring contract

Date: 2026-10-18. Status: implemented and verified locally.

## Problem and decision

Comparing aggregate pass rates can hide changed fixtures, different scoring rules, unrun cases or an obligation regression inside a scenario that already fails. Historical baseline and model reports also carry different source-provenance fields. Add a provider-independent offline comparison over raw scenario bundles, rescoring both sides in the same process with the same authored dataset and current scorer. Do not infer compatibility merely from two summary percentages.

Dataset bytes must match the parsed dataset object and each bundle's dataset hash. Scenario IDs are bounded and unique; each scenario requires a nonempty set of unique expected obligation texts. Existing score_bundle gates bind opaque case IDs, per-case input digests, source snapshots and exact citation/draft/pending-review contracts. Rows pair by authored identity, independently of result ordering; obligations pair by position within the frozen scenario and carry the original text digest. Unknown/duplicate IDs, foreign inputs/sources and unknown execution statuses refuse publication rather than becoming apparent improvements.

## Missing data and outcome semantics

Missing attempts are null and unpaired, even if the other side passes. An attempted operational failure is a strict failure with an explicit execution-failed status; its exception text is not exported. Both-pass, both-fail, improved, regressed and unpaired counts are separate at scenario and obligation levels. Opposite transitions cannot cancel to pass the optional fixture gate.

fixture_gate_passed requires complete paired coverage, no execution failures on either side, no scenario or obligation regressions, and every candidate scenario passing. This is an authored-fixture gate only. The optional --require-fixture-gate flag writes the failed evidence before exiting nonzero; without that flag the CLI is a descriptive report generator. Neither mode approves deployment, publication, broad model superiority, prompt-injection resistance or human requirements reviews.

Obligations are correlated within scenarios. No statistical significance, independent sample-size inflation, confidence claim or latency/cost comparison is computed. A transition from execution failure to success is visibly a strict-outcome improvement, not necessarily better reasoning; the execution-failure count prevents it from passing the fixture gate.

## Artifact boundary and provenance

The CLI bounds each input to 8 MB before parsing, rejects duplicate JSON keys and non-finite constants, refuses output paths aliasing inputs, and uses atomic report replacement only after validation. Dataset/reference/candidate bytes and comparison/scenario/citation-helper source digests are bound before and checked after rescoring. Source/input drift refuses publication and preserves previous measured evidence. Public output projects only outcome booleans, dataset-owned IDs, obligation indices/digests and bounded provenance, not raw model outputs, prompts, source text, exception strings or credentials. This is not a general-purpose redaction guarantee for private datasets, whose authored identifiers are still visible.

Hash checks identify saved bytes, not signed original provider execution or loaded-code attestations. Adapters used by the experiment remain trusted subprocesses with the user's filesystem/network permissions, not hostile-code sandboxes. This change does not alter ATLAS's execution pipeline or old golden labels, so pipeline versions stay unchanged.

## Actual experiment and verification

scripts/compare_recorded_scenarios.py verifies the retained October 16 Bedrock artifact against its original public report's artifact digest, executes three fresh local extractive-baseline adapter subprocesses with label-free inputs, and rescores both bundles together. No provider call is made. The resulting reports/scenario-comparison.json records full coverage of three authored scenarios/nine obligations, five obligations passing on both sides and four improvements, with zero regressions or operational failures. All three complete scenario contracts improve from fail to pass. These observations are confined to this same-author development set; transfer/hostile-evidence failures remain in their original reports.

Twenty-two new mutation/coverage/CLI cases pass, including hidden obligation regressions within failed scenarios, cancelling improvements/regressions, empty sides, operational failures, reordered rows, identity/source confusion, ambiguous/oversized JSON, input aliasing, failed-gate exit status and preservation of existing evidence on drift. The full native backend suite passes 348 tests with 18 optional PostgreSQL skips. No frontend changes, new model calls, remote CI, Linux/container rerun, cloud provisioning, publication or modifications to the immutable release candidate are claimed by this milestone.
