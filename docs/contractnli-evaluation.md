# External contract evaluation

CHAOSLAB now has a separate ContractNLI task. A system receives a contract and fixed claims, predicts `Entailment`, `Contradiction` or `NotMentioned`, and selects evidence by sentence/list-item index. It receives no expected labels or evidence annotations.

The data comes from Yuta Koreeda and Christopher D. Manning's [ContractNLI](https://stanfordnlp.github.io/contract-nli/), published in [Findings of EMNLP 2021](https://aclanthology.org/2021.findings-emnlp.164/). The dataset uses [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) and published download terms. The owner approved its use. Original notices remain with the private archive. No contract text or copied annotations are bundled with this repository.

## Run the reference

Review the terms on the official download page, then save the unmodified archive as `var/external-data/contractnli/contract-nli.zip`. The loader checks its pinned digest before opening it. It reads only `contract-nli/dev.json` in place. It extracts no paths and loads neither the training nor test JSON. One PDF in the original archive has a backslash in its filename; that unselected name never becomes a filesystem destination.

```sh
PYTHONPATH=src .runtime/bin/python -m chaoslab.contractnli \
  --archive var/external-data/contractnli/contract-nli.zip \
  --adapter chaoslab.contractnli:always_not_mentioned \
  --output var/contractnli-development.json
```

The same task is available as `chaoslab-contractnli` in the separately installed evaluator, version 0.1.3. It uses the existing child-process deadline and artifact budgets. Adapters are trusted local code with filesystem and network permissions, not a sandbox. The recorded reference is a constant-label function: it runs no model and retrieves no evidence.

## Recorded result

The [development report](../reports/contractnli-development.json) covers all 61 development contracts and 1,037 claims, without selecting cases based on answers. The constant `NotMentioned` reference labels 423 claims correctly: **40.8% accuracy**, **0.193 macro F1**, and **zero evidence recall**. Evidence precision is undefined because it selected no spans; the report records `null`.

This is a useful floor, not an AI achievement. Its apparent accuracy comes entirely from the label distribution: 519 entailments, 95 contradictions and 423 not-mentioned cases. A useful model comparison must improve on that reference and retrieve the authored evidence, rather than just report a larger overall percentage.

## Scoring

Label accuracy includes every authored claim. Macro F1 averages the three fixed classes, with zero for a zero-denominator class. Evidence precision/recall count span indexes only on claims whose expected label is entailment or contradiction, following the task's evidence boundary. Exact-set scoring requires every marked evidence span; selecting a real but incomplete excerpt is insufficient. Joint correctness requires both the right label and the complete evidence set.

A missing prediction stays missing. A failed process or unusable document response counts against every claim in that document. Wrong but structurally valid labels remain scored errors. Invalid gold annotations stop the run before any adapter executes. Report publication is atomic, rejects non-finite metrics and refuses the archive as a destination. Exit zero means the run was recorded; it does not mean all answers were correct.

The public report contains aggregate results, dataset/source fingerprints and the adapter reference. It contains no contract text, raw predictions, filenames or document URLs. Evaluation wall time includes sequential process startup and scoring, excluding download and archive loading. It is not model-request latency.

## What remains

The labels were authored outside this project, which improves on the same-author synthetic fixtures. They concern an NDA inference task rather than end-to-end RFP review. They do not establish legal correctness or general contract accuracy. The public corpus may have appeared in a pretrained model's training data. The test split remains unused. The completed development comparison below does not replace a frozen test comparison, which remains unfinished.

## Save a run and rescore it

A model run should not have to be repeated just because the judge changes. Add `--journal` to save one private observation per contract, including malformed responses and invocation failures. The directory must be new and under `var/`; pick a different name for each run.

```sh
PYTHONPATH=src .runtime/bin/python -m chaoslab.contractnli \
  --archive var/external-data/contractnli/contract-nli.zip \
  --adapter chaoslab.contractnli:always_not_mentioned \
  --journal var/contractnli-runs/reference-01 \
  --output var/reference-01.json

PYTHONPATH=src .runtime/bin/python -m chaoslab.contractnli \
  --archive var/external-data/contractnli/contract-nli.zip \
  --replay var/contractnli-runs/reference-01/observations.jsonl \
  --output var/reference-01-replayed.json
```

Replay reads the same pinned development inputs and scores the saved responses. It neither imports the original adapter nor calls a model. Compare the reports' `results` objects for score equality; their wall times and run modes describe different work. The original scorer fingerprint stays with the observations, while each new report identifies the scorer used for that evaluation.

The recorded [capture](../reports/contractnli-development.json) and [replay](../reports/contractnli-replay.json) produced identical result objects across all 61 contracts and 1,037 claims. Both refer to the same complete observation file. These are two scorings of one constant-label run, not independent trials or model comparisons.

Observations may contain private contract excerpts returned by an adapter. They stay in ignored `var/`, in a new owner-only directory with an owner-only file. Inputs and expected annotations are not copied into the journal. Public reports contain only aggregate scores and an observation digest/count. Do not publish raw observations or attach them to CI artifacts.

The writer flushes each record and marks the file complete only after evaluation and a source-stability check. An interrupted run leaves a partial file; replay refuses it. A recording error stops report publication rather than hiding the error as a model failure. Replay also rejects missing or duplicate contracts, mismatched inputs, altered checksums, trailing data, ambiguous JSON, oversized files and broadly readable files. The limits are 128 MiB per journal and the adapter-output budget plus a small envelope per line.

These controls detect incomplete or inconsistent local files. They are not signatures: someone with access to the same account can rewrite both observations and checksums. Adapter code still has local-user privileges. Keep the archive and journal protected, and review aggregate reports before publication.

## Model integration

The optional [Bedrock runner](contract-model-runbook.md) uses the full project environment and a shared spending ledger. It does not change the independent evaluator wheel. Two live development attempts stopped during preflight, after eighteen and twenty-three validated responses. Those historical overlapping prefixes were incomplete. [The stopped-run record](../reports/contract-model-stopped.json) retains their costs, reservations and unresolved failure scope. A later explicit continuation completed the development cohort without changing either original attempt.


## Complete development model comparison — October 26

The [model report](../reports/contract-model-development.json) covers all 61 development contracts and 1,037 claims. It combines 23 admitted saved responses with 38 new Bedrock responses from Claude Haiku 4.5. No answer was changed or selected based on its score. The original attempts and their full spending reservations remain intact.

| Measure | Constant NotMentioned reference | Model |
| --- | ---: | ---: |
| Label accuracy, all 1,037 claims | 40.8% | 77.4% |
| Macro label F1 | 0.193 | 0.692 |
| Correct label and exact evidence set | 40.8% | 48.7% |
| Evidence precision, 614 evidence-bearing claims | Undefined; no spans selected | 84.2% |
| Evidence recall, same claims | 0% | 52.6% |

The joint measure includes not-mentioned claims, whose expected evidence set is empty. It must not be read as evidence extraction accuracy. On the 614 claims that require evidence, the model selected the exact complete evidence set for 220 (35.8%). It omitted two claim predictions; both stay in the denominator. No document response failed structurally.

The overall accuracy hides a substantial contradiction problem: only 41 of 95 contradictions received the correct label. Another 25 were labeled entailments and 29 not mentioned. The model also labeled 105 not-mentioned claims as entailments. These errors matter in a review application: a plausible passage can support an incorrect conclusion. The result supports mandatory source inspection and human review, not unattended contract decisions.

The aggregate exporter replayed the complete saved journal and matched the original scores. A [second replay](../reports/contract-model-standalone-replay.json) built and installed a fresh CHAOSLAB wheel outside the checkout, with ATLAS, boto3, FastAPI and SQLAlchemy absent. It reproduced every result without calling a provider. This establishes independent rescoring, not provider authenticity of saved responses.

The 38 new calls used 276,623 input and 16,366 output tokens, with a recorded inference estimate of US$0.3942983. The reused prefix has a separate estimate of US$0.2406261. The continuation took about 374 seconds, including token preflight, ten-second pacing, responses, recording and scoring; saved-prefix generation time is excluded. These figures are neither invoices nor a complete account bill, and exclude other stopped attempts. All reservations remain retained.

This is an NDA development task with externally authored annotations. It is not an untouched test, an RFP accuracy measurement, legal validation or a continuous 61-request run. The public corpus may have appeared in model training. Raw contracts, predictions and private provider records remain excluded from this repository. The next gate is to freeze the protocol before loading the untouched test split.
