# Run a contract model evaluation

CHAOSLAB owns the contract task, annotations and scoring. The Bedrock integration lives in `atlas.models.contract_evaluation` because it reuses the existing provider gateway and spending ledger. It requires the full project environment; the standalone evaluator wheel does not install boto3, Pydantic or ATLAS. Saved observations can still be scored by that wheel without provider access.

## Prepare the run

Read the [dataset terms and task boundaries](contractnli-evaluation.md) first. The runner admits only the pinned development archive. It does not load training or test JSON. It evaluates the complete development split rather than choosing contracts based on model answers.

Use temporary credentials for the restricted Bedrock role. A browser console session alone does not configure the SDK. Keep the SDK configuration, login cache and credential helper inside the private project directory, and verify the assumed role before enabling inference. No credentials belong in source, model inputs or public reports.

Create an owner-only model configuration under `var/bedrock/`, following the fields in [the Bedrock guide](bedrock-live-validation.md). It needs the exact model/profile and region, input/output token limits, a call limit, a total reserved-token limit, a dollar limit and a recently verified official price card. This task needs capacity for all 61 document calls. A configuration that can fund only a subset is refused before provider setup.

The recorded run configuration reserves at most 24,000 input and 4,096 output tokens per call, with 61 calls and 1,713,856 reserved tokens in total. These are conservative ceilings, not measured usage. Price-card amounts and the campaign's remaining authorization must be reviewed separately. Do not assume unused AWS credits remove the need for a spending limit.

## Check the plan

```sh
PYTHONPATH=src .runtime/bin/python -m atlas.models.contract_evaluation \
  --archive var/external-data/contractnli/contract-nli.zip \
  --config var/bedrock/contract-development-v1-config.json \
  --run-dir var/contract-model-runs/development-v1
```

The command checks the configuration, archive, full-split call capacity and every prompt locally. It prints a reservation plan. It does not resolve provider credentials, count tokens remotely, reserve campaign spending or create the run directory. The example configuration is private and is not bundled with a fresh checkout.

Only after access and spending are authorized, run the same command with:

```sh
  --session-budget var/bedrock/campaign-budget.json --allow-paid
```

Append those flags to the full command above. Initialize the campaign budget through the existing [spending controls](../src/atlas/models/session_budget.py) only after explicit authorization; never reset an existing campaign file to make room for another run. `--allow-paid` is an operator gate, not evidence of user approval.

## Read the outcome

One provider gateway and ledger cover the whole split. Before any potentially billable request, the gateway checks the token count and persists a reservation. SDK retries are disabled. The CLI spaces request starts at least ten seconds apart by default; `--min-interval-seconds` accepts a reviewed value between zero and sixty. Pacing reduces request bursts, but is not a verified provider quota guarantee. The campaign retains its full run reservation after failures or process death; it does not automatically refund calls that might have been charged. This limits cooperating project commands, not unrelated AWS use or the credit-card bill.

The model receives the contract, fixed claims and numbered evidence candidates. Expected labels and evidence annotations stay in CHAOSLAB. Contract and claim text remain untrusted task data in the request. The system prompt asks the model to ignore embedded instructions, but request construction tests do not prove resistance to prompt injection.

Under the new run directory:

- `run.json` records completion, aggregate scores and source fingerprints. A stopped cohort has no scores.
- `usage.json` preserves the gateway's request receipts and known or unknown cost estimates. Estimates are not invoices.
- `observations.jsonl` contains a complete private run for replay. An interrupted or stopped run keeps `observations.partial.jsonl` instead.

A wrong but usable prediction remains a scored mistake. Omissions stay missing. A truncated or structurally unusable completed provider response counts against all claims in that document and is not retried. The provider gateway rejects that response before returning raw predictions, so the observation records an invocation failure; its usage receipt retains the bounded failure category, not the rejected response body.

A provider failure, unknown usage, exhausted resource budget, failed recording or changed source stops the cohort. The result does not present the completed prefix as a full-split accuracy score. Review the private receipt and reconcile uncertain billing before any new run; choose a new directory rather than overwriting the failed one.

For a complete run, use the independent `chaoslab-contractnli --replay` command in the [task guide](contractnli-evaluation.md#save-a-run-and-rescore-it). Check equality of the result objects and the observation digest/count. Replay makes no provider request. Keep raw responses private: they can quote licensed contract text. Review any aggregate report before publishing it, and retain the development-only and possible pretraining-exposure qualifications.

Token-count failures now persist a bounded `preflight_failure` diagnostic in `usage.json`: a transport category, an allowlisted service code and `inference_sent: false` for that attempt. Unknown codes and messages are discarded. This is the last failed preflight, not a complete event history; a later success does not erase it. It creates no inference receipt, refund or retry. Earlier stopped runs predate this diagnostic and cannot be retrospectively classified. See [the decision](adr/052-token-preflight-diagnostics.md).

## Audit a stopped checkpoint

Before planning another paid run, inspect the preserved prefix without opening AWS credentials:

```sh
PYTHONPATH=src python -m atlas.models.contract_checkpoint \
  --archive var/external-data/contractnli/contract-nli.zip \
  --run-dir var/contract-model-runs/development-paced-v2 \
  --session-budget var/bedrock/campaign-budget.json \
  --output var/contract-model-runs/checkpoint-review.json
```

Choose a new report path outside the original run directory. Existing output is refused. Inputs must remain private under `var/`; the official archive is verified and only development JSON is read. The audit matches the ordered prefix to its input digests, prompt/schema fingerprints, validated receipts and retained full-cohort reservation. It publishes no document predictions or accuracy.

A successful audit is not a resume command. `automatic_resume_allowed` remains false. No ledger or journal changes, refunds, new reservations or provider requests follow from it. Preserve the audit fingerprint for a later continuation review. The original failure cause remains unknown, and old partial response bytes are not provider-authenticated. See [ADR 054](adr/054-stopped-contract-checkpoints.md) and the [recorded audits](../reports/contract-checkpoints.json).
