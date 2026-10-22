# CHAOSLAB

An evaluation runner for checking agent output and failure behavior.

ATLAS was the first system tested with it. A valid source span did not necessarily support the right requirement, and valid JSON did not guarantee a useful assessment. CHAOSLAB checks those properties separately so a single pass rate cannot hide the difference.

[Evaluation commands](../../docs/comparison-runbook.md) · [Recovery checks](../../docs/recovery-evaluation-runbook.md) · [Recorded model failures](../../docs/adr/030-live-paired-injection-diagnostic.md)

## Running it

Install the repository's locked environment using the [setup instructions](../../README.md#run-atlas-locally), then run from the repository root:

```sh
PYTHONPATH=src .runtime/bin/python -m chaoslab \
  --dataset datasets/golden.json \
  --adapter atlas.chaos_adapter:run \
  --output var/evaluation.json

PYTHONPATH=src .runtime/bin/python -m chaoslab.recovery \
  --output var/recovery.json
```

The first command evaluates the extractive contract. The second exercises recovery scenarios. An adapter receives JSON inputs without expected labels and returns observations for scoring. Select a trusted adapter explicitly; the child process retains the local user's filesystem and network permissions.

The runner writes per-case outcomes and the configuration used. A timeout, malformed response or missing case stays distinguishable from an answer with insufficient evidence. Recovery failures are recorded before the command exits unsuccessfully.

## Install the evaluator on its own

From a source checkout, install the evaluator into a separate Python 3.12+ environment:

```sh
python -m pip install ./src/chaoslab
chaoslab-compare --help
```

The `chaoslab-eval` wheel has no third-party runtime dependencies. `chaoslab-compare` takes a dataset and two saved raw runs and rescores them without installing ATLAS. Use `--require-fixture-gate` to return a failing exit code for missing attempts, regressions or candidate failures. The report is written before that exit. A malformed dataset or artifact instead exits with code 2 and preserves any previous report. Saved succeeded rows are admitted before scoring; a wrong citation or review state still counts as a quality failure. See the [artifact decision](../../docs/adr/043-saved-observation-admission.md).

The [package check](../../scripts/verify_chaoslab_package.py) builds a wheel, installs it in a fresh environment and runs from outside the source tree. It checks unchanged output, a corrupt citation and a missing attempt, then invokes a separate trusted adapter. These are controlled installation checks, not agent benchmark results.

ATLAS adapters, database drivers and embedding models still need their integration environment. Execution adapters use POSIX process controls; Windows is not supported by this release.

## Comparisons

Paired comparisons rescore two saved raw runs against the same dataset and scorer. They report changed obligations, missing attempts and regressions, including regressions inside scenarios that already failed for another reason. Existing aggregate percentages are not enough to reconstruct that comparison.

The hostile-evidence cases pair an ordinary source with an instruction-bearing variant. Citation contamination, relation errors and unauthorized review states are separate findings. The recorded v4 run passed eight of twelve cases and cited a forbidden appendix in one hostile case. That is a result on those fixtures, not a general attack-success estimate.

## External contract labels

The separate [ContractNLI task](../../docs/contractnli-evaluation.md) evaluates fixed claims and evidence spans against externally authored NDA annotations. Its first report uses a constant-label reference on the complete development split: 40.8% label accuracy and zero evidence recall. That is a baseline for a future model comparison, not an AI performance claim. Raw contracts stay private and the test split remains unused. A run can now save private observations and replay them without importing the adapter or making another model request. The recorded constant-label capture and replay have identical scores; the task guide explains the file checks and their limits.

## Document ingestion

The [layout checks](../../docs/layout-evaluation.md) test canonical text and authored page/paragraph locations. They include repeated text on different pages and DOCX reading rules. They do not score visual layout or infer relationships between table cells.

## Writing cases

Each expected obligation must quote its RFP. Relations are `supported`, `contradicted` or `insufficient`; evidence IDs must name unique knowledge records in that case. Document IDs cannot overlap, including between the RFP and knowledge records. Invalid labels or ambiguous source identities stop the experiment before scoring. These checks catch authoring mistakes; they cannot establish whether a label is factually right.

## Independence and limits

The core runner and scorers do not import ATLAS's decision logic. The bundled adapter and several retrieval probes do use ATLAS, and both projects currently share dependency setup and CI. Separate installation is verified for saved-run comparisons and trusted adapter invocation. A second application adapter and broader independent datasets are still needed before calling it a general agent-evaluation platform.

The RFP golden cases are same-author synthetic development data. The separate ContractNLI task uses external annotations, with different inputs and metrics; neither establishes blinded evaluation or general RFP accuracy. The recovery scenarios use simulated lease clocks, and process deadlines are not a hostile-code sandbox. Read [the recovery guide](../../docs/recovery-evaluation-runbook.md) for the exact execution boundary.
