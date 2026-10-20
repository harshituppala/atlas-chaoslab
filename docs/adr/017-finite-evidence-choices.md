# ADR 017 — Finite evidence choices for provisional assessments

Status: implemented; measured live results recorded below when execution completes.

## Observed failure

V2 and V3 provider output was valid JSON but violated coupled domain constraints: a contradiction had no evidence IDs, or an abstention carried evidence. Prompt clarification alone did not remove these failures. Local validation correctly rejected these responses.

## Decision

Source-selection-v4 uses one required `choice` enum for assessment generation. The application constructs choices from one to three verified retrieval candidates: `insufficient`, or supported/contradicted paired with each nonempty candidate subset. Three candidates yield fifteen alternatives. Candidate IDs are application-owned; source text cannot define the enum. A local lookup reconstructs the existing validated EvidenceDecision and exact citations. The model never controls source offsets, draft prose, approval state or tools.

Unknown choices and extra response fields fail local validation. No repair or silent conversion of an invalid answer to abstention occurs. The original EvidenceDecision validator remains authoritative internally. Extraction, evidence scope checks and mandatory human review retain their existing behavior. With no retrieval candidate, the application abstains without an assessment call.

This encodes structural constraints, not semantic correctness. The model can still choose the wrong valid alternative, miss an obligation, misunderstand a condition or follow an injected instruction. The top-three retrieval limit is required to keep the choice space bounded; expanding it needs an explicit design change. Prompt clarification distinguishes absent guarantees from incompatible actual capabilities.

## Evaluation design

The original 18 cases remain development diagnostics. A separate twelve-case transfer set covers four new families with supported/contradicted/insufficient examples. It was authored after the v4 prompt was fixed and was not supplied as prompt examples; however, it shares the engineering author and simple synthetic style, so it is not a blinded independent holdout. The deterministic baseline passed 7/12, including zero correct abstentions out of four expected abstentions. Its executed report is `reports/reasoning-transfer-baseline.json`.

Tests exhaust all finite alternatives for one to three candidates, verify provider-schema enumeration, reject unknown/duplicate-ID/abstention-with-citation encodings and extra fields, exercise the real SDK stub through the batch runner and retain rejection of out-of-scope retrieval. The full default suite passed 208 tests with 17 optional database groups skipped. No new database or browser integration is implied.

## Transfer execution

The first live transfer run completed all 12 cases and passed 10. All 24 provider responses passed structural validation. The two remaining failures were a wrong contradiction for a 24-hour deletion capability against a 48-hour upper bound, and a strict extraction mismatch caused by omitting the obligation's final period. The latter is an exact-contract failure, not evidence that a substantive condition was lost. Original labels and scoring policy were preserved. Estimated token cost: USD 0.0182545, not an invoice. The one-case schema smoke passed at USD 0.0014465 estimated cost. Neither result establishes broad reasoning reliability.

The unchanged v4 also completed all 18 original cases: 17 passed, 35 provider responses passed local schema validation, and the only failure omitted the final period of the roadmap obligation. Estimated model cost was USD 0.0261140. These cases were already used during development; the result is not a generalization estimate.
