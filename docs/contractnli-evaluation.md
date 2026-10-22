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

The same task is available as `chaoslab-contractnli` in the separately installed evaluator, version 0.1.2. It uses the existing child-process deadline and artifact budgets. Adapters are trusted local code with filesystem and network permissions, not a sandbox. The recorded reference is a constant-label function: it runs no model and retrieves no evidence.

## Recorded result

The [development report](../reports/contractnli-development.json) covers all 61 development contracts and 1,037 claims, without selecting cases based on answers. The constant `NotMentioned` reference labels 423 claims correctly: **40.8% accuracy**, **0.193 macro F1**, and **zero evidence recall**. Evidence precision is undefined because it selected no spans; the report records `null`.

This is a useful floor, not an AI achievement. Its apparent accuracy comes entirely from the label distribution: 519 entailments, 95 contradictions and 423 not-mentioned cases. A useful model comparison must improve on that reference and retrieve the authored evidence, rather than just report a larger overall percentage.

## Scoring

Label accuracy includes every authored claim. Macro F1 averages the three fixed classes, with zero for a zero-denominator class. Evidence precision/recall count span indexes only on claims whose expected label is entailment or contradiction, following the task's evidence boundary. Exact-set scoring requires every marked evidence span; selecting a real but incomplete excerpt is insufficient. Joint correctness requires both the right label and the complete evidence set.

A missing prediction stays missing. A failed process or unusable document response counts against every claim in that document. Wrong but structurally valid labels remain scored errors. Invalid gold annotations stop the run before any adapter executes. Report publication is atomic, rejects non-finite metrics and refuses the archive as a destination. Exit zero means the run was recorded; it does not mean all answers were correct.

The public report contains aggregate results, dataset/source fingerprints and the adapter reference. It contains no contract text, raw predictions, filenames or document URLs. Evaluation wall time includes sequential process startup and scoring, excluding download and archive loading. It is not model-request latency.

## What remains

The labels were authored outside this project, which improves on the same-author synthetic fixtures. They concern an NDA inference task rather than end-to-end RFP review. They do not establish legal correctness or general contract accuracy. The public corpus may have appeared in a pretrained model's training data. The test split remains unused; a model adapter, private raw-observation journaling and a frozen test comparison are still required.
