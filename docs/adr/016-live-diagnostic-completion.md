# ADR 016 — Complete diagnostic coverage without accepting invalid outputs

Status: implemented; live results recorded separately from the extractive baseline.

## Observed requirement

The first complete live smoke passed. A larger run stopped on the second case when a structurally constrained provider response failed local domain validation. Stopping on every model-quality failure prevents a diagnostic set from revealing its full failure distribution.

## Decision

Default batch execution still stops on any failure. The explicit `--continue-invalid-output` evaluation option continues only after InvalidModelOutput while preserving that case as failed. Provider failures, unknown-billing receipts, exhausted budgets and other exceptions still stop the batch. One gateway and ledger cover the run, and the cumulative campaign allowance reserves the whole configured upper bound before provider initialization. This option changes evaluation collection only; it neither repairs outputs nor changes model inference prompts, citation gates or pipeline semantics.

Future invalid-response receipts contain a fixed local diagnostic code for abstention with evidence, unsupported positive relations without evidence, duplicate evidence IDs, or generic schema/response failure. Raw responses, upstream messages and Pydantic input values are not retained in those diagnostic fields. Failed cases remain operational/contract failures in the independent score; repetitions do not increase the number of authored cases.

## Interpretation

The eighteen synthetic cases are targeted diagnostics authored before this model run, not a representative production sample or blinded holdout. Live model results must be published separately from `reports/reasoning.json`, which remains the deterministic baseline. A completed call is not proof of factual support: the independent judge must still verify the full expected obligation, reference context, exact source identities, pending review and draft rules. Successful account use validates only this selected model/profile/configuration, not AWS deployment, production credentials or cloud SLAs.


## Executed evidence

Source-selection-v2 passed 12/18 complete synthetic cases, rejecting six missing-evidence contradictions. Its USD 0.0259776 estimated model cost is not an invoice. Clarifying contradiction evidence in source-selection-v3 did not establish a full-set improvement: 11 of 15 attempted cases passed, two abstentions carried evidence, one relation was wrong, and one provider failure stopped execution with unknown billing. Three cases were not run. Reports retain the failures and null unknown cost. The modified prompt was evaluated on seen development cases; further independent coverage is needed. The source-selection version changes with the prompt; diagnostic continuation itself does not relax inference contracts.
