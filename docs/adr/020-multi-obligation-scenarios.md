# ADR 020 — Evaluate complete reviews across multiple evidence records

Status: independent scorer implemented; actual results recorded below.

The earlier one-obligation diagnostics do not test whether an agent can extract several obligations, keep evidence associated with the right obligation, combine records or avoid historical distractors. Added three authored synthetic scenarios with three obligations each: current/historical identity capabilities; retention/recovery/residency; split encryption support plus notice/response obligations. Labels and source sets were fixed before model execution, with no new prompt examples or model tuning.

The independent scorer requires exact obligation extraction, unique requirement IDs, valid source spans/hashes, exact expected evidence record sets, full authored evidence excerpts, the expected relation, extractive drafts and pending human review. All required supporting records must be cited for split evidence. Extra/duplicate obligations and evidence fail. Failed executions remain errors for every affected obligation. Partial coverage reports unrun scenarios explicitly. Dataset/input/source drift and duplicate artifact cases are rejected. Inputs exported to the model contain opaque case IDs and no labels or expected evidence sets.

These are same-author development fixtures, not independently blinded annotations or representative contracts. Full-record selection and exact extraction are conservative; failures can include punctuation mismatches. The requirement-pass count and complete-scenario count answer different questions. Operational failures count against the end-to-end denominator and cannot be relabeled successful abstentions.

Executed deterministic baseline: 5/9 obligation contracts passed and 0/3 complete scenarios passed. All outcomes are preserved in reports/scenarios-baseline.json. Eleven positive/mutation/binding tests verify perfect split support, missing records, omissions, duplicate IDs/evidence, forged spans, approvals, unsupported drafts, extras and operational failures. The default suite passed 258 tests, with 18 optional database groups skipped. No model-quality conclusion follows from those regression tests.


The unchanged source-selection-v4 model completed all three scenarios and passed all nine obligation contracts, including split evidence and exclusion of the historical distractor. All twelve provider responses passed structural validation. Estimated token cost USD 0.0100232, not an invoice. The cumulative campaign retains the full USD 0.1216512 worst-case allowance for this run. Runtime source identity was unchanged at completion; the public artifact retains model/source/dataset/scoring-module identity and the private artifact hash. This small authored set cannot establish broad reliability, and earlier transfer failures remain published.

CHAOSLAB now displays these results separately from one-obligation reasoning diagnostics. It shows obligation counts, full-scenario counts, unrun coverage, cost estimates and case-level outcomes. Reports with different dataset identities are labelled non-comparable. No model is called while viewing reports.
