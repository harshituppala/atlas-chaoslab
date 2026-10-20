# Bedrock validation

Restricted live diagnostics have run through the Bedrock adapter. The default workbench remains offline; enabling paid jobs is a separate operator action. Model results are provisional and still require human review. No AWS application infrastructure has been deployed.

## Recorded results

The v4 workflow passed seventeen of eighteen original reasoning cases, ten of twelve transfer cases and all nine obligations in three multi-obligation scenarios. The paired hostile-evidence run passed eight of twelve cases and cited a forbidden appendix in one hostile case. These are small, same-author synthetic datasets, not representative contract accuracy estimates.

The transfer and paired failures remain visible. A 15-day deletion policy was misclassified against a within-30-day requirement; a keyword filter also removed legitimate security-training evidence. Valid source spans did not prevent hostile evidence selection.

See the [original reasoning report](../reports/reasoning-live-v4.json), [transfer report](../reports/reasoning-transfer-live-v4.json), [scenario report](../reports/scenarios-live-v4.json) and [paired failure analysis](adr/030-live-paired-injection-diagnostic.md). Each report identifies its own execution inputs. They should not be combined into one accuracy figure.

## Preparing another run

1. Check the exact model, region and inference profile. Confirm that the intended profile supports the required structured output and token-counting calls. A Canadian API endpoint alone does not establish Canadian-only inference routing.
2. Use temporary credentials for the restricted inference role and verify the assumed-role identity before running the adapter. A console sign-in alone is not a configured SDK session. Keep configuration, caches and receipts under private, ignored project directories; do not use an administrator profile.
3. Check current pricing and record the model/profile, region, positive token rates, verification date and source in the private configuration. The guarded workflow refuses missing or stale price information.
4. Export a label-free input manifest. Choose fresh private filenames; existing or interrupted artifacts must not be overwritten.
5. Inspect the dry plan and remaining cumulative test allowance. Paid execution requires explicit opt-in. Do not treat a login refresh, a budget alert or unused AWS credits as permission to expand spending.

From the repository root, with a reviewed private configuration:

```sh
PYTHONPATH=src .runtime/bin/python -m chaoslab.reasoning \
  --export-inputs var/bedrock/reasoning-inputs-new.json
PYTHONPATH=src .runtime/bin/python -m atlas.models.benchmark \
  --input var/bedrock/reasoning-inputs-new.json \
  --config var/bedrock/config.json \
  --output var/bedrock/reasoning-run-new.json \
  --max-cases 1
```

The second command is a dry plan. Adding `--allow-paid` performs inference and reserves the configured worst-case run cost before provider initialization. Only do so within the approved allowance. The local campaign journal coordinates cooperating processes; it is not an AWS account or credit-card spending cap.

A timeout can leave a billable request in progress. Preserve the reservation and receipts, inspect the fixed error category and do not automatically retry. `--continue-invalid-output` can retain a locally invalid model response as a failed evaluation case; it does not permit continuing after an unknown-billing or provider failure.

Score a completed artifact without making new model calls:

```sh
PYTHONPATH=src .runtime/bin/python -m chaoslab.reasoning \
  --artifacts var/bedrock/reasoning-run-new.json \
  --output var/bedrock/reasoning-score-new.json
```

A one-case smoke result covers one case. The scorer reports unrun cases explicitly. Keep new scores separate from the extractive baseline and retain the original expectations when investigating a failure.

## Reproduction limits

Public reports omit raw provider output, prompts, credentials and private source-bearing artifacts. A clean checkout can run the offline checks, but cannot reconstruct the original inference from an aggregate report. Rescoring retained private artifacts requires their matching source and dataset identity. The [paired-run guide](live-injection-runbook.md) describes that check.

Authentication, provider activation and pricing can change. Follow the official [model access](https://docs.aws.amazon.com/bedrock/latest/userguide/model-access.html), [structured output](https://docs.aws.amazon.com/bedrock/latest/userguide/structured-output.html), [temporary CLI login](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-sign-in.html) and [pricing](https://aws.amazon.com/bedrock/pricing/) documentation for new setup. Review any requested account terms, subscription or permission expansion before accepting it.
