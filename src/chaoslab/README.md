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

## Comparisons

Paired comparisons rescore two saved raw runs against the same dataset and scorer. They report changed obligations, missing attempts and regressions, including regressions inside scenarios that already failed for another reason. Existing aggregate percentages are not enough to reconstruct that comparison.

The hostile-evidence cases pair an ordinary source with an instruction-bearing variant. Citation contamination, relation errors and unauthorized review states are separate findings. The recorded v4 run passed eight of twelve cases and cited a forbidden appendix in one hostile case. That is a result on those fixtures, not a general attack-success estimate.

## Independence and limits

The core runner and scorers do not import ATLAS's decision logic. The bundled adapter and several retrieval probes do use ATLAS, and both projects currently share dependency setup and CI. Separate installation and a second application adapter are still needed before calling CHAOSLAB a standalone platform.

The golden cases are same-author synthetic development data. They catch regressions but do not provide blinded external validation. The recovery scenarios use simulated lease clocks, and process deadlines are not a hostile-code sandbox. Read [the recovery guide](../../docs/recovery-evaluation-runbook.md) for the exact execution boundary.
