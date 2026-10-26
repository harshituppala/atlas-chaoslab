# Run the separate contract test evaluation

The development comparison is complete. The test run uses the same Claude Haiku 4.5 adapter on a separate split, with the rules fixed before test inputs were loaded. Its [complete result](contractnli-evaluation.md#frozen-test-result--october-26), protocol and independent replay are recorded. The commands below reproduce the process; do not rerun paid inference just to inspect the saved result.

## What is fixed

The [protocol](../reports/contract-test-protocol.json) binds the archive, test member, model and region, tokenizer, input/output limits, system prompt, request/schema code and scorer files. Macro label F1 is the primary measure. Label accuracy, joint label/evidence correctness, evidence precision/recall, per-class results and the confusion matrix are reported alongside it. The reference always predicts `NotMentioned` and selects no evidence.

Every contract and fixed claim is included in archive order. A missing prediction stays in the denominator. A completed but unusable response fails every claim in that document. Provider or uncertain-usage failures stop the cohort, preserve the reservation and leave an incomplete journal. There are no automatic retries or prompt changes after test exposure.

The normal development command still reads only development JSON. Test inputs use a separate task identity and journal header. A development journal cannot be replayed as test observations.

## Freeze before opening test JSON

With the original archive and a complete independently replayed development report available privately:

```sh
PYTHONPATH=src .runtime/bin/python -m atlas.models.contract_holdout \
  --archive var/external-data/contractnli/contract-nli.zip \
  --config var/bedrock/contract-holdout-v1-config.json \
  --protocol var/contract-model-runs/test-protocol-v1.json \
  --development-report reports/contract-model-development.json \
  --development-observations var/contract-model-runs/development-continued-v3/observations.jsonl \
  --freeze
```

Freezing replays development observations, checks them against the complete report and writes a new private protocol. It reads no test JSON and makes no provider request. An existing destination is refused. Keep the returned checksum separately; later commands require that exact value. The recorded protocol above already exists: do not overwrite or regenerate it for the same test experiment.

## Check the whole run without AWS

```sh
PYTHONPATH=src .runtime/bin/python -m atlas.models.contract_holdout \
  --archive var/external-data/contractnli/contract-nli.zip \
  --config var/bedrock/contract-holdout-v1-config.json \
  --protocol var/contract-model-runs/test-protocol-v1.json \
  --protocol-sha256 CHECKSUM_FROM_FREEZE \
  --run-dir var/contract-model-runs/test-v1
```

This checks the frozen rules before opening test JSON, admits every label-free request and prints the full reservation plan. It performs no credential lookup, remote token count or reservation, and creates no run directory. The recorded plan covers all 123 contracts and reserves capacity for exactly 123 calls, even when the configuration allows more.

The shared configuration accepts up to 200 calls so this cohort fits in one run. Its default remains twelve. This is a capacity bound, not spending permission: the existing campaign ledger must still fund the complete reservation. A request that cannot fund the whole split fails before provider setup.

## Execute only with access and spending approval

The owner approved a cumulative US$18 model-testing allowance for this cohort. Existing reservations stay intact. Check the exact restricted SDK identity and current official prices before adding these flags to the command above:

```sh
  --session-budget var/bedrock/campaign-budget.json --allow-paid
```

Do not reuse a directory once execution has begun. One gateway and ledger cover the cohort. The runner rechecks the protocol and execution recipe around every call. A change stops the run rather than being counted as an ordinary wrong answer. Source checksums identify local files; they do not prove which bytes were loaded into memory or protect against an owner who rewrites the code and checksums together.

## Replay without the model

A complete test journal can be rescored by CHAOSLAB without ATLAS or a provider SDK:

```sh
chaoslab-contractnli-test \
  --archive var/external-data/contractnli/contract-nli.zip \
  --protocol var/contract-model-runs/test-protocol-v1.json \
  --protocol-sha256 CHECKSUM_FROM_FREEZE \
  --replay var/contract-model-runs/test-v1/observations.jsonl \
  --output var/contract-test-replayed.json
```

Replay checks the pinned protocol, scorer, dataset and complete journal before writing aggregate results. It neither imports the named adapter nor contacts a provider. Match its result object with the model run before publication. Keep raw contracts, annotations, predictions and provider records private.

This is a public NDA dataset that may have appeared in pretraining. A frozen test result can measure this experiment without post-test tuning; it cannot establish performance on previously unseen private contracts, RFP accuracy or legal correctness.


## Export the completed model run

The reviewed aggregate export checks the complete live-run status, protocol/source identity, journal adapter, replay equality, all 123 usage receipts, model/region and token limits before writing a report:

```sh
PYTHONPATH=src .runtime/bin/python scripts/record_contract_test.py \
  --archive var/external-data/contractnli/contract-nli.zip \
  --protocol var/contract-model-runs/test-protocol-v1.json \
  --protocol-sha256 CHECKSUM_FROM_FREEZE \
  --run-dir var/contract-model-runs/test-v1 \
  --output var/contract-model-test.json
```

Thirteen fictional controls reject partial or non-live runs, changed scores, source, protocol, receipt identity, call limits and cost arithmetic. They are [export checks](../reports/contract-test-export-controls.json), separate from the model-quality result. Preserve the frozen source revision or installed wheel for later replay; a newer scorer must not silently replace it.
